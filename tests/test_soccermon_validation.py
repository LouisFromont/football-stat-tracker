"""The real-data audit must reject changed native values and untrusted files."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HAS_ARROW = importlib.util.find_spec("pyarrow") is not None
if HAS_ARROW:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from football_stat_tracker.importers.soccermon import IMU_COLUMNS, import_soccermon_session
    spec = importlib.util.spec_from_file_location(
        "validate_soccermon_imports", Path(__file__).resolve().parents[1] / "scripts/validate_soccermon_imports.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)


@unittest.skipUnless(HAS_ARROW, "Requires pyarrow")
class ImportValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "example.parquet"
        pq.write_table(pa.table({
            "player_name": ["player"] * 2, "time": ["10:00:00.0"] * 2,
            "lat": [59.] * 2, "lon": [10.] * 2,
            **{n: [0., 1.] for n in IMU_COLUMNS},
        }), self.path)

    def test_audit_detects_modified_native_sensor_value(self):
        session = import_soccermon_session(self.path)
        audit.verify_native_rows(self.path, session)
        sample = session.imu[1]
        altered = replace(sample, raw_source=replace(sample.raw_source, values=(99., *sample.raw_source.values[1:])))
        session = replace(session, imu=(session.imu[0], altered))
        with self.assertRaisesRegex(ValueError, "Native value changed at row 1, column accl_x"):
            audit.verify_native_rows(self.path, session)

    def test_manifest_hash_mismatch_stops_before_import(self):
        manifest = self.root / "manifest.json"
        output = self.root / "summary.json"
        manifest.write_text(json.dumps({"sessions": [{"extracted_path": str(self.path), "sha256": "wrong"}]}))
        with patch("sys.argv", ["audit", "--manifest", str(manifest), "--output", str(output)]), \
                patch.object(audit, "import_soccermon_session") as importer:
            with self.assertRaisesRegex(ValueError, "Manifest checksum mismatch"):
                audit.main()
            importer.assert_not_called()
        self.assertFalse(output.exists())
        self.assertEqual(audit.sha256(self.path), hashlib.sha256(self.path.read_bytes()).hexdigest())
