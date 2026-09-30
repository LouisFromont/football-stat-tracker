import unittest

from football_stat_tracker.data_model import (
    ImuSample, RawSensorSample, SessionMetadata, TrackingSession,
)


class SourcePreservationTests(unittest.TestCase):
    def test_no_ground_truth_and_repeated_imu_times_are_representable(self):
        metadata = SessionMetadata("example", "player", "recording", 100, 100,
                                   None, None, None, None, None, None)
        samples = tuple(
            ImuSample(100, 0, None, None, None, None, None, None, None, None, None,
                      RawSensorSample(i, 1, "00:00:00.1", ("accl_x",), (i,)))
            for i in range(2)
        )
        session = TrackingSession(metadata, (), samples)
        self.assertIsNone(session.ground_truth)
        self.assertIsNone(session.metadata.gt_type)
        self.assertEqual([s.raw_source.source_row_index for s in session.imu], [0, 1])
        self.assertEqual([s.raw_source.get("accl_x") for s in session.imu], [0, 1])
        self.assertIsNone(session.imu[0].raw_source.get("absent"))


if __name__ == "__main__":
    unittest.main()
