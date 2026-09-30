"""Meaningful cadence, anomaly-preservation and plot aggregation tests."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES=all(importlib.util.find_spec(n) for n in ['pyarrow','numpy','matplotlib'])
if DEPENDENCIES:
    sys.path.insert(0,str(ROOT/'scripts'))
    import analyze_soccermon_subset as audit
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    sys.path.pop(0)

@unittest.skipUnless(DEPENDENCIES,'Requires project-local analysis dependencies')
class SensorAuditTests(unittest.TestCase):
    def test_time_parser_does_not_guess_or_roll_over(self):
        self.assertEqual(audit.parse_time_ms('09:07:39.7'),32859700)
        self.assertEqual(audit.parse_time_ms('00:00:00.001'),1)
        for value in [None,'2020-01-01T10:00:00','25:00:00','12:00:00.0001','12:00:00+01:00']:
            with self.assertRaises(ValueError):audit.parse_time_ms(value)
        r=audit.interval_profile(np.array([86399900,0,0,100]))
        self.assertEqual(r['negative_intervals'],1)
        self.assertEqual(r['adjacent_duplicates'],1)

    def test_display_envelope_retains_finite_peak_and_missing_bin(self):
        x,low,median,high=audit.envelopes(np.array([0,100,1000,11000]),np.array([1.,99.,2.,np.nan]))
        self.assertEqual(high[0],99.)
        self.assertEqual(median[0],2.)
        self.assertTrue(np.isnan(high[1]))

    def test_shared_timestamp_does_not_discard_imu_or_hide_gnss_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'example.parquet'
            columns={n:[1.,1.,1.,1.] for n in audit.GNSS+['heart_rate','inst_acc_impulse']+[prefix+a for prefix in ['accl_','gyro_'] for a in 'xyz']}
            columns.update(time=['10:00:00.0','10:00:00.0','10:00:00.1','10:00:00.1'],
                           player_name=['TeamB-a']*4,lat=[59.,59.1,0.,0.],lon=[10.,10.,0.,0.],
                           accl_x=[0.,10.,0.,2.])
            pq.write_table(pa.table(columns),path)
            entry={'extracted_path':str(path),'sha256':audit.hashes(path)['sha256'],'date':'2020-01-01','player_filename_id':'a'}
            r,ms,arrays,index,accel,gyro=audit.inspect_session(entry)
            self.assertEqual(r['rows'],4)
            self.assertEqual(r['row_intervals']['adjacent_duplicates'],2)
            self.assertEqual(r['gnss_tuple_changes_within_equal_timestamp'],1)
            self.assertEqual(r['suspicious_counts']['zero_coordinate_pairs'],2)
            self.assertEqual(len(accel),4)
            self.assertGreater(accel.max(),10.)
            self.assertEqual(len(index),2)
            self.assertEqual(pq.read_table(path)['lat'].to_pylist(),[59.,59.1,0.,0.])
            entry['sha256']='wrong'
            with self.assertRaises(ValueError):audit.inspect_session(entry)

if __name__=='__main__':unittest.main()
