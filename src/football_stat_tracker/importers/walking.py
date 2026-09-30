"""Importer for one session of the Walking dataset."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from football_stat_tracker.data_model import (
    ContinuousGroundTruth,
    FinalGroundTruth,
    GnssSample,
    GroundTruth,
    GroundTruthAlignment,
    GroundTruthSample,
    GroundTruthType,
    ImuSample,
    SessionMetadata,
    TrackingSession,
)


class WalkingImportError(ValueError):
    """Raised when a Walking session cannot be mapped safely."""


@dataclass(frozen=True, slots=True)
class _WalkingTrackMetadata:
    gt_type: GroundTruthType
    distance_reference_m: float | None
    device: str | None
    fs_acc_hz: float | None
    fs_gnss_hz: float | None
    path_curvature: int | None


def import_walking_session(session_directory: str | Path) -> TrackingSession:
    """Load and normalize a Walking session into the common data model.

    Samples are sorted, restricted to the inclusive test window, and rebased
    to ``testStart``. Continuous and final ground truths are represented
    explicitly and never prevent valid GNSS and IMU streams from loading.
    """

    session_path = Path(session_directory)
    if not session_path.is_dir():
        raise WalkingImportError(f"Walking session directory not found: {session_path}")

    test_start, test_end = _load_test_window(session_path / "events.csv")
    track_metadata = _load_track_metadata(session_path)
    metadata = SessionMetadata(
        source="walking",
        subject_id=session_path.parent.name,
        recording_id=session_path.name,
        test_start_raw_ms=test_start,
        test_end_raw_ms=test_end,
        gt_type=track_metadata.gt_type,
        distance_reference_m=track_metadata.distance_reference_m,
        device=track_metadata.device,
        fs_acc_hz=track_metadata.fs_acc_hz,
        fs_gnss_hz=track_metadata.fs_gnss_hz,
        path_curvature=track_metadata.path_curvature,
    )

    return TrackingSession(
        metadata=metadata,
        gnss=_load_gnss(session_path / "positions.csv", test_start, test_end),
        imu=_load_imu(session_path / "motion.csv", test_start, test_end),
        ground_truth=_load_ground_truth(
            session_path,
            track_metadata.gt_type,
            track_metadata.distance_reference_m,
            test_start,
            test_end,
        ),
    )


def _read_rows(path: Path, required_columns: Iterable[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise WalkingImportError(f"Required Walking file not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = set(reader.fieldnames or ())
        missing = set(required_columns) - fieldnames
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise WalkingImportError(f"Missing columns in {path.name}: {missing_list}")

        # Walking CSV files contain an unnamed exported dataframe index. It is
        # deliberately discarded rather than propagated into the data model.
        return [
            {key: value for key, value in row.items() if key not in (None, "")}
            for row in reader
        ]


def _required_float(row: dict[str, str], column: str, path: Path) -> float:
    value = row.get(column, "")
    if value == "":
        raise WalkingImportError(f"Missing required value {column!r} in {path.name}")
    try:
        return float(value)
    except ValueError as error:
        raise WalkingImportError(
            f"Invalid numeric value for {column!r} in {path.name}: {value!r}"
        ) from error


def _optional_float(row: dict[str, str], column: str, path: Path) -> float | None:
    value = row.get(column, "")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError as error:
        raise WalkingImportError(
            f"Invalid numeric value for {column!r} in {path.name}: {value!r}"
        ) from error


def _load_track_metadata(session_path: Path) -> _WalkingTrackMetadata:
    path = session_path.parent.parent / "metadata_tracks.csv"
    rows = _read_rows(
        path,
        (
            "testName",
            "distanceReference",
            "device",
            "fs_acc",
            "fs_gnss",
            "path curvature",
            "gt_type",
        ),
    )
    matches = [row for row in rows if row["testName"] == session_path.name]
    if len(matches) != 1:
        raise WalkingImportError(
            f"Expected exactly one metadata row for {session_path.name!r} in {path}"
        )

    row = matches[0]
    raw_gt_type = row["gt_type"].strip().lower()
    try:
        gt_type = GroundTruthType(raw_gt_type)
    except ValueError as error:
        raise WalkingImportError(
            f"Unsupported ground-truth type for {session_path.name}: {raw_gt_type!r}"
        ) from error

    raw_curvature = row["path curvature"]
    try:
        path_curvature = int(raw_curvature) if raw_curvature != "" else None
    except ValueError as error:
        raise WalkingImportError(
            f"Invalid path curvature for {session_path.name}: {raw_curvature!r}"
        ) from error

    return _WalkingTrackMetadata(
        gt_type=gt_type,
        distance_reference_m=_optional_float(row, "distanceReference", path),
        device=row["device"] or None,
        fs_acc_hz=_optional_float(row, "fs_acc", path),
        fs_gnss_hz=_optional_float(row, "fs_gnss", path),
        path_curvature=path_curvature,
    )


def _load_test_window(path: Path) -> tuple[float, float]:
    rows = _read_rows(path, ("testStart", "testEnd"))
    if len(rows) != 1:
        raise WalkingImportError(f"Expected exactly one event row in {path.name}")

    test_start = _required_float(rows[0], "testStart", path)
    test_end = _required_float(rows[0], "testEnd", path)
    if test_end < test_start:
        raise WalkingImportError("testEnd precedes testStart")
    return test_start, test_end


def _load_gnss(path: Path, test_start: float, test_end: float) -> tuple[GnssSample, ...]:
    columns = (
        "ms",
        "latitude",
        "longitude",
        "altitude",
        "confInterval",
        "heading",
        "speed",
    )
    rows = _read_rows(path, columns)
    parsed = sorted(rows, key=lambda row: _required_float(row, "ms", path))

    samples = []
    for row in parsed:
        timestamp = _required_float(row, "ms", path)
        if test_start <= timestamp <= test_end:
            samples.append(
                GnssSample(
                    timestamp_raw_ms=timestamp,
                    timestamp_analysis_ms=timestamp - test_start,
                    latitude_deg=_optional_float(row, "latitude", path),
                    longitude_deg=_optional_float(row, "longitude", path),
                    altitude_m=_optional_float(row, "altitude", path),
                    speed_mps=_optional_float(row, "speed", path),
                    heading_deg=_optional_float(row, "heading", path),
                    horizontal_accuracy_m=_optional_float(row, "confInterval", path),
                )
            )
    return tuple(samples)


def _load_imu(path: Path, test_start: float, test_end: float) -> tuple[ImuSample, ...]:
    columns = (
        "ms",
        "accelX",
        "accelY",
        "accelZ",
        "accelWithGX",
        "accelWithGY",
        "accelWithGZ",
        "rotRateAlpha",
        "rotRateBeta",
        "rotRateGamma",
    )
    rows = _read_rows(path, columns)
    parsed = sorted(rows, key=lambda row: _required_float(row, "ms", path))

    samples = []
    for row in parsed:
        timestamp = _required_float(row, "ms", path)
        if test_start <= timestamp <= test_end:
            samples.append(
                ImuSample(
                    timestamp_raw_ms=timestamp,
                    timestamp_analysis_ms=timestamp - test_start,
                    accel_x_mps2=_optional_float(row, "accelX", path),
                    accel_y_mps2=_optional_float(row, "accelY", path),
                    accel_z_mps2=_optional_float(row, "accelZ", path),
                    accel_including_gravity_x_mps2=_optional_float(
                        row, "accelWithGX", path
                    ),
                    accel_including_gravity_y_mps2=_optional_float(
                        row, "accelWithGY", path
                    ),
                    accel_including_gravity_z_mps2=_optional_float(
                        row, "accelWithGZ", path
                    ),
                    rot_rate_alpha=_optional_float(row, "rotRateAlpha", path),
                    rot_rate_beta=_optional_float(row, "rotRateBeta", path),
                    rot_rate_gamma=_optional_float(row, "rotRateGamma", path),
                )
            )
    return tuple(samples)


def _load_ground_truth(
    session_path: Path,
    gt_type: GroundTruthType,
    distance_reference_m: float | None,
    test_start: float,
    test_end: float,
) -> GroundTruth:
    if gt_type is GroundTruthType.FINAL:
        return FinalGroundTruth(distance_final_m=distance_reference_m)

    path = session_path / "reference_cont_distance.csv"
    if not path.is_file():
        return ContinuousGroundTruth(
            samples=(), alignment=GroundTruthAlignment.UNAVAILABLE
        )

    rows = _read_rows(path, ("ms", "distance"))
    source_samples = sorted(
        (
            _required_float(row, "ms", path),
            _required_float(row, "distance", path),
        )
        for row in rows
    )
    if not source_samples:
        return ContinuousGroundTruth(
            samples=(), alignment=GroundTruthAlignment.UNAVAILABLE
        )

    exact_start = next(
        (distance for timestamp, distance in source_samples if timestamp == test_start),
        None,
    )
    before = [sample for sample in source_samples if sample[0] < test_start]
    after = [sample for sample in source_samples if sample[0] > test_start]
    add_start_sample = False

    if exact_start is not None:
        distance_at_start = exact_start
        alignment = GroundTruthAlignment.EXACT_AT_TEST_START
    elif before and after:
        left_time, left_distance = before[-1]
        right_time, right_distance = after[0]
        fraction = (test_start - left_time) / (right_time - left_time)
        distance_at_start = left_distance + fraction * (right_distance - left_distance)
        alignment = GroundTruthAlignment.INTERPOLATED_AT_TEST_START
        add_start_sample = True
    elif after and after[0][1] == 0.0:
        distance_at_start = 0.0
        alignment = GroundTruthAlignment.ASSUMED_ZERO_AT_TEST_START
        add_start_sample = True
    else:
        distance_at_start = None
        alignment = GroundTruthAlignment.NOT_ALIGNED_TO_TEST_START

    window_samples = [
        sample for sample in source_samples if test_start <= sample[0] <= test_end
    ]
    if add_start_sample:
        window_samples.insert(0, (test_start, distance_at_start))

    return ContinuousGroundTruth(
        alignment=alignment,
        samples=tuple(
            GroundTruthSample(
                timestamp_raw_ms=timestamp,
                timestamp_analysis_ms=timestamp - test_start,
                distance_raw_m=distance,
                distance_analysis_m=(
                    distance - distance_at_start
                    if distance_at_start is not None
                    else None
                ),
            )
            for timestamp, distance in window_samples
        )
    )
