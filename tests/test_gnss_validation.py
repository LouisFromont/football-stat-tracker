from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

from football_stat_tracker.data_model import GnssSample, RawSensorSample, SessionMetadata, TrackingSession
from football_stat_tracker.gnss_robust import estimate_robust_gnss_distance
from football_stat_tracker.gnss_validation import build_candidate_series, integrate_vendor_speed


def sample(time=0, lat=59., lon=10., speed=2., row=0, quality=1):
    return GnssSample(time, time, lat, lon, None, speed, None, None,
                      raw_source=RawSensorSample(row, 10, str(time),
                                                 ("lat", "lon", "speed", "hdop"),
                                                 (lat, lon, speed, quality)))


class CandidateSeriesTests(unittest.TestCase):
    def test_stationary_coordinates_at_new_times_are_retained_without_claiming_fixes(self):
        source = (sample(0), sample(100, row=10), sample(200, row=20))
        series = build_candidate_series(source)
        self.assertEqual(series.samples, source)
        self.assertTrue(all(a is b for a, b in zip(source, series.samples)))
        self.assertEqual(series.source_indices, ((0,), (1,), (2,)))
        self.assertEqual(series.break_before, (False, False, False))

    def test_identical_same_time_exports_keep_all_original_indices_and_row_provenance(self):
        source = (sample(0), sample(0, row=10), sample(100, row=20))
        series = build_candidate_series(source)
        self.assertEqual(len(series.samples), 2)
        self.assertEqual(series.source_indices, ((0, 1), (2,)))
        self.assertEqual(series.exclusions, ((1, "equivalent_timestamp_export"),))
        self.assertEqual(series.duplicate_time_groups, 1)
        self.assertEqual(source[1].raw_source.source_row_index, 10)

    def test_conflicts_quarantine_whole_group_and_break_continuity(self):
        for changed in (sample(100, lat=59.1), sample(100, speed=3), sample(100, quality=2)):
            source = (sample(0), sample(100), changed, sample(200))
            series = build_candidate_series(source)
            self.assertEqual([s.timestamp_raw_ms for s in series.samples], [0, 200])
            self.assertEqual(series.conflicting_time_groups, 1)
            self.assertEqual(series.break_before, (False, True))
            self.assertEqual(len(series.exclusions), 2)

    def test_invalid_coordinates_are_excluded_without_mutation_and_break_links(self):
        for lat, lon in ((0., 0.), (None, 10.), (math.nan, 10.), (91., 10.), (59., math.inf)):
            source = (sample(0), sample(100, lat, lon), sample(200))
            series = build_candidate_series(source)
            self.assertEqual(len(series.samples), 2)
            self.assertIs(source[1].latitude_deg, lat)
            self.assertEqual(series.exclusions, ((1, "invalid_coordinates"),))
            self.assertEqual(series.break_before, (False, True))

    def test_a_single_zero_coordinate_axis_remains_valid(self):
        self.assertEqual(len(build_candidate_series((sample(lat=0), sample(100, lon=0))).samples), 2)

    def test_clock_reversals_and_midnight_are_refused_without_sorting(self):
        for source in ((sample(200), sample(100)), (sample(86399900), sample(0))):
            with self.assertRaisesRegex(ValueError, "reversal"):
                build_candidate_series(source)

    def test_nonfinite_or_inconsistent_clocks_are_refused(self):
        for source in ((sample(math.nan),), (sample(math.inf),),
                       (sample(0), replace(sample(100), timestamp_analysis_ms=90))):
            with self.assertRaises(ValueError):
                build_candidate_series(source)

    def test_empty_singleton_and_all_invalid_views_have_no_invented_intervals(self):
        for source in ((), (sample(),), (sample(lat=0, lon=0),)):
            series = build_candidate_series(source)
            result = integrate_vendor_speed(series)
            self.assertEqual(result.distance_m, 0)
            self.assertEqual(result.total_link_duration_s, 0)
            self.assertEqual(result.eligible, ())

    def test_original_time_text_and_nonzero_origin_are_preserved(self):
        first = replace(sample(123400), timestamp_analysis_ms=0)
        second = replace(sample(123500), timestamp_analysis_ms=100)
        series = build_candidate_series((first, second))
        self.assertEqual(series.samples[0].raw_source.timestamp_original, "123400")
        self.assertEqual(series.samples[1].timestamp_raw_ms, 123500)
        self.assertAlmostEqual(integrate_vendor_speed(series).distance_m, .2)

    def test_equal_parsed_times_do_not_overwrite_distinct_original_text(self):
        a, b = sample(), sample(row=10)
        a = replace(a, raw_source=replace(a.raw_source, timestamp_original="10:00:00.0"))
        b = replace(b, raw_source=replace(b.raw_source, timestamp_original="10:00:00.00"))
        series = build_candidate_series((a, b))
        self.assertEqual(series.source_indices, ((0, 1),))
        self.assertEqual(a.raw_source.timestamp_original, "10:00:00.0")
        self.assertEqual(b.raw_source.timestamp_original, "10:00:00.00")


class VendorIntegrationTests(unittest.TestCase):
    def test_left_right_trapezoidal_use_actual_irregular_intervals_and_no_endpoint_extension(self):
        series = build_candidate_series((sample(0, speed=2), sample(100, speed=4), sample(300, speed=8)))
        for convention, expected in (("left", 1.), ("right", 2.), ("trapezoidal", 1.5)):
            result = integrate_vendor_speed(series, max_interval_s=.2, convention=convention)
            self.assertAlmostEqual(result.distance_m, expected)
            self.assertAlmostEqual(result.supported_duration_s, .3)
            self.assertEqual(result.eligible, (True, True))

    def test_gaps_are_flagged_and_excluded_with_duration_accounting(self):
        series = build_candidate_series((sample(0), sample(100), sample(1000), sample(1100)))
        result = integrate_vendor_speed(series)
        self.assertAlmostEqual(result.distance_m, .4)
        self.assertEqual(result.reasons, ("supported", "clock_gap", "supported"))
        self.assertAlmostEqual(result.total_link_duration_s, 1.1)
        self.assertAlmostEqual(result.supported_duration_s, .2)

    def test_quarantined_coordinates_break_support_even_with_a_permissive_gap_limit(self):
        series = build_candidate_series((sample(0), sample(100, 0, 0), sample(200)))
        result = integrate_vendor_speed(series, max_interval_s=30)
        self.assertEqual(result.distance_m, 0)
        self.assertEqual(result.reasons, ("excluded_candidate_between_endpoints",))
        self.assertEqual(estimate_robust_gnss_distance(series.samples).accepted_segments, 1)

    def test_missing_negative_and_nonfinite_speeds_break_both_neighboring_links(self):
        for bad in (None, -1., math.nan, math.inf):
            series = build_candidate_series((sample(0), sample(100, speed=bad), sample(200)))
            result = integrate_vendor_speed(series)
            self.assertEqual(result.reasons, ("unusable_vendor_speed",) * 2)
            self.assertEqual(result.distance_m, 0)

    def test_zero_speed_is_valid_and_stationary_coordinates_do_not_invalidate_vendor_speed(self):
        for speed, distance in ((0., 0.), (2., .2)):
            series = build_candidate_series((sample(0, speed=speed), sample(100, speed=speed)))
            result = integrate_vendor_speed(series)
            self.assertEqual(result.eligible, (True,))
            self.assertAlmostEqual(result.distance_m, distance)
            self.assertEqual(estimate_robust_gnss_distance(series.samples).raw_distance_m, 0)

    def test_implausible_geometry_does_not_silently_filter_the_vendor_integral(self):
        series = build_candidate_series((sample(0), sample(100, lat=59.1)))
        self.assertEqual(estimate_robust_gnss_distance(series.samples).estimated_distance_m, 0)
        self.assertAlmostEqual(integrate_vendor_speed(series).distance_m, .2)

    def test_invalid_configuration_and_malformed_series_are_refused(self):
        series = build_candidate_series((sample(0), sample(100)))
        for value in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                integrate_vendor_speed(series, max_interval_s=value)
        with self.assertRaises(ValueError):
            integrate_vendor_speed(series, convention="guessed")
        with self.assertRaises(ValueError):
            integrate_vendor_speed(replace(series, samples=(sample(100), sample(0))))


@unittest.skipUnless(importlib.util.find_spec("pyarrow"), "Requires existing Parquet environment")
class AnalysisScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/validate_soccermon_gnss.py"
        spec = importlib.util.spec_from_file_location("v0b3_validation", path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_common_support_and_cumulative_totals_reconcile_without_bridging_vendor_gaps(self):
        samples = (sample(0), sample(100, lat=59.000001), sample(200, 0, 0),
                   sample(300, lat=59.000003), sample(1000, lat=59.000005), sample(1100, lat=59.1))
        metadata = SessionMetadata("soccermon", "synthetic", "synthetic", 0, 1100,
                                   None, None, None, None, None, None)
        session = TrackingSession(metadata, samples, ())
        summary, arrays, _, _ = self.script.evaluate_session(session, "synthetic")
        self.assertEqual(arrays["common"].tolist(), [True, False, False, True])
        self.assertEqual(summary["links_crossing_excluded_groups"], 1)
        self.assertEqual(summary["robust_rejected_links"], 1)
        self.assertAlmostEqual(summary["vendor_supported_duration_s"], .2)
        self.assertAlmostEqual(summary["vendor_left_m"], .4)
        self.assertLess(summary["robust_common_input_m"], .12)
        self.assertGreater(summary["raw_common_input_m"], 10000)
        for array, field in (("raw_cumulative", "raw_haversine_m"),
                             ("robust_cumulative", "robust_m"), ("vendor_cumulative", "vendor_left_m")):
            self.assertAlmostEqual(arrays[array][-1], summary[field])

    def test_two_parquet_recordings_produce_separate_supported_totals_and_unchanged_hashes(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = []
            for i, speed in enumerate((2., 4.)):
                identity = f"TeamB-player{i}"
                path = root / f"2020-06-17-{identity}.parquet"
                columns = {"player_name": [identity] * 6, "time": ["10:00:00.0"] * 2 + ["10:00:00.1"] * 2 + ["10:00:00.4"] * 2,
                           "lat": [59.] * 6, "lon": [10.] * 6, "speed": [speed] * 6,
                           **{p+a: list(range(6)) for p in ("accl_", "gyro_") for a in "xyz"}}
                pq.write_table(pa.table(columns), path)
                entries.append({"extracted_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sessions": entries}))
            output = root / "out"
            payload = self.script.main(["--manifest", str(manifest), "--output", str(output), "--no-plots"])
            self.assertEqual(len(payload["sessions"]), 2)
            for i, summary in enumerate(payload["sessions"]):
                self.assertEqual(summary["imu_samples_preserved"], 6)
                self.assertEqual(summary["retained_candidates"], 3)
                self.assertEqual(summary["raw_haversine_m"], 0)
                self.assertAlmostEqual(summary["vendor_left_m"], (.2, .4)[i])
                self.assertAlmostEqual(summary["vendor_coverage_percent"], 25)
                self.assertIsNone(summary["independently_identifiable_fixes"])
                self.assertTrue(summary["source_hash_unchanged"])
                self.assertEqual(hashlib.sha256(Path(entries[i]["extracted_path"]).read_bytes()).hexdigest(), entries[i]["sha256"])
            self.assertTrue((output / "comparison.csv").exists())
            self.assertNotIn('"lat"', (output / "validation_summary.json").read_text())

    def test_manifest_hash_mismatch_stops_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "file.parquet"
            source.write_bytes(b"not a dataset")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sessions": [{"extracted_path": str(source), "sha256": "wrong"}]}))
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.script.main(["--manifest", str(manifest), "--output", str(root / "out"), "--no-plots"])
