"""Conservative SoccerMon Parquet import; no timestamp reconstruction or filtering.

Native IMU axes remain in ``raw_source``: accl_* in documented g, gyro_* in
documented deg/s. Gravity, orientation and calibration are unknown, so Walking
linear/gravity and alpha/beta/gamma fields are deliberately left unset.

GNSS candidates collapse only consecutive identical GNSS/auxiliary exports with
identical source time text. Different time groups are always retained, even for
a stationary player. Candidates do not establish independently acquired fixes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date
import hashlib
import math
from pathlib import Path
import re
from typing import BinaryIO

from football_stat_tracker.data_model import (
    GnssPositionStatus, GnssSample, ImuSample, RawSensorSample,
    RecordingProvenance, SessionMetadata, TrackingSession,
)


IMU_COLUMNS = tuple(prefix + axis for prefix in ("accl_", "gyro_") for axis in "xyz")
GNSS_COLUMNS = (
    "lat", "lon", "speed", "hacc", "hdop", "signal_quality", "num_satellites",
    "heart_rate", "inst_acc_impulse",
)
REQUIRED_COLUMNS = frozenset(("player_name", "time", "lat", "lon", *IMU_COLUMNS))
KNOWN_COLUMNS = REQUIRED_COLUMNS | frozenset(GNSS_COLUMNS)
# Source units only. No scale is established for the native quality encodings.
SOURCE_UNITS = {
    "lat": "degrees", "lon": "degrees", "speed": "m/s", "heart_rate": "bpm",
    "inst_acc_impulse": "m/s^2",
    **{name: "g" for name in IMU_COLUMNS[:3]},
    **{name: "deg/s" for name in IMU_COLUMNS[3:]},
}
BATCH_SIZE = 32768


class SoccerMonImportError(ValueError):
    """The recording cannot be represented without guessing or losing data."""


def parse_soccermon_time_ms(value: str) -> int:
    """Parse exact milliseconds since local midnight, without date/timezone repair."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,3})?", value
    ):
        raise SoccerMonImportError(f"Unsupported source time: {value!r}")
    hour, minute, second = (int(part) for part in value[:8].split(":"))
    if hour > 23 or minute > 59 or second > 59:
        raise SoccerMonImportError(f"Invalid source time: {value!r}")
    fraction = int(value[9:].ljust(3, "0")) if len(value) > 8 else 0
    return ((hour * 60 + minute) * 60 + second) * 1000 + fraction


def _sha256(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def _validate_schema(schema, pa) -> None:
    names = schema.names
    if len(set(names)) != len(names):
        raise SoccerMonImportError("Duplicate Parquet column names")
    missing = REQUIRED_COLUMNS - set(names)
    if missing:
        raise SoccerMonImportError("Missing required columns: " + ", ".join(sorted(missing)))
    unknown = set(names) - KNOWN_COLUMNS
    if unknown:
        raise SoccerMonImportError("Unsupported columns (would lose data): " + ", ".join(sorted(unknown)))
    for field in schema:
        if field.name in ("player_name", "time"):
            valid = pa.types.is_string(field.type) or pa.types.is_large_string(field.type)
        else:
            # Entirely missing numeric columns can be Arrow null-typed. Keep
            # them; missing measurements are different from missing columns.
            valid = (pa.types.is_integer(field.type) or pa.types.is_floating(field.type)
                     or pa.types.is_null(field.type))
        if not valid:
            raise SoccerMonImportError(f"Invalid type for {field.name!r}: {field.type}")


def _position_status(lat, lon) -> GnssPositionStatus:
    if lat is None or lon is None:
        return GnssPositionStatus.MISSING
    if not math.isfinite(lat) or not math.isfinite(lon):
        return GnssPositionStatus.NON_FINITE
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return GnssPositionStatus.OUT_OF_RANGE
    if lat == 0 and lon == 0:
        return GnssPositionStatus.ZERO_PAIR
    return GnssPositionStatus.USABLE


def _same_values(left, right) -> bool:
    # Null equals null; NaNs are conservatively retained separately. Signed
    # zero distinctions must not disappear when reconstructing original rows.
    for a, b in zip(left, right):
        if a != b:
            return False
        if isinstance(a, float) and a == 0 and math.copysign(1, a) != math.copysign(1, b):
            return False
    return True


def _gnss_candidate(raw: RawSensorSample, timestamp: int, origin: int) -> GnssSample:
    lat, lon = raw.get("lat"), raw.get("lon")
    status = _position_status(lat, lon)
    usable = status is GnssPositionStatus.USABLE
    return GnssSample(
        timestamp_raw_ms=timestamp, timestamp_analysis_ms=timestamp - origin,
        latitude_deg=lat if usable else None, longitude_deg=lon if usable else None,
        altitude_m=None, speed_mps=raw.get("speed"), heading_deg=None,
        horizontal_accuracy_m=None, raw_source=raw, position_status=status,
        observation_kind="timestamp_group_candidate",
    )


def import_soccermon_session(recording_path: str | Path) -> TrackingSession:
    """Import one single-player recording, retaining original order and values.

    Required: player_name/time strings, lat/lon and six numeric IMU columns.
    Speed, quality, heart rate and impulse are optional numeric columns. Sensor
    nulls/non-finites are preserved. Missing identity/time, multiple identities,
    unsupported columns/types, corrupt or empty files raise SoccerMonImportError.
    Backwards times are preserved (including possible midnight ambiguity).

    Parsing uses bounded Arrow batches; the returned canonical tuples are eager.
    pyarrow is imported lazily, so existing Walking usage needs no dependency.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise SoccerMonImportError("SoccerMon import requires pyarrow; install requirements-v0b1.txt") from error

    path = Path(recording_path)
    try:
        with path.open("rb") as handle:
            before = path.stat()
            digest = _sha256(handle)
            pf = pq.ParquetFile(handle)
            _validate_schema(pf.schema_arrow, pa)
            if pf.metadata.num_rows == 0:
                raise SoccerMonImportError("Empty SoccerMon recording")

            # First pass establishes the identity and exact time-of-day span.
            # Intern repeated original time strings without creating new times.
            time_cache = {}
            player = None
            row_index = 0
            for batch in pf.iter_batches(batch_size=BATCH_SIZE, columns=["player_name", "time"]):
                players = batch.column("player_name").to_pylist()
                times = batch.column("time").to_pylist()
                for identity, text in zip(players, times):
                    if not identity or not identity.strip():
                        raise SoccerMonImportError(f"Missing player_name at source row {row_index}")
                    if player is not None and identity != player:
                        raise SoccerMonImportError(f"Multiple players in one recording at source row {row_index}")
                    player = identity
                    if text not in time_cache:
                        try:
                            time_cache[text] = (text, parse_soccermon_time_ms(text))
                        except SoccerMonImportError as error:
                            raise SoccerMonImportError(f"{error} at source row {row_index}") from error
                    row_index += 1
            origin = min(ms for _, ms in time_cache.values())
            end = max(ms for _, ms in time_cache.values())
            context = [("created_by", pf.metadata.created_by or ""),
                       ("row_groups", str(pf.num_row_groups)),
                       ("documented_nominal_gnss_hz", "10"),
                       ("documented_nominal_imu_hz", "100")]
            match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})-(.+)\.parquet", path.name)
            if match:
                try:
                    recording_date = date.fromisoformat(match[1]).isoformat()
                except ValueError as error:
                    raise SoccerMonImportError("Invalid recording date in filename") from error
                if match[2] != player:
                    raise SoccerMonImportError("Filename/player_name identity mismatch")
                context.append(("recording_date_from_filename", recording_date))
            provenance = RecordingProvenance(
                source_path=str(path.resolve()), sha256=digest,
                source_row_count=pf.metadata.num_rows,
                source_columns=tuple((f.name, str(f.type)) for f in pf.schema_arrow),
                source_metadata=tuple(sorted((pf.metadata.metadata or {}).items())),
                timestamp_basis="local_time_of_day_ms_timezone_unknown", context=tuple(context),
            )
            gnss_columns = tuple(n for n in GNSS_COLUMNS if n in pf.schema_arrow.names)
            imu, gnss = [], []
            pending_raw = None
            pending_timestamp = None
            pending_count = 0
            row_index = 0
            for batch in pf.iter_batches(batch_size=BATCH_SIZE):
                columns = {n: batch.column(n).to_pylist() for n in batch.schema.names}
                for i, source_time in enumerate(columns["time"]):
                    text, timestamp = time_cache[source_time]
                    imu_raw = RawSensorSample(row_index, 1, text, IMU_COLUMNS,
                                              tuple(columns[n][i] for n in IMU_COLUMNS))
                    imu.append(ImuSample(
                        timestamp, timestamp - origin, None, None, None, None,
                        None, None, None, None, None, raw_source=imu_raw,
                    ))
                    values = tuple(columns[n][i] for n in gnss_columns)
                    if (pending_raw is not None and text == pending_raw.timestamp_original
                            and _same_values(values, pending_raw.values)):
                        pending_count += 1
                    else:
                        if pending_raw is not None:
                            gnss.append(_gnss_candidate(replace(pending_raw, source_row_count=pending_count),
                                                        pending_timestamp, origin))
                        pending_raw = RawSensorSample(row_index, 1, text, gnss_columns, values)
                        pending_timestamp = timestamp
                        pending_count = 1
                    row_index += 1
            gnss.append(_gnss_candidate(replace(pending_raw, source_row_count=pending_count),
                                        pending_timestamp, origin))
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns
            ):
                raise SoccerMonImportError("Source file changed during import")
    except SoccerMonImportError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise SoccerMonImportError(f"Cannot read SoccerMon recording {path}: {error}") from error

    return TrackingSession(
        metadata=SessionMetadata(
            source="soccermon", subject_id=player, recording_id=path.stem,
            test_start_raw_ms=origin, test_end_raw_ms=end, gt_type=None,
            distance_reference_m=None, device="STATSports APEX", fs_acc_hz=None,
            fs_gnss_hz=None, path_curvature=None, provenance=provenance,
        ), gnss=tuple(gnss), imu=tuple(imu), ground_truth=None,
    )


def summarize_soccermon_session(session: TrackingSession) -> dict:
    """Describe stored timestamps/candidates, never physical sampling frequency."""
    if session.metadata.source != "soccermon" or session.metadata.provenance is None:
        raise ValueError("Expected an imported SoccerMon session")
    times = [s.timestamp_raw_ms for s in session.imu]
    intervals = Counter(b - a for a, b in zip(times, times[1:]))
    groups = [times[0]] + [b for a, b in zip(times, times[1:]) if a != b]
    group_intervals = Counter(b - a for a, b in zip(groups, groups[1:]))
    statuses = Counter(s.position_status.value for s in session.gnss)
    invalid_rows = sum(s.raw_source.source_row_count for s in session.gnss
                       if s.position_status is not GnssPositionStatus.USABLE)
    candidates_by_group = Counter()
    group_index = 0
    previous_time = None
    for candidate in session.gnss:
        if candidate.timestamp_raw_ms != previous_time:
            group_index += 1
        candidates_by_group[group_index] += 1
        previous_time = candidate.timestamp_raw_ms
    return {
        "recording_id": session.metadata.recording_id,
        "source_rows": session.metadata.provenance.source_row_count,
        "imu_samples": len(session.imu), "gnss_candidates": len(session.gnss),
        "independently_identifiable_gnss_fixes": None,
        "gnss_position_status_counts": dict(statuses),
        "invalid_coordinate_source_rows": invalid_rows,
        "duplicate_timestamp_rows": len(times) - len(set(times)),
        "adjacent_duplicate_timestamps": intervals.get(0, 0),
        "backwards_timestamp_intervals": sum(n for dt, n in intervals.items() if dt < 0),
        "contiguous_timestamp_groups": len(groups),
        "groups_with_multiple_candidates": sum(n > 1 for n in candidates_by_group.values()),
        "duration_s": (times[-1] - times[0]) / 1000 if all(dt >= 0 for dt in intervals) else None,
        "time_of_day_span_s": (max(times) - min(times)) / 1000,
        "source_interval_counts_ms": dict(sorted(intervals.items())),
        "group_interval_counts_ms": dict(sorted(group_intervals.items())),
        "ambiguities": ["Receiver fix freshness is unknown", "Exact IMU sample timing is unknown",
                        "Timezone and midnight behavior are unknown", "Quality code scales are unknown",
                        "Accelerometer gravity/axis conventions are unknown",
                        "Gyroscope units are documented but not independently verified"],
    }
