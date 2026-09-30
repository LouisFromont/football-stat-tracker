"""Auditable robust distance estimation for GNSS tracks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from football_stat_tracker.data_model import GnssSample
from football_stat_tracker.gnss import total_gnss_distance_m
from football_stat_tracker.gnss_diagnostics import gnss_segment_diagnostics


class SegmentDecision(str, Enum):
    ACCEPTED = "accepted"
    ACCEPTED_GAP_CHORD = "accepted_gap_chord"
    REJECTED_IMPLAUSIBLE_SPEED = "rejected_implausible_speed"
    REJECTED_NON_POSITIVE_TIME = "rejected_non_positive_time"
    REJECTED_INVALID_TIME = "rejected_invalid_time"


@dataclass(frozen=True, slots=True)
class RobustGnssConfig:
    """Configurable, ground-truth-independent physical rules."""

    # 15 m/s = 54 km/h: deliberately above plausible elite human sprinting,
    # so the rule catches only clearly non-human point-to-point motion.
    max_speed_mps: float = 15.0
    # 30 s is an outage boundary, not a model of motion. It is far beyond the
    # expected smartphone GNSS cadence while remaining well below multi-minute
    # gaps; no distance is reconstructed within such an interval.
    gap_threshold_s: float = 30.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_speed_mps) or self.max_speed_mps <= 0.0:
            raise ValueError("max_speed_mps must be finite and positive")
        if not math.isfinite(self.gap_threshold_s) or self.gap_threshold_s <= 0.0:
            raise ValueError("gap_threshold_s must be finite and positive")


@dataclass(frozen=True, slots=True)
class RobustSegmentAssessment:
    start_index: int
    end_index: int
    start_timestamp_analysis_ms: float
    end_timestamp_analysis_ms: float
    delta_t_s: float
    distance_m: float
    geometric_speed_mps: float | None
    is_gap: bool
    decision: SegmentDecision
    start_horizontal_accuracy_m: float | None
    end_horizontal_accuracy_m: float | None


@dataclass(frozen=True, slots=True)
class RobustGnssDistanceResult:
    raw_distance_m: float
    estimated_distance_m: float
    observed_non_gap_distance_m: float
    uncertain_distance_m: float
    rejected_distance_m: float
    total_segments: int
    accepted_segments: int
    rejected_segments: int
    rejected_implausible_speed_count: int
    rejected_non_positive_time_count: int
    rejected_invalid_time_count: int
    gap_count: int
    total_gap_duration_s: float
    segment_assessments: tuple[RobustSegmentAssessment, ...]

    @property
    def rejection_reasons(self) -> dict[str, int]:
        """Return non-zero rejection counts keyed by auditable reason."""

        counts = {
            SegmentDecision.REJECTED_IMPLAUSIBLE_SPEED.value: (
                self.rejected_implausible_speed_count
            ),
            SegmentDecision.REJECTED_NON_POSITIVE_TIME.value: (
                self.rejected_non_positive_time_count
            ),
            SegmentDecision.REJECTED_INVALID_TIME.value: (
                self.rejected_invalid_time_count
            ),
        }
        return {reason: count for reason, count in counts.items() if count}

    @property
    def gap_durations_s(self) -> tuple[float, ...]:
        """Return each detected gap duration, in track order."""

        return tuple(
            segment.delta_t_s for segment in self.segment_assessments if segment.is_gap
        )

    @property
    def gap_endpoint_distances_m(self) -> tuple[float, ...]:
        """Return each gap's endpoint chord, without implying a travelled path."""

        return tuple(
            segment.distance_m for segment in self.segment_assessments if segment.is_gap
        )

    # Compatibility aliases for the initial V0A.9 prototype names.
    @property
    def accepted_distance_m(self) -> float:
        return self.estimated_distance_m

    @property
    def gap_chord_distance_m(self) -> float:
        return self.uncertain_distance_m

    @property
    def analyzed_segment_count(self) -> int:
        return self.total_segments

    @property
    def accepted_segment_count(self) -> int:
        return self.accepted_segments

    @property
    def rejected_segment_count(self) -> int:
        return self.rejected_segments


def estimate_robust_gnss_distance(
    samples: tuple[GnssSample, ...] | list[GnssSample],
    config: RobustGnssConfig | None = None,
) -> RobustGnssDistanceResult:
    """Estimate distance while rejecting only physically impossible segments.

    A segment whose positive-time geometric speed exceeds ``max_speed_mps`` is
    rejected. A segment longer than ``gap_threshold_s`` in time is explicitly
    marked as a gap. If its speed remains physically plausible, its endpoint
    chord contributes to ``estimated_distance_m`` but is also reported in full
    as ``uncertain_distance_m``. This chord is only observed displacement: it
    does not reconstruct, interpolate, or claim to know the travelled path
    during the outage.

    Horizontal accuracy is recorded in each assessment for audit purposes but
    is not used as a rejection rule.
    """

    active_config = config or RobustGnssConfig()
    raw_distance = total_gnss_distance_m(samples)
    accepted_distance = 0.0
    observed_non_gap_distance = 0.0
    gap_chord_distance = 0.0
    rejected_distance = 0.0
    accepted_count = 0
    rejected_count = 0
    rejected_speed_count = 0
    rejected_time_count = 0
    rejected_invalid_time_count = 0
    gap_count = 0
    total_gap_duration = 0.0
    assessments = []

    for segment in gnss_segment_diagnostics(samples):
        time_is_finite = math.isfinite(segment.delta_t_s)
        is_gap = (
            time_is_finite
            and segment.delta_t_s > active_config.gap_threshold_s
        )
        if is_gap:
            gap_count += 1
            total_gap_duration += segment.delta_t_s

        if not time_is_finite:
            decision = SegmentDecision.REJECTED_INVALID_TIME
            rejected_distance += segment.distance_m
            rejected_count += 1
            rejected_invalid_time_count += 1
        elif segment.delta_t_s <= 0.0:
            decision = SegmentDecision.REJECTED_NON_POSITIVE_TIME
            rejected_distance += segment.distance_m
            rejected_count += 1
            rejected_time_count += 1
        elif (
            segment.geometric_speed_mps is not None
            and segment.geometric_speed_mps > active_config.max_speed_mps
        ):
            decision = SegmentDecision.REJECTED_IMPLAUSIBLE_SPEED
            rejected_distance += segment.distance_m
            rejected_count += 1
            rejected_speed_count += 1
        elif is_gap:
            decision = SegmentDecision.ACCEPTED_GAP_CHORD
            accepted_distance += segment.distance_m
            gap_chord_distance += segment.distance_m
            accepted_count += 1
        else:
            decision = SegmentDecision.ACCEPTED
            accepted_distance += segment.distance_m
            observed_non_gap_distance += segment.distance_m
            accepted_count += 1

        assessments.append(
            RobustSegmentAssessment(
                start_index=segment.start_index,
                end_index=segment.end_index,
                start_timestamp_analysis_ms=segment.start_timestamp_analysis_ms,
                end_timestamp_analysis_ms=segment.end_timestamp_analysis_ms,
                delta_t_s=segment.delta_t_s,
                distance_m=segment.distance_m,
                geometric_speed_mps=segment.geometric_speed_mps,
                is_gap=is_gap,
                decision=decision,
                start_horizontal_accuracy_m=segment.start_horizontal_accuracy_m,
                end_horizontal_accuracy_m=segment.end_horizontal_accuracy_m,
            )
        )

    return RobustGnssDistanceResult(
        raw_distance_m=raw_distance,
        estimated_distance_m=accepted_distance,
        observed_non_gap_distance_m=observed_non_gap_distance,
        uncertain_distance_m=gap_chord_distance,
        rejected_distance_m=rejected_distance,
        total_segments=len(assessments),
        accepted_segments=accepted_count,
        rejected_segments=rejected_count,
        rejected_implausible_speed_count=rejected_speed_count,
        rejected_non_positive_time_count=rejected_time_count,
        rejected_invalid_time_count=rejected_invalid_time_count,
        gap_count=gap_count,
        total_gap_duration_s=total_gap_duration,
        segment_assessments=tuple(assessments),
    )
