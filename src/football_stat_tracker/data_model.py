"""Source-independent data model used by Football Stat Tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GroundTruthType(str, Enum):
    CONTINUOUS = "continuous"
    FINAL = "final"


class GroundTruthAlignment(str, Enum):
    EXACT_AT_TEST_START = "exact_at_test_start"
    INTERPOLATED_AT_TEST_START = "interpolated_at_test_start"
    ASSUMED_ZERO_AT_TEST_START = "assumed_zero_at_test_start"
    NOT_ALIGNED_TO_TEST_START = "not_aligned_to_test_start"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    source: str
    subject_id: str
    recording_id: str
    test_start_raw_ms: float
    test_end_raw_ms: float
    gt_type: GroundTruthType
    distance_reference_m: float | None
    device: str | None
    fs_acc_hz: float | None
    fs_gnss_hz: float | None
    path_curvature: int | None


@dataclass(frozen=True, slots=True)
class GnssSample:
    timestamp_raw_ms: float
    timestamp_analysis_ms: float
    latitude_deg: float | None
    longitude_deg: float | None
    altitude_m: float | None
    speed_mps: float | None
    heading_deg: float | None
    horizontal_accuracy_m: float | None


@dataclass(frozen=True, slots=True)
class ImuSample:
    timestamp_raw_ms: float
    timestamp_analysis_ms: float
    accel_x_mps2: float | None
    accel_y_mps2: float | None
    accel_z_mps2: float | None
    accel_including_gravity_x_mps2: float | None
    accel_including_gravity_y_mps2: float | None
    accel_including_gravity_z_mps2: float | None
    # Axis correspondence and units are intentionally not inferred from the
    # Walking dataset's alpha/beta/gamma labels.
    rot_rate_alpha: float | None
    rot_rate_beta: float | None
    rot_rate_gamma: float | None


@dataclass(frozen=True, slots=True)
class GroundTruthSample:
    timestamp_raw_ms: float
    timestamp_analysis_ms: float
    distance_raw_m: float
    distance_analysis_m: float | None


@dataclass(frozen=True, slots=True)
class ContinuousGroundTruth:
    samples: tuple[GroundTruthSample, ...]
    alignment: GroundTruthAlignment
    type: GroundTruthType = field(default=GroundTruthType.CONTINUOUS, init=False)


@dataclass(frozen=True, slots=True)
class FinalGroundTruth:
    distance_final_m: float | None
    alignment: GroundTruthAlignment = field(
        default=GroundTruthAlignment.NOT_APPLICABLE, init=False
    )
    type: GroundTruthType = field(default=GroundTruthType.FINAL, init=False)


GroundTruth = ContinuousGroundTruth | FinalGroundTruth


@dataclass(frozen=True, slots=True)
class TrackingSession:
    metadata: SessionMetadata
    gnss: tuple[GnssSample, ...]
    imu: tuple[ImuSample, ...]
    ground_truth: GroundTruth
