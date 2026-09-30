"""Diagnostic calculations for raw GNSS tracks.

These helpers describe imported data without filtering, smoothing, correcting,
or changing the distance calculation implemented in :mod:`gnss`.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from football_stat_tracker.data_model import GnssSample
from football_stat_tracker.gnss import EARTH_RADIUS_M, haversine_distance_m


@dataclass(frozen=True, slots=True)
class DistanceError:
    signed_m: float
    relative_percent: float


@dataclass(frozen=True, slots=True)
class CumulativeDistancePoint:
    timestamp_analysis_ms: float
    distance_m: float


@dataclass(frozen=True, slots=True)
class GnssSegmentDiagnostic:
    start_index: int
    end_index: int
    start_timestamp_analysis_ms: float
    end_timestamp_analysis_ms: float
    delta_t_s: float
    distance_m: float
    geometric_speed_mps: float | None
    start_horizontal_accuracy_m: float | None
    end_horizontal_accuracy_m: float | None


@dataclass(frozen=True, slots=True)
class SegmentStatistics:
    count: int
    median_distance_m: float | None
    maximum_distance_m: float | None
    median_delta_t_s: float | None
    maximum_delta_t_s: float | None
    median_geometric_speed_mps: float | None
    maximum_geometric_speed_mps: float | None


@dataclass(frozen=True, slots=True)
class HorizontalAccuracyStatistics:
    count: int
    median_m: float | None
    mean_m: float | None
    maximum_m: float | None


@dataclass(frozen=True, slots=True)
class LocalGnssPoint:
    timestamp_analysis_ms: float
    x_m: float
    y_m: float


def calculate_distance_error(
    distance_gnss_m: float, distance_reference_m: float
) -> DistanceError:
    """Return signed absolute and relative errors against a non-zero reference."""

    if not math.isfinite(distance_gnss_m) or not math.isfinite(distance_reference_m):
        raise ValueError("Distances must be finite")
    if distance_reference_m == 0.0:
        raise ValueError("Reference distance must be non-zero")
    signed_error = distance_gnss_m - distance_reference_m
    return DistanceError(
        signed_m=signed_error,
        relative_percent=100.0 * signed_error / distance_reference_m,
    )


def cumulative_gnss_distance(
    samples: Iterable[GnssSample],
) -> tuple[CumulativeDistancePoint, ...]:
    """Return raw cumulative distance at each valid GNSS position."""

    points: list[CumulativeDistancePoint] = []
    previous: tuple[float, float] | None = None
    cumulative_distance = 0.0

    for sample in samples:
        if not _sample_has_valid_coordinates(sample):
            continue
        current = (sample.latitude_deg, sample.longitude_deg)
        if previous is not None:
            cumulative_distance += haversine_distance_m(
                previous[0], previous[1], current[0], current[1]
            )
        points.append(
            CumulativeDistancePoint(
                timestamp_analysis_ms=sample.timestamp_analysis_ms,
                distance_m=cumulative_distance,
            )
        )
        previous = current

    return tuple(points)


def gnss_segment_diagnostics(
    samples: Sequence[GnssSample],
) -> tuple[GnssSegmentDiagnostic, ...]:
    """Describe every segment between successive valid positions."""

    segments: list[GnssSegmentDiagnostic] = []
    previous: tuple[int, GnssSample] | None = None

    for index, sample in enumerate(samples):
        if not _sample_has_valid_coordinates(sample):
            continue
        if previous is not None:
            previous_index, previous_sample = previous
            delta_t_s = (
                sample.timestamp_analysis_ms
                - previous_sample.timestamp_analysis_ms
            ) / 1000.0
            distance_m = haversine_distance_m(
                previous_sample.latitude_deg,
                previous_sample.longitude_deg,
                sample.latitude_deg,
                sample.longitude_deg,
            )
            speed = distance_m / delta_t_s if delta_t_s > 0.0 else None
            segments.append(
                GnssSegmentDiagnostic(
                    start_index=previous_index,
                    end_index=index,
                    start_timestamp_analysis_ms=previous_sample.timestamp_analysis_ms,
                    end_timestamp_analysis_ms=sample.timestamp_analysis_ms,
                    delta_t_s=delta_t_s,
                    distance_m=distance_m,
                    geometric_speed_mps=speed,
                    start_horizontal_accuracy_m=previous_sample.horizontal_accuracy_m,
                    end_horizontal_accuracy_m=sample.horizontal_accuracy_m,
                )
            )
        previous = (index, sample)

    return tuple(segments)


def summarize_segments(
    segments: Iterable[GnssSegmentDiagnostic],
) -> SegmentStatistics:
    """Summarize raw segment lengths, time intervals, and geometric speeds."""

    values = tuple(segments)
    if not values:
        return SegmentStatistics(0, None, None, None, None, None, None)

    distances = [segment.distance_m for segment in values]
    delta_times = [segment.delta_t_s for segment in values]
    speeds = [
        segment.geometric_speed_mps
        for segment in values
        if segment.geometric_speed_mps is not None
        and math.isfinite(segment.geometric_speed_mps)
    ]
    return SegmentStatistics(
        count=len(values),
        median_distance_m=statistics.median(distances),
        maximum_distance_m=max(distances),
        median_delta_t_s=statistics.median(delta_times),
        maximum_delta_t_s=max(delta_times),
        median_geometric_speed_mps=statistics.median(speeds) if speeds else None,
        maximum_geometric_speed_mps=max(speeds) if speeds else None,
    )


def summarize_horizontal_accuracy(
    samples: Iterable[GnssSample],
) -> HorizontalAccuracyStatistics:
    """Summarize finite horizontal-accuracy values without changing samples."""

    values = [
        sample.horizontal_accuracy_m
        for sample in samples
        if sample.horizontal_accuracy_m is not None
        and math.isfinite(sample.horizontal_accuracy_m)
    ]
    if not values:
        return HorizontalAccuracyStatistics(0, None, None, None)
    return HorizontalAccuracyStatistics(
        count=len(values),
        median_m=statistics.median(values),
        mean_m=statistics.fmean(values),
        maximum_m=max(values),
    )


def local_gnss_coordinates(
    samples: Iterable[GnssSample],
) -> tuple[LocalGnssPoint, ...]:
    """Project valid positions locally with an equirectangular approximation.

    The first valid position is the origin. This projection is intended only
    for visualization of these short tracks, not for distance calculation.
    """

    valid_samples = [sample for sample in samples if _sample_has_valid_coordinates(sample)]
    if not valid_samples:
        return ()

    origin_latitude_rad = math.radians(valid_samples[0].latitude_deg)
    origin_longitude_rad = math.radians(valid_samples[0].longitude_deg)
    cosine_origin_latitude = math.cos(origin_latitude_rad)
    points = []
    for sample in valid_samples:
        latitude_rad = math.radians(sample.latitude_deg)
        longitude_rad = math.radians(sample.longitude_deg)
        points.append(
            LocalGnssPoint(
                timestamp_analysis_ms=sample.timestamp_analysis_ms,
                x_m=(
                    EARTH_RADIUS_M
                    * (longitude_rad - origin_longitude_rad)
                    * cosine_origin_latitude
                ),
                y_m=EARTH_RADIUS_M * (latitude_rad - origin_latitude_rad),
            )
        )
    return tuple(points)


def _sample_has_valid_coordinates(sample: GnssSample) -> bool:
    latitude = sample.latitude_deg
    longitude = sample.longitude_deg
    return (
        latitude is not None
        and longitude is not None
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90.0 <= latitude <= 90.0
        and -180.0 <= longitude <= 180.0
    )
