from __future__ import annotations

import math
import unittest

from football_stat_tracker.data_model import GnssSample
from football_stat_tracker.gnss_robust import (
    RobustGnssConfig,
    SegmentDecision,
    estimate_robust_gnss_distance,
)


def sample(timestamp_ms: float, latitude_deg: float, longitude_deg: float) -> GnssSample:
    return GnssSample(
        timestamp_raw_ms=timestamp_ms,
        timestamp_analysis_ms=timestamp_ms,
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=None,
        speed_mps=None,
        heading_deg=None,
        horizontal_accuracy_m=None,
    )


class RobustGnssDistanceTests(unittest.TestCase):
    def test_normal_trajectory_accepts_every_segment(self) -> None:
        samples = [
            sample(0.0, 0.0, 0.0),
            sample(1000.0, 0.00001, 0.0),
            sample(2000.0, 0.00002, 0.0),
        ]
        result = estimate_robust_gnss_distance(samples)
        self.assertEqual(result.total_segments, 2)
        self.assertEqual(result.accepted_segments, 2)
        self.assertEqual(result.rejected_segments, 0)
        self.assertAlmostEqual(result.estimated_distance_m, result.raw_distance_m)
        self.assertAlmostEqual(
            result.raw_distance_m,
            result.estimated_distance_m + result.rejected_distance_m,
        )

    def test_obvious_teleportation_is_rejected_by_speed(self) -> None:
        samples = [sample(0.0, 0.0, 0.0), sample(1000.0, 0.001, 0.0)]
        result = estimate_robust_gnss_distance(samples)
        self.assertEqual(result.rejected_implausible_speed_count, 1)
        self.assertEqual(result.estimated_distance_m, 0.0)
        self.assertAlmostEqual(result.rejected_distance_m, result.raw_distance_m)
        self.assertEqual(result.rejection_reasons, {"rejected_implausible_speed": 1})
        self.assertEqual(
            result.segment_assessments[0].decision,
            SegmentDecision.REJECTED_IMPLAUSIBLE_SPEED,
        )

    def test_fast_but_humanly_plausible_sprint_is_accepted(self) -> None:
        # About 12 m in one second: deliberately fast, but still below the
        # conservative 15 m/s anomaly threshold.
        samples = [sample(0.0, 0.0, 0.0), sample(1000.0, 0.000108, 0.0)]
        result = estimate_robust_gnss_distance(samples)
        segment = result.segment_assessments[0]
        self.assertGreater(segment.geometric_speed_mps, 10.0)
        self.assertLess(segment.geometric_speed_mps, 15.0)
        self.assertEqual(result.accepted_segments, 1)
        self.assertEqual(result.rejected_segments, 0)

    def test_large_gap_is_flagged_and_only_its_chord_is_retained(self) -> None:
        samples = [sample(0.0, 0.0, 0.0), sample(60_000.0, 0.003, 0.0)]
        result = estimate_robust_gnss_distance(samples)
        self.assertEqual(result.gap_count, 1)
        self.assertEqual(result.total_gap_duration_s, 60.0)
        self.assertEqual(result.rejected_segments, 0)
        self.assertAlmostEqual(result.uncertain_distance_m, result.raw_distance_m)
        self.assertAlmostEqual(result.estimated_distance_m, result.raw_distance_m)
        self.assertEqual(result.observed_non_gap_distance_m, 0.0)
        self.assertEqual(result.gap_durations_s, (60.0,))
        self.assertEqual(result.gap_endpoint_distances_m, (result.raw_distance_m,))
        self.assertEqual(
            result.segment_assessments[0].decision,
            SegmentDecision.ACCEPTED_GAP_CHORD,
        )

    def test_identical_points_are_accepted_with_zero_distance(self) -> None:
        samples = [sample(0.0, 1.0, 2.0), sample(1000.0, 1.0, 2.0)]
        result = estimate_robust_gnss_distance(samples)
        self.assertEqual(result.accepted_segments, 1)
        self.assertEqual(result.estimated_distance_m, 0.0)
        self.assertEqual(result.rejected_segments, 0)

    def test_zero_and_negative_timestamp_intervals_are_explicitly_rejected(self) -> None:
        for end_timestamp in (1000.0, 999.0):
            with self.subTest(end_timestamp=end_timestamp):
                samples = [
                    sample(1000.0, 0.0, 0.0),
                    sample(end_timestamp, 0.00001, 0.0),
                ]
                result = estimate_robust_gnss_distance(samples)
                self.assertEqual(result.rejected_non_positive_time_count, 1)
                self.assertEqual(result.estimated_distance_m, 0.0)
                self.assertEqual(
                    result.segment_assessments[0].decision,
                    SegmentDecision.REJECTED_NON_POSITIVE_TIME,
                )

    def test_non_finite_timestamp_interval_is_explicitly_rejected(self) -> None:
        samples = [sample(0.0, 0.0, 0.0), sample(math.nan, 0.00001, 0.0)]
        result = estimate_robust_gnss_distance(samples)
        self.assertEqual(result.rejected_invalid_time_count, 1)
        self.assertEqual(result.estimated_distance_m, 0.0)
        self.assertEqual(
            result.segment_assessments[0].decision,
            SegmentDecision.REJECTED_INVALID_TIME,
        )

    def test_configuration_requires_positive_thresholds(self) -> None:
        with self.assertRaises(ValueError):
            RobustGnssConfig(max_speed_mps=0.0)
        with self.assertRaises(ValueError):
            RobustGnssConfig(gap_threshold_s=0.0)
        with self.assertRaises(ValueError):
            RobustGnssConfig(max_speed_mps=math.nan)
        with self.assertRaises(ValueError):
            RobustGnssConfig(gap_threshold_s=math.inf)
