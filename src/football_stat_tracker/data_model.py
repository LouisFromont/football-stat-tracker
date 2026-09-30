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


class GnssPositionStatus(str, Enum):
    """Coordinate usability, not a guarantee of receiver accuracy/freshness."""

    USABLE = "usable"
    MISSING = "missing"
    NON_FINITE = "non_finite"
    OUT_OF_RANGE = "out_of_range"
    ZERO_PAIR = "zero_pair"


@dataclass(frozen=True, slots=True)
class RecordingProvenance:
    source_path: str
    sha256: str
    source_row_count: int
    source_columns: tuple[tuple[str, str], ...]
    source_metadata: tuple[tuple[bytes, bytes], ...]
    timestamp_basis: str
    context: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RawSensorSample:
    """Original values in source units and a contiguous zero-based row range.

    A range records repeated exports, never a count of independent fixes.
    Column names can be shared between samples; values retain nulls and NaNs.
    Source-specific units/semantics belong to the importer contract.
    """

    source_row_index: int
    source_row_count: int
    timestamp_original: str
    columns: tuple[str, ...]
    values: tuple[int | float | None, ...]

    def get(self, column: str) -> int | float | None:
        """Get a native value; inspect columns to distinguish absent from null."""
        return self.values[self.columns.index(column)] if column in self.columns else None


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    source: str
    subject_id: str
    recording_id: str
    test_start_raw_ms: float
    test_end_raw_ms: float
    gt_type: GroundTruthType | None
    distance_reference_m: float | None
    device: str | None
    fs_acc_hz: float | None
    fs_gnss_hz: float | None
    path_curvature: int | None
    provenance: RecordingProvenance | None = None


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
    raw_source: RawSensorSample | None = None
    position_status: GnssPositionStatus | None = None
    observation_kind: str | None = None


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
    # Native axes can be retained without asserting gravity inclusion or a
    # correspondence to Walking's alpha/beta/gamma fields.
    raw_source: RawSensorSample | None = None


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
    ground_truth: GroundTruth | None = None
