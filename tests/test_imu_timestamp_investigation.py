"""Scientific counting and source-order diagnostics on small synthetic sequences."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

DEPENDENCIES = all(importlib.util.find_spec(n) for n in ("numpy", "pyarrow"))
if DEPENDENCIES:
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    spec = importlib.util.spec_from_file_location(
        "imu_timestamp_audit", Path(__file__).resolve().parents[1] / "scripts/investigate_soccermon_imu_timestamps.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)


@unittest.skipUnless(DEPENDENCIES, "Requires project-local numpy and pyarrow")
class ImuTimestampInvestigationTests(unittest.TestCase):
    def vectors(self, x):
        return np.column_stack((x, np.zeros(len(x)), np.zeros(len(x))))

    def test_ten_row_groups_and_independent_sensor_identity(self):
        times = np.repeat([1000, 1100], 10)
        accel = self.vectors(np.arange(20))
        gyro = np.ones((20, 3))
        result = audit.analyze_imu_arrays(times, accel, gyro)
        self.assertEqual(result["clock"]["rows_per_distinct_timestamp_distribution"], {"10": 2})
        self.assertEqual(result["clock"]["exactly_ten_group_percent"], 100)
        a, g = result["accelerometer"], result["gyroscope"]
        self.assertEqual(a["identity"]["varying_multirow_group_count"], 2)
        self.assertEqual(g["identity"]["identical_multirow_group_count"], 2)
        self.assertEqual(g["identity"]["consecutive_identical_vector_count"], 19)
        self.assertEqual(g["identity"]["maximum_identical_finite_vector_run_rows"], 20)
        self.assertEqual(a["pairs"]["within_group"]["pair_count"], 18)
        self.assertEqual(a["pairs"]["within_group"]["difference_norm"]["median"], 1)
        self.assertEqual(a["pairs"]["boundary_100ms"]["difference_norm"]["median"], 1)
        self.assertEqual(a["boundary100ms_to_within_median_norm_ratio"], 1)
        self.assertEqual(a["full_ten_row_group_pair_ordinals"]["1"]["pair_count"], 2)
        self.assertEqual(a["full_ten_row_group_pair_ordinals"]["boundary"]["pair_count"], 1)
        self.assertEqual(result["combined_six_axis_identity"]["consecutive_identical_vector_count"], 0)
        self.assertNotIn("difference_norm", result["combined_six_axis_identity"])

    def test_middle_pair_pattern_is_reported_without_interpreting_it_as_timing(self):
        times = np.repeat([0, 100], 10)
        values = self.vectors(np.r_[np.arange(5), np.arange(7, 12), np.arange(12, 17), np.arange(19, 24)])
        result = audit.analyze_imu_arrays(times, values, values)
        sensor = result["accelerometer"]
        self.assertEqual(sensor["middle_pair_to_other_within_median_ratio"], 3)
        self.assertEqual(sensor["full_ten_row_group_pair_ordinals"]["5"]["difference_norm"]["median"], 3)
        self.assertEqual(sensor["pairs"]["within_group"]["difference_norm"]["median"], 1)
        np.testing.assert_array_equal(times, np.repeat([0, 100], 10))

    def test_distinct_timestamp_multiplicity_is_separate_from_contiguous_groups(self):
        times = np.array([0, 0, 100, 0, 0], dtype=np.uint64)
        original = times.copy()
        starts, sizes, clock = audit.timestamp_groups(times)
        self.assertEqual(starts.tolist(), [0, 2, 3])
        self.assertEqual(sizes.tolist(), [2, 1, 2])
        self.assertEqual(clock["rows_per_distinct_timestamp_distribution"], {"1": 1, "4": 1})
        self.assertEqual(clock["contiguous_group_size_distribution"], {"1": 1, "2": 2})
        self.assertEqual(clock["noncontiguous_timestamp_recurrences"], 1)
        self.assertEqual(clock["timestamp_reversal_count"], 1)
        self.assertIsNone(clock["elapsed_stored_span_s"])
        np.testing.assert_array_equal(times, original)

    def test_within_boundary_and_gap_differences_are_not_divided_by_assumed_time(self):
        result = audit.analyze_imu_arrays(np.array([0, 0, 100, 100, 400]),
                                         self.vectors([0, 1, 9, 10, 30]), self.vectors([1, 1, 1, 1, 1]))
        pairs = result["accelerometer"]["pairs"]
        self.assertEqual(pairs["within_group"]["difference_norm"]["median"], 1)
        self.assertEqual(pairs["boundary_100ms"]["difference_norm"]["median"], 8)
        self.assertEqual(pairs["boundary_gap_over100ms"]["difference_norm"]["median"], 20)
        self.assertEqual(result["clock"]["gap_over_100ms_count"], 1)
        self.assertEqual(result["clock"]["absent_grid_bins_if_100ms_grid"], 2)
        self.assertEqual(pairs["within_group"]["signed_axis_differences"]["x"]["median"], 1)

    def test_partial_edges_and_irregular_interior_groups_are_explicit(self):
        _, _, clock = audit.timestamp_groups(np.repeat([0, 100, 200, 300], [5, 10, 7, 4]))
        self.assertEqual(clock["first_group_size"], 5)
        self.assertEqual(clock["last_group_size"], 4)
        self.assertTrue(clock["first_group_partial_relative_to_ten"])
        self.assertTrue(clock["last_group_partial_relative_to_ten"])
        self.assertEqual(clock["interior_non_ten_group_count"], 1)
        self.assertEqual(clock["exactly_ten_group_percent"], 25)

    def test_null_nan_infinity_vectors_are_unclassifiable_instead_of_identical(self):
        times = np.array([0, 0, 100, 100, 200])
        accel = self.vectors([0, 0, np.nan, np.inf, 1])
        result = audit.analyze_imu_arrays(times, accel, self.vectors([1, 1, 1, 1, 1]))
        identity = result["accelerometer"]["identity"]
        self.assertEqual(identity["unclassifiable_group_count"], 1)
        self.assertEqual(identity["identical_multirow_group_count"], 1)
        self.assertEqual(identity["singleton_group_count"], 1)
        self.assertEqual(identity["consecutive_finite_pair_count"], 1)
        self.assertEqual(result["accelerometer"]["pairs"]["all_consecutive"]["nonfinite_pair_count"], 3)
        json.dumps(result, allow_nan=False)
        all_null = audit.analyze_imu_arrays(np.array([0, 0]), [[None] * 3] * 2, [[None] * 3] * 2)
        self.assertIsNone(all_null["combined_six_axis_identity"]["identical_group_percent"])

    def test_single_sample_and_constant_clock_do_not_imply_frequency(self):
        result = audit.analyze_imu_arrays(np.array([0]), self.vectors([1]), self.vectors([1]))
        self.assertIsNone(result["clock"]["observed_export_row_density_rows_s"])
        self.assertIsNone(result["accelerometer"]["pairs"]["within_group"]["difference_norm"]["median"])
        self.assertIsNone(result["accelerometer"]["identity"]["identical_group_percent"])
        for times in [np.array([], dtype=int), np.array([.5]), np.array([86400000]), np.array([-1]), np.array([[1]])]:
            with self.assertRaises(ValueError):
                audit.timestamp_groups(times)
        with self.assertRaisesRegex(ValueError, "three-axis"):
            audit.analyze_imu_arrays(np.array([0]), [[1, 2]], [[1, 2, 3]])

    def test_counterfactual_span_is_a_scalar_and_nonuniform_grid_is_not_repaired(self):
        _, _, clock = audit.timestamp_groups(np.array([0, 0, 100, 100]))
        self.assertEqual(clock["stored_span_minus_uniform_100rows_s_span_ms"], 70)
        _, _, clock = audit.timestamp_groups(np.array([0, 95, 310]))
        self.assertEqual(clock["off_100ms_grid_group_count"], 2)
        self.assertIsNone(clock["absent_grid_bins_if_100ms_grid"])
        self.assertEqual(clock["contiguous_group_interval_counts_ms"], {"95": 1, "215": 1})

    def test_parquet_audit_reads_only_imu_clock_and_preserves_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sensor.parquet"
            # A location field exists, but it must not enter the aggregate output.
            table = pa.table({"time": ["00:00:00.0", "00:00:00.0", "00:00:00.1"],
                              **{n: [0., 1., 2.] for n in audit.IMU_COLUMNS}, "lat": [59.] * 3})
            pq.write_table(table, path)
            import hashlib
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result = audit.inspect_recording({"extracted_path": str(path), "sha256": digest})
            self.assertTrue(result["source_hash_unchanged"])
            self.assertEqual(result["clock"]["source_rows"], 3)
            self.assertNotIn("player_name", result)
            self.assertNotIn("59.0", json.dumps(result))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                audit.inspect_recording({"extracted_path": str(path), "sha256": "wrong"})
