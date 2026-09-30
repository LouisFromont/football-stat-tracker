from __future__ import annotations

import math
import unittest

from football_stat_tracker.data_model import GnssSample
from football_stat_tracker.gnss import total_gnss_distance_m
from football_stat_tracker.gnss_diagnostics import (
    calculate_distance_error,
    cumulative_gnss_distance,
    gnss_segment_diagnostics,
    local_gnss_coordinates,
    summarize_horizontal_accuracy,
    summarize_segments,
)


def sample(
    timestamp_ms: float,
    latitude: float | None,
    longitude: float | None,
    accuracy: float | None = None,
) -> GnssSample:
    return GnssSample(
        timestamp_raw_ms=timestamp_ms,
        timestamp_analysis_ms=timestamp_ms,
        latitude_deg=latitude,
        longitude_deg=longitude,
        altitude_m=None,
        speed_mps=None,
        heading_deg=None,
        horizontal_accuracy_m=accuracy,
    )


class GnssDiagnosticTests(unittest.TestCase):
    def test_distance_error_is_signed_and_relative(self) -> None:
        error = calculate_distance_error(110.0, 100.0)
        self.assertEqual(error.signed_m, 10.0)
        self.assertEqual(error.relative_percent, 10.0)

    def test_cumulative_distance_matches_total_raw_distance(self) -> None:
        samples = [
            sample(0.0, 0.0, 0.0),
            sample(1000.0, None, None),
            sample(2000.0, 0.0, 1.0),
            sample(3000.0, 0.0, 2.0),
        ]
        cumulative = cumulative_gnss_distance(samples)
        self.assertEqual(len(cumulative), 3)
        self.assertEqual(cumulative[0].distance_m, 0.0)
        self.assertAlmostEqual(
            cumulative[-1].distance_m, total_gnss_distance_m(samples)
        )

    def test_segments_include_time_distance_and_geometric_speed(self) -> None:
        samples = [sample(0.0, 0.0, 0.0), sample(2000.0, 0.0, 1.0)]
        segment = gnss_segment_diagnostics(samples)[0]
        self.assertEqual(segment.delta_t_s, 2.0)
        self.assertAlmostEqual(segment.distance_m, 111_194.9266, places=3)
        self.assertAlmostEqual(
            segment.geometric_speed_mps, segment.distance_m / 2.0
        )

    def test_non_positive_time_interval_has_no_geometric_speed(self) -> None:
        segments = gnss_segment_diagnostics(
            [sample(1000.0, 0.0, 0.0), sample(1000.0, 0.0, 1.0)]
        )
        self.assertIsNone(segments[0].geometric_speed_mps)

    def test_segment_statistics_are_computed(self) -> None:
        segments = gnss_segment_diagnostics(
            [
                sample(0.0, 0.0, 0.0),
                sample(1000.0, 0.0, 1.0),
                sample(3000.0, 0.0, 2.0),
            ]
        )
        summary = summarize_segments(segments)
        self.assertEqual(summary.count, 2)
        self.assertEqual(summary.median_delta_t_s, 1.5)
        self.assertEqual(summary.maximum_delta_t_s, 2.0)

    def test_accuracy_summary_ignores_only_missing_and_non_finite_values(self) -> None:
        summary = summarize_horizontal_accuracy(
            [
                sample(0.0, 0.0, 0.0, 2.0),
                sample(1.0, 0.0, 0.0, None),
                sample(2.0, 0.0, 0.0, math.nan),
                sample(3.0, 0.0, 0.0, 4.0),
            ]
        )
        self.assertEqual(summary.count, 2)
        self.assertEqual(summary.median_m, 3.0)
        self.assertEqual(summary.mean_m, 3.0)
        self.assertEqual(summary.maximum_m, 4.0)

    def test_local_projection_uses_first_valid_point_as_origin(self) -> None:
        points = local_gnss_coordinates(
            [sample(0.0, None, None), sample(1.0, 0.0, 0.0), sample(2.0, 0.0, 1.0)]
        )
        self.assertEqual((points[0].x_m, points[0].y_m), (0.0, 0.0))
        self.assertAlmostEqual(points[1].x_m, 111_194.9266, places=3)
        self.assertAlmostEqual(points[1].y_m, 0.0)
