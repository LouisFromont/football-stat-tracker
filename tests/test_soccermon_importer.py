"""Small real Parquet fixtures exercising import semantics and lossless ordering."""
from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from football_stat_tracker.data_model import GnssPositionStatus
from football_stat_tracker.gnss import total_gnss_distance_m
from football_stat_tracker.importers.soccermon import (
    IMU_COLUMNS, REQUIRED_COLUMNS, SoccerMonImportError,
    import_soccermon_session, parse_soccermon_time_ms, summarize_soccermon_session,
)

HAS_ARROW = importlib.util.find_spec("pyarrow") is not None
if HAS_ARROW:
    import pyarrow as pa
    import pyarrow.parquet as pq


def fixture(count=4):
    return {
        "player_name": ["TeamB-player"] * count,
        "time": [f"10:00:00.{i // 2}" for i in range(count)],
        "lat": [59.0] * count, "lon": [10.0] * count,
        "speed": [0.0] * count, "hacc": [0] * count, "hdop": [2] * count,
        "signal_quality": [300] * count, "num_satellites": [18] * count,
        "heart_rate": [0] * count, "inst_acc_impulse": [1.0] * count,
        **{name: [float(i) / 4 for i in range(count)] for name in IMU_COLUMNS},
    }


class TimestampParsingTests(unittest.TestCase):
    def test_millisecond_precision_is_exact_and_original_representation_is_not_guessed(self):
        for text, ms in [("00:00:00", 0), ("00:00:00.1", 100),
                         ("00:00:00.01", 10), ("00:00:00.001", 1),
                         ("23:59:59.999", 86399999)]:
            self.assertEqual(parse_soccermon_time_ms(text), ms)
        for text in [None, 12, "24:00:00", "10:60:00", "10:00:60", "1:00:00",
                     "10:00:00.0001", "10:00:00Z", "2020-01-01T10:00:00", ""]:
            with self.subTest(text=text), self.assertRaises(SoccerMonImportError):
                parse_soccermon_time_ms(text)


@unittest.skipUnless(HAS_ARROW, "Requires pyarrow for Parquet fixtures")
class SoccerMonImporterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, columns=None, name="2020-06-17-TeamB-player.parquet", metadata=None,
              row_group_size=None):
        path = self.root / name
        table = pa.table(columns if columns is not None else fixture())
        if metadata is not None:
            table = table.replace_schema_metadata(metadata)
        pq.write_table(table, path, row_group_size=row_group_size)
        return path

    def load(self, columns=None, **kwargs):
        return import_soccermon_session(self.write(columns, **kwargs))

    def test_valid_streams_preserve_identity_native_values_and_metadata(self):
        path = self.write(metadata={b"recording_note": b"original bytes"})
        session = import_soccermon_session(path)
        self.assertEqual(session.metadata.subject_id, "TeamB-player")
        self.assertEqual(session.metadata.recording_id, path.stem)
        self.assertEqual(session.metadata.provenance.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(session.metadata.provenance.source_path, str(path.resolve()))
        self.assertIn((b"recording_note", b"original bytes"), session.metadata.provenance.source_metadata)
        self.assertIn(("recording_date_from_filename", "2020-06-17"), session.metadata.provenance.context)
        self.assertEqual(session.gnss[0].latitude_deg, 59)
        self.assertEqual(session.gnss[0].speed_mps, 0)
        self.assertEqual(session.imu[3].raw_source.get("accl_x"), .75)
        self.assertEqual(session.imu[3].raw_source.get("gyro_z"), .75)
        self.assertIsNone(session.imu[3].accel_x_mps2)
        self.assertIsNone(session.imu[3].accel_including_gravity_x_mps2)
        self.assertIsNone(session.imu[3].rot_rate_alpha)

    def test_no_ground_truth_or_measured_frequency_is_invented(self):
        session = self.load()
        for value in [session.ground_truth, session.metadata.gt_type,
                      session.metadata.distance_reference_m, session.metadata.fs_acc_hz,
                      session.metadata.fs_gnss_hz, session.gnss[0].horizontal_accuracy_m]:
            self.assertIsNone(value)
        self.assertIsNone(summarize_soccermon_session(session)["independently_identifiable_gnss_fixes"])

    def test_repeated_timestamps_preserve_all_imu_rows_and_order(self):
        session = self.load()
        self.assertEqual(len(session.imu), 4)
        self.assertEqual([s.timestamp_analysis_ms for s in session.imu], [0, 0, 100, 100])
        self.assertEqual([s.raw_source.source_row_index for s in session.imu], list(range(4)))
        self.assertTrue(all(s.raw_source.source_row_count == 1 for s in session.imu))
        self.assertEqual([s.raw_source.timestamp_original for s in session.imu], fixture()["time"])

    def test_stationary_player_retains_candidates_at_different_times(self):
        session = self.load()
        self.assertEqual(len(session.gnss), 2)
        self.assertEqual([s.raw_source.source_row_count for s in session.gnss], [2, 2])
        self.assertEqual([s.raw_source.source_row_index for s in session.gnss], [0, 2])
        self.assertEqual(total_gnss_distance_m(session.gnss), 0)
        self.assertTrue(all(s.observation_kind == "timestamp_group_candidate" for s in session.gnss))

    def test_conflicting_gnss_values_at_one_time_are_not_dropped(self):
        columns = fixture()
        columns["lat"] = [59., 59.1, 59., 59.]
        session = self.load(columns)
        self.assertEqual(len(session.gnss), 3)
        summary = summarize_soccermon_session(session)
        self.assertEqual(summary["groups_with_multiple_candidates"], 1)
        self.assertEqual(sum(s.raw_source.source_row_count for s in session.gnss), 4)

    def test_gnss_quality_and_auxiliary_changes_are_preserved(self):
        for name in ["hacc", "hdop", "signal_quality", "num_satellites", "heart_rate", "inst_acc_impulse", "speed"]:
            columns = fixture()
            columns[name][1] += 1
            with self.subTest(column=name):
                session = self.load(columns)
                self.assertEqual(len(session.gnss), 3)
                self.assertEqual(session.gnss[1].raw_source.get(name), columns[name][1])

    def test_nonconsecutive_values_in_same_group_are_not_globally_deduplicated(self):
        columns = fixture()
        columns["time"] = ["10:00:00.0"] * 4
        columns["lat"] = [59., 60., 59., 59.]
        session = self.load(columns)
        self.assertEqual([s.raw_source.source_row_count for s in session.gnss], [1, 1, 2])

    def test_signed_zero_and_nan_exports_are_conservatively_preserved(self):
        columns = fixture()
        columns["speed"] = [0., -0., math.nan, math.nan]
        session = self.load(columns)
        self.assertEqual(len(session.gnss), 4)
        self.assertEqual(math.copysign(1, session.gnss[1].raw_source.get("speed")), -1)
        self.assertTrue(math.isnan(session.gnss[2].raw_source.get("speed")))

    def test_invalid_positions_remain_raw_and_are_unusable_in_existing_pipeline(self):
        examples = [(0., 0., GnssPositionStatus.ZERO_PAIR),
                    (91., 10., GnssPositionStatus.OUT_OF_RANGE),
                    (59., 181., GnssPositionStatus.OUT_OF_RANGE),
                    (math.nan, 10., GnssPositionStatus.NON_FINITE),
                    (59., math.inf, GnssPositionStatus.NON_FINITE),
                    (None, 10., GnssPositionStatus.MISSING)]
        for lat, lon, status in examples:
            with self.subTest(status=status, lat=lat):
                columns = fixture()
                columns["lat"][2:] = [lat, lat]
                columns["lon"][2:] = [lon, lon]
                session = self.load(columns)
                candidate = session.gnss[-1]
                self.assertEqual(candidate.position_status, status)
                self.assertIsNone(candidate.latitude_deg)
                self.assertIsNone(candidate.longitude_deg)
                if lat is not None and math.isnan(lat):
                    self.assertTrue(math.isnan(candidate.raw_source.get("lat")))
                else:
                    self.assertEqual(candidate.raw_source.get("lat"), lat)
                self.assertEqual(total_gnss_distance_m(session.gnss), 0)
                self.assertEqual(summarize_soccermon_session(session)["invalid_coordinate_source_rows"], 2)

    def test_single_zero_axis_and_poor_quality_do_not_invalidate_numeric_position(self):
        columns = fixture()
        columns["lat"] = [0.] * 4
        columns["num_satellites"] = [0] * 4
        columns["hacc"] = [-1] * 4
        session = self.load(columns)
        self.assertEqual(session.gnss[0].position_status, GnssPositionStatus.USABLE)
        self.assertEqual(session.gnss[0].raw_source.get("hacc"), -1)

    def test_missing_optional_columns_and_null_measurements_remain_distinguishable(self):
        columns = {name: values for name, values in fixture().items() if name in REQUIRED_COLUMNS}
        columns["accl_x"] = [None] * 4
        session = self.load(columns)
        self.assertIsNone(session.gnss[0].speed_mps)
        self.assertNotIn("hacc", session.gnss[0].raw_source.columns)
        self.assertIn("accl_x", session.imu[0].raw_source.columns)
        self.assertIsNone(session.imu[0].raw_source.get("accl_x"))

    def test_nan_null_infinity_and_negative_sensor_values_are_not_filtered(self):
        columns = fixture()
        columns["accl_x"] = [None, math.nan, math.inf, -100.]
        columns["speed"] = [-2., -2., math.inf, math.inf]
        session = self.load(columns)
        self.assertIsNone(session.imu[0].raw_source.get("accl_x"))
        self.assertTrue(math.isnan(session.imu[1].raw_source.get("accl_x")))
        self.assertEqual(session.imu[2].raw_source.get("accl_x"), math.inf)
        self.assertEqual(session.imu[3].raw_source.get("accl_x"), -100.)
        self.assertEqual(session.gnss[0].speed_mps, -2.)
        self.assertEqual(session.gnss[1].speed_mps, math.inf)

    def test_each_missing_required_column_has_clear_error(self):
        for name in REQUIRED_COLUMNS:
            columns = fixture()
            del columns[name]
            with self.subTest(name=name), self.assertRaisesRegex(SoccerMonImportError, "Missing required.*" + name):
                self.load(columns)

    def test_wrong_types_and_unknown_fields_are_rejected_without_coercion(self):
        for name, values in [("lat", ["59"] * 4), ("hacc", [True] * 4),
                             ("time", [123] * 4), ("player_name", [12] * 4),
                             ("gyro_z", [[1.]] * 4)]:
            columns = fixture()
            columns[name] = values
            with self.subTest(name=name), self.assertRaisesRegex(SoccerMonImportError, "Invalid type"):
                self.load(columns)
        columns = fixture()
        columns["new_sensor"] = [1.] * 4
        with self.assertRaisesRegex(SoccerMonImportError, "Unsupported columns"):
            self.load(columns)

    def test_null_identity_or_timestamp_and_malformed_times_report_row(self):
        for name, value in [("time", None), ("time", "24:00:00"),
                            ("player_name", None), ("player_name", " ")]:
            columns = fixture()
            columns[name][1] = value
            with self.subTest(name=name, value=value), self.assertRaisesRegex(SoccerMonImportError, "source row 1"):
                self.load(columns)

    def test_nonmonotonic_times_preserve_order_and_withhold_duration(self):
        columns = fixture()
        columns["time"] = ["10:00:00.2", "10:00:00.1", "10:00:00.1", "10:00:00.2"]
        session = self.load(columns)
        self.assertEqual([s.timestamp_analysis_ms for s in session.imu], [100, 0, 0, 100])
        summary = summarize_soccermon_session(session)
        self.assertEqual(summary["backwards_timestamp_intervals"], 1)
        self.assertEqual(summary["duplicate_timestamp_rows"], 2)
        self.assertEqual(summary["contiguous_timestamp_groups"], 3)
        self.assertEqual(len(session.gnss), 3)
        self.assertIsNone(summary["duration_s"])

    def test_possible_midnight_crossing_is_not_unwrapped(self):
        columns = fixture(2)
        columns["time"] = ["23:59:59.9", "00:00:00.0"]
        session = self.load(columns)
        self.assertEqual([s.timestamp_raw_ms for s in session.imu], [86399900, 0])
        self.assertIsNone(summarize_soccermon_session(session)["duration_s"])

    def test_different_source_time_spellings_are_preserved(self):
        columns = fixture(2)
        columns["time"] = ["10:00:00.1", "10:00:00.100"]
        session = self.load(columns)
        self.assertEqual(len(session.gnss), 2)
        self.assertEqual([s.raw_source.timestamp_original for s in session.imu], columns["time"])

    def test_multiple_players_in_one_file_rejected_and_separate_sessions_supported(self):
        columns = fixture()
        columns["player_name"][2:] = ["TeamB-other"] * 2
        with self.assertRaisesRegex(SoccerMonImportError, "Multiple players"):
            self.load(columns)
        first = self.load()
        second = self.load(name="2020-08-27-TeamB-player.parquet")
        columns["player_name"] = ["TeamB-other"] * 4
        third = self.load(columns, name="2020-08-27-TeamB-other.parquet")
        self.assertNotEqual(first.metadata.recording_id, second.metadata.recording_id)
        self.assertEqual(first.metadata.subject_id, second.metadata.subject_id)
        self.assertNotEqual(second.metadata.subject_id, third.metadata.subject_id)

    def test_filename_identity_and_calendar_date_are_validated_when_present(self):
        with self.assertRaisesRegex(SoccerMonImportError, "identity mismatch"):
            self.load(name="2020-06-17-TeamB-other.parquet")
        with self.assertRaisesRegex(SoccerMonImportError, "Invalid recording date"):
            self.load(name="2020-02-30-TeamB-player.parquet")
        session = self.load(name="arbitrary.parquet")
        self.assertNotIn("recording_date_from_filename", dict(session.metadata.provenance.context))

    def test_batch_and_row_group_boundaries_do_not_change_deduplication(self):
        path = self.write(row_group_size=1)
        with patch("football_stat_tracker.importers.soccermon.BATCH_SIZE", 1):
            session = import_soccermon_session(path)
        self.assertEqual(len(session.gnss), 2)
        self.assertEqual([s.raw_source.source_row_count for s in session.gnss], [2, 2])

    def test_all_known_columns_can_be_reconstructed_for_each_original_row(self):
        columns = fixture()
        columns["lat"][1] = 59.1
        session = self.load(columns)
        reconstructed = [dict(player_name=session.metadata.subject_id) for _ in session.imu]
        for sample in (*session.gnss, *session.imu):
            raw = sample.raw_source
            for i in range(raw.source_row_index, raw.source_row_index + raw.source_row_count):
                reconstructed[i].update(zip(raw.columns, raw.values))
                reconstructed[i]["time"] = raw.timestamp_original
        self.assertEqual(reconstructed, [dict(zip(columns, row)) for row in zip(*columns.values())])

    def test_summary_counts_source_rows_candidates_duplicates_and_intervals(self):
        summary = summarize_soccermon_session(self.load())
        self.assertEqual(summary["source_rows"], 4)
        self.assertEqual(summary["imu_samples"], 4)
        self.assertEqual(summary["gnss_candidates"], 2)
        self.assertEqual(summary["duplicate_timestamp_rows"], 2)
        self.assertEqual(summary["source_interval_counts_ms"], {0: 2, 100: 1})
        self.assertEqual(summary["duration_s"], .1)

    def test_empty_corrupt_absent_and_duplicate_column_files_have_clear_errors(self):
        columns = {n: pa.array([], type=pa.string() if n in ["time", "player_name"] else pa.float64())
                   for n in REQUIRED_COLUMNS}
        with self.assertRaisesRegex(SoccerMonImportError, "Empty"):
            self.load(columns)
        path = self.root / "corrupt.parquet"
        path.write_bytes(b"invalid")
        for file in [path, self.root / "absent.parquet"]:
            with self.assertRaisesRegex(SoccerMonImportError, "Cannot read"):
                import_soccermon_session(file)
        path = self.root / "duplicate.parquet"
        table = pa.table(fixture())
        table = table.append_column("lat", table["lat"])
        pq.write_table(table, path)
        with self.assertRaisesRegex(SoccerMonImportError, "Duplicate"):
            import_soccermon_session(path)


if __name__ == "__main__":
    unittest.main()
