from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from football_stat_tracker.data_model import (
    ContinuousGroundTruth,
    FinalGroundTruth,
    GroundTruthAlignment,
    GroundTruthType,
)
from football_stat_tracker.importers.walking import import_walking_session


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REAL_SESSION = REPOSITORY_ROOT / "data/raw/walking/data/subject_14/14_2"
WALKING_DATA = REPOSITORY_ROOT / "data/raw/walking/data"


class WalkingImporterRealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = import_walking_session(REAL_SESSION)

    def test_reads_test_window_and_identifiers_from_source(self) -> None:
        with (REAL_SESSION / "events.csv").open(newline="") as events_file:
            event = next(csv.DictReader(events_file))
        with (WALKING_DATA / "metadata_tracks.csv").open(newline="") as metadata_file:
            metadata_row = next(
                row
                for row in csv.DictReader(metadata_file)
                if row["testName"] == REAL_SESSION.name
            )

        self.assertEqual(
            self.session.metadata.test_start_raw_ms, float(event["testStart"])
        )
        self.assertEqual(self.session.metadata.test_end_raw_ms, float(event["testEnd"]))
        self.assertEqual(self.session.metadata.subject_id, REAL_SESSION.parent.name)
        self.assertEqual(self.session.metadata.recording_id, REAL_SESSION.name)
        self.assertEqual(self.session.metadata.gt_type, GroundTruthType.CONTINUOUS)
        self.assertEqual(self.session.metadata.device, metadata_row["device"])
        self.assertEqual(
            self.session.metadata.distance_reference_m,
            float(metadata_row["distanceReference"]),
        )
        self.assertEqual(self.session.metadata.fs_acc_hz, float(metadata_row["fs_acc"]))
        self.assertEqual(
            self.session.metadata.fs_gnss_hz, float(metadata_row["fs_gnss"])
        )
        self.assertEqual(
            self.session.metadata.path_curvature,
            int(metadata_row["path curvature"]),
        )

    def test_each_stream_is_sorted_and_inside_test_window(self) -> None:
        start = self.session.metadata.test_start_raw_ms
        end = self.session.metadata.test_end_raw_ms

        self.assertIsInstance(self.session.ground_truth, ContinuousGroundTruth)
        for stream in (self.session.gnss, self.session.imu):
            raw_timestamps = [sample.timestamp_raw_ms for sample in stream]
            self.assertEqual(raw_timestamps, sorted(raw_timestamps))
            self.assertTrue(all(start <= timestamp <= end for timestamp in raw_timestamps))

        ground_truth_timestamps = [
            sample.timestamp_raw_ms for sample in self.session.ground_truth.samples
        ]
        self.assertEqual(ground_truth_timestamps, sorted(ground_truth_timestamps))
        self.assertTrue(
            all(start <= timestamp <= end for timestamp in ground_truth_timestamps)
        )

    def test_analysis_timestamps_use_test_start_as_origin(self) -> None:
        start = self.session.metadata.test_start_raw_ms

        self.assertIsInstance(self.session.ground_truth, ContinuousGroundTruth)
        for stream in (
            self.session.gnss,
            self.session.imu,
            self.session.ground_truth.samples,
        ):
            self.assertGreater(len(stream), 0)
            self.assertGreaterEqual(stream[0].timestamp_analysis_ms, 0.0)
            for sample in stream:
                self.assertEqual(
                    sample.timestamp_analysis_ms, sample.timestamp_raw_ms - start
                )

        self.assertEqual(self.session.gnss[0].timestamp_analysis_ms, 0.0)
        self.assertEqual(
            self.session.ground_truth.samples[0].timestamp_analysis_ms, 0.0
        )

    def test_ground_truth_is_rebased_at_interpolated_test_start(self) -> None:
        self.assertIsInstance(self.session.ground_truth, ContinuousGroundTruth)
        self.assertEqual(
            self.session.ground_truth.alignment,
            GroundTruthAlignment.INTERPOLATED_AT_TEST_START,
        )
        first = self.session.ground_truth.samples[0]
        self.assertEqual(first.timestamp_raw_ms, self.session.metadata.test_start_raw_ms)
        self.assertAlmostEqual(first.distance_analysis_m, 0.0)

        for sample in self.session.ground_truth.samples:
            self.assertAlmostEqual(
                sample.distance_analysis_m,
                sample.distance_raw_m - first.distance_raw_m,
            )


class WalkingImporterMultiSessionTests(unittest.TestCase):
    EXPECTED_ALIGNMENTS = {
        "subject_14/14_2": GroundTruthAlignment.INTERPOLATED_AT_TEST_START,
        "subject_14/14_6": GroundTruthAlignment.NOT_ALIGNED_TO_TEST_START,
        "subject_16/16_2": GroundTruthAlignment.INTERPOLATED_AT_TEST_START,
        "subject_17/17_0": GroundTruthAlignment.ASSUMED_ZERO_AT_TEST_START,
        "subject_18/18_0": GroundTruthAlignment.INTERPOLATED_AT_TEST_START,
    }

    def test_six_real_sessions_import_with_typed_ground_truth(self) -> None:
        for relative_path, expected_alignment in self.EXPECTED_ALIGNMENTS.items():
            with self.subTest(session=relative_path):
                session = import_walking_session(WALKING_DATA / relative_path)
                self.assertGreater(len(session.gnss), 0)
                self.assertGreater(len(session.imu), 0)
                self.assertEqual(session.metadata.gt_type, GroundTruthType.CONTINUOUS)
                self.assertIsInstance(session.ground_truth, ContinuousGroundTruth)
                self.assertEqual(session.ground_truth.type, GroundTruthType.CONTINUOUS)
                self.assertEqual(session.ground_truth.alignment, expected_alignment)
                self.assertGreater(len(session.ground_truth.samples), 0)

        final_session = import_walking_session(WALKING_DATA / "subject_8/8_4")
        self.assertGreater(len(final_session.gnss), 0)
        self.assertGreater(len(final_session.imu), 0)
        self.assertEqual(final_session.metadata.gt_type, GroundTruthType.FINAL)
        self.assertIsInstance(final_session.ground_truth, FinalGroundTruth)
        self.assertEqual(final_session.ground_truth.type, GroundTruthType.FINAL)
        self.assertEqual(
            final_session.ground_truth.alignment,
            GroundTruthAlignment.NOT_APPLICABLE,
        )
        self.assertIsNotNone(final_session.ground_truth.distance_final_m)
        self.assertEqual(
            final_session.ground_truth.distance_final_m,
            final_session.metadata.distance_reference_m,
        )

    def test_unaligned_continuous_distance_is_not_artificially_rebased(self) -> None:
        session = import_walking_session(WALKING_DATA / "subject_14/14_6")
        self.assertIsInstance(session.ground_truth, ContinuousGroundTruth)
        self.assertGreater(session.ground_truth.samples[0].timestamp_analysis_ms, 0.0)
        self.assertGreater(session.ground_truth.samples[0].distance_raw_m, 0.0)
        self.assertTrue(
            all(
                sample.distance_analysis_m is None
                for sample in session.ground_truth.samples
            )
        )

    def test_zero_first_distance_can_define_test_start_origin(self) -> None:
        session = import_walking_session(WALKING_DATA / "subject_17/17_0")
        self.assertIsInstance(session.ground_truth, ContinuousGroundTruth)
        first = session.ground_truth.samples[0]
        self.assertEqual(first.timestamp_analysis_ms, 0.0)
        self.assertEqual(first.distance_raw_m, 0.0)
        self.assertEqual(first.distance_analysis_m, 0.0)


class WalkingImporterGeneralizationTests(unittest.TestCase):
    def test_imports_another_window_without_recording_specific_constants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            session_path = Path(temporary_directory) / "subject_custom" / "trial_custom"
            session_path.mkdir(parents=True)
            self._write_synthetic_session(session_path)

            session = import_walking_session(session_path)

        self.assertEqual(session.metadata.subject_id, "subject_custom")
        self.assertEqual(session.metadata.recording_id, "trial_custom")
        self.assertEqual(session.metadata.test_start_raw_ms, 100.0)
        self.assertEqual(session.metadata.test_end_raw_ms, 300.0)
        self.assertEqual(
            [sample.timestamp_raw_ms for sample in session.gnss],
            [100.0, 200.0, 300.0],
        )
        self.assertIsNone(session.gnss[1].latitude_deg)
        self.assertIsNone(session.gnss[1].horizontal_accuracy_m)
        self.assertIsNone(session.gnss[1].speed_mps)
        self.assertIsNone(session.gnss[1].heading_deg)
        self.assertEqual(
            [sample.timestamp_raw_ms for sample in session.imu], [110.0, 250.0]
        )
        self.assertIsInstance(session.ground_truth, ContinuousGroundTruth)
        self.assertEqual(
            [sample.timestamp_raw_ms for sample in session.ground_truth.samples],
            [100.0, 150.0, 250.0],
        )
        self.assertAlmostEqual(session.ground_truth.samples[0].distance_raw_m, 15.0)
        self.assertAlmostEqual(
            session.ground_truth.samples[0].distance_analysis_m, 0.0
        )
        self.assertAlmostEqual(
            session.ground_truth.samples[-1].distance_analysis_m, 15.0
        )
        self.assertIsNone(session.imu[0].accel_x_mps2)
        self.assertIsNone(session.imu[0].rot_rate_gamma)

    @staticmethod
    def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
        with path.open("w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(header)
            writer.writerows(rows)

    @classmethod
    def _write_synthetic_session(cls, path: Path) -> None:
        cls._write_csv(
            path.parent.parent / "metadata_tracks.csv",
            [
                "testName",
                "distanceReference",
                "device",
                "fs_acc",
                "fs_gnss",
                "path curvature",
                "gt_type",
            ],
            [["trial_custom", 30, "Test device", 50, 1, 2, "continuous"]],
        )
        cls._write_csv(
            path / "events.csv",
            ["", "signalStart", "testStart", "testEnd"],
            [[0, 0, 100, 300]],
        )
        cls._write_csv(
            path / "positions.csv",
            [
                "",
                "ms",
                "latitude",
                "longitude",
                "altitude",
                "confInterval",
                "heading",
                "speed",
            ],
            [
                [0, 300, 1.3, 2.3, 3.3, 4.3, 90, 2],
                [1, 50, 1.0, 2.0, 3.0, 4.0, 90, 2],
                [2, 200, "", 2.2, 3.2, "", "", ""],
                [3, 100, 1.1, 2.1, 3.1, 4.1, 90, 2],
            ],
        )
        cls._write_csv(
            path / "motion.csv",
            [
                "",
                "ms",
                "accelX",
                "accelY",
                "accelZ",
                "accelWithGX",
                "accelWithGY",
                "accelWithGZ",
                "rotRateAlpha",
                "rotRateBeta",
                "rotRateGamma",
                "interval",
            ],
            [
                [0, 250, 1, 2, 3, 4, 5, 6, 7, 8, 9, 16],
                [1, 301, 1, 2, 3, 4, 5, 6, 7, 8, 9, 16],
                [2, 110, "", 2, 3, 4, 5, 6, 7, 8, "", 16],
            ],
        )
        cls._write_csv(
            path / "reference_cont_distance.csv",
            ["", "ms", "distance"],
            [[0, 250, 30], [1, 50, 10], [2, 350, 40], [3, 150, 20]],
        )
