"""Separate, conservative SoccerMon GNSS analysis views; no raw-data mutation.

These views identify exported candidates, not independently acquired fixes.
Clock reversals are refused rather than sorted/repaired (midnight is ambiguous).
Conflicting same-time exports are quarantined as a whole timestamp group.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from football_stat_tracker.data_model import GnssPositionStatus, GnssSample
from football_stat_tracker.gnss_diagnostics import gnss_segment_diagnostics


@dataclass(frozen=True, slots=True)
class CandidateSeries:
    samples: tuple[GnssSample, ...]
    # Original canonical candidate indices, including equivalent duplicates.
    source_indices: tuple[tuple[int, ...], ...]
    break_before: tuple[bool, ...]
    exclusions: tuple[tuple[int, str], ...]
    source_candidate_count: int
    duplicate_time_groups: int
    conflicting_time_groups: int


def _valid_position(sample: GnssSample) -> bool:
    lat, lon = sample.latitude_deg, sample.longitude_deg
    return (
        sample.position_status in (None, GnssPositionStatus.USABLE)
        and lat is not None and lon is not None
        and math.isfinite(lat) and math.isfinite(lon)
        and -90 <= lat <= 90 and -180 <= lon <= 180
        and (lat != 0 or lon != 0)
    )


def _equal_values(left, right) -> bool:
    # NaN-bearing and signed-zero-distinct exports are not safely equivalent.
    for a, b in zip(left, right):
        if a != b:
            return False
        if isinstance(a, float) and a == 0 and math.copysign(1, a) != math.copysign(1, b):
            return False
    return len(left) == len(right)


def _same_export(left: GnssSample, right: GnssSample) -> bool:
    fields = ("latitude_deg", "longitude_deg", "altitude_m", "speed_mps",
              "heading_deg", "horizontal_accuracy_m", "position_status")
    if not _equal_values(tuple(getattr(left, f) for f in fields),
                         tuple(getattr(right, f) for f in fields)):
        return False
    a, b = left.raw_source, right.raw_source
    if a is None or b is None:
        return a is None and b is None
    return a.columns == b.columns and _equal_values(a.values, b.values)


def build_candidate_series(samples: Sequence[GnssSample]) -> CandidateSeries:
    """Keep usable unique-time observations without guessing chronological order.

    Raw and analysis clocks must have the same offset throughout the recording.
    Equal parsed clocks with equal native fields get one representative and all
    original indices; original time strings/row ranges stay on source objects.
    A rejected coordinate or conflicting time group breaks integration support.
    Different times with the same coordinates remain distinct candidates.
    """
    offset = None
    previous = None
    for sample in samples:
        raw, analysis = sample.timestamp_raw_ms, sample.timestamp_analysis_ms
        if not math.isfinite(raw) or not math.isfinite(analysis):
            raise ValueError("Non-finite GNSS timestamp")
        current_offset = raw - analysis
        if offset is None:
            offset = current_offset
        elif current_offset != offset:
            raise ValueError("Raw/analysis timestamp offset changed")
        if previous is not None and raw < previous:
            raise ValueError("GNSS timestamp reversal: chronology/midnight is unresolved")
        previous = raw

    retained, indices, breaks, exclusions = [], [], [], []
    duplicates = conflicts = 0
    pending_break = False
    start = 0
    while start < len(samples):
        end = start + 1
        while end < len(samples) and samples[end].timestamp_raw_ms == samples[start].timestamp_raw_ms:
            end += 1
        group = samples[start:end]
        duplicates += end - start > 1
        if not all(_same_export(group[0], s) for s in group[1:]):
            conflicts += 1
            exclusions.extend((i, "conflicting_timestamp") for i in range(start, end))
            pending_break = True
        elif not _valid_position(group[0]):
            exclusions.extend((i, "invalid_coordinates") for i in range(start, end))
            pending_break = True
        else:
            retained.append(group[0])
            indices.append(tuple(range(start, end)))
            breaks.append(pending_break if len(retained) > 1 else False)
            exclusions.extend((i, "equivalent_timestamp_export") for i in range(start + 1, end))
            pending_break = False
        start = end
    return CandidateSeries(tuple(retained), tuple(indices), tuple(breaks),
                           tuple(exclusions), len(samples), duplicates, conflicts)


@dataclass(frozen=True, slots=True)
class VendorIntegration:
    distance_m: float
    supported_duration_s: float
    total_link_duration_s: float
    interval_distances_m: tuple[float, ...]
    eligible: tuple[bool, ...]
    reasons: tuple[str, ...]
    convention: str
    max_interval_s: float


def integrate_vendor_speed(
    series: CandidateSeries, *, max_interval_s: float = 0.1,
    convention: str = "left",
) -> VendorIntegration:
    """Integrate only unbroken short links with usable speeds at BOTH endpoints.

    Left rectangles are the primary convention: v[i] * actual dt. Right and
    trapezoidal weights are explicit sensitivity experiments on identical input
    support. They do not create points or reconstruct a missing path. Intervals
    crossing quarantined groups, longer than max_interval_s, or with missing,
    negative/non-finite endpoint speeds contribute nothing and are flagged.
    No first/last extrapolation, quality clipping or geometric-speed filtering.
    """
    if not math.isfinite(max_interval_s) or max_interval_s <= 0:
        raise ValueError("max_interval_s must be finite and positive")
    if convention not in ("left", "right", "trapezoidal"):
        raise ValueError("Unknown vendor integration convention")
    if len(series.break_before) != len(series.samples):
        raise ValueError("Invalid candidate break mask")
    distances, eligible, reasons, durations = [], [], [], []
    segments = gnss_segment_diagnostics(series.samples)
    if len(segments) != max(0, len(series.samples) - 1):
        raise ValueError("CandidateSeries must contain only usable positions")
    for segment in segments:
        a, b = series.samples[segment.start_index], series.samples[segment.end_index]
        dt = segment.delta_t_s
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("CandidateSeries must have strictly increasing timestamps")
        speeds = (a.speed_mps, b.speed_mps)
        if series.break_before[segment.end_index]:
            reason = "excluded_candidate_between_endpoints"
        elif dt > max_interval_s:
            reason = "clock_gap"
        elif any(v is None or not math.isfinite(v) or v < 0 for v in speeds):
            reason = "unusable_vendor_speed"
        else:
            reason = "supported"
        ok = reason == "supported"
        if ok:
            speed = speeds[0] if convention == "left" else speeds[1]
            if convention == "trapezoidal":
                speed = speeds[0] / 2 + speeds[1] / 2
            distance = speed * dt
            if not math.isfinite(distance):
                raise ValueError("Vendor distance overflow")
        else:
            distance = 0.0
        distances.append(distance)
        eligible.append(ok)
        reasons.append(reason)
        durations.append(dt)
    return VendorIntegration(
        math.fsum(distances), math.fsum(d for d, ok in zip(durations, eligible) if ok),
        math.fsum(durations), tuple(distances), tuple(eligible), tuple(reasons),
        convention, max_interval_s,
    )
