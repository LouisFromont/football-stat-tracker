from __future__ import annotations

import unittest

from football_stat_tracker.data_model import GnssSample
from football_stat_tracker.gnss import haversine_distance_m, total_gnss_distance_m


def gnss_sample(
    latitude_deg: float | None, longitude_deg: float | None
) -> GnssSample:
    return GnssSample(
        timestamp_raw_ms=0.0,
        timestamp_analysis_ms=0.0,
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=None,
        speed_mps=None,
        heading_deg=None,
        horizontal_accuracy_m=None,
    )


class HaversineDistanceTests(unittest.TestCase):
    def test_identical_points_have_zero_distance(self) -> None:
        self.assertEqual(haversine_distance_m(48.8566, 2.3522, 48.8566, 2.3522), 0.0)

    def test_one_degree_of_longitude_at_equator(self) -> None:
        self.assertAlmostEqual(
            haversine_distance_m(0.0, 0.0, 0.0, 1.0),
            111_194.9266,
            places=3,
        )

    def test_distance_is_symmetric(self) -> None:
        forward = haversine_distance_m(48.8566, 2.3522, 51.5074, -0.1278)
        backward = haversine_distance_m(51.5074, -0.1278, 48.8566, 2.3522)
        self.assertAlmostEqual(forward, backward)


class TotalGnssDistanceTests(unittest.TestCase):
    def test_sums_a_small_multi_point_trajectory(self) -> None:
        samples = [
            gnss_sample(0.0, 0.0),
            gnss_sample(0.0, 1.0),
            gnss_sample(0.0, 2.0),
        ]
        self.assertAlmostEqual(
            total_gnss_distance_m(samples),
            2.0 * 111_194.9266,
            places=3,
        )

    def test_fewer_than_two_valid_points_return_zero(self) -> None:
        self.assertEqual(total_gnss_distance_m([]), 0.0)
        self.assertEqual(total_gnss_distance_m([gnss_sample(1.0, 2.0)]), 0.0)
        self.assertEqual(
            total_gnss_distance_m(
                [gnss_sample(None, 2.0), gnss_sample(1.0, None)]
            ),
            0.0,
        )

    def test_missing_coordinates_are_skipped_without_using_zero(self) -> None:
        samples = [
            gnss_sample(0.0, 1.0),
            gnss_sample(None, None),
            gnss_sample(0.0, 2.0),
        ]
        self.assertAlmostEqual(
            total_gnss_distance_m(samples),
            111_194.9266,
            places=3,
        )

    def test_out_of_range_coordinates_are_skipped(self) -> None:
        samples = [
            gnss_sample(0.0, 1.0),
            gnss_sample(91.0, 1.5),
            gnss_sample(0.0, 2.0),
        ]
        self.assertAlmostEqual(
            total_gnss_distance_m(samples),
            111_194.9266,
            places=3,
        )
