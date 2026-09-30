"""Validate the existing selected subset, including every imported native value.

Reads only manifest-selected Parquet files. Writes small aggregate JSON without
coordinates, raw measurements or reconstructed timestamps. No dataset download.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import struct

import pyarrow.parquet as pq

from football_stat_tracker.importers.soccermon import (
    import_soccermon_session, summarize_soccermon_session,
)


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def native_equal(a, b):
    if isinstance(a, float) and isinstance(b, float):
        if a == 0 or math.isnan(a):
            return struct.pack(">d", a) == struct.pack(">d", b)
    return a == b


def verify_native_rows(path, session):
    """Expand GNSS row ranges and check all 17 known columns against source."""
    gnss_index = 0
    row_index = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=32768):
        columns = {n: batch.column(n).to_pylist() for n in batch.schema.names}
        for i in range(batch.num_rows):
            imu = session.imu[row_index]
            while row_index >= (session.gnss[gnss_index].raw_source.source_row_index
                                + session.gnss[gnss_index].raw_source.source_row_count):
                gnss_index += 1
            gnss = session.gnss[gnss_index]
            if (imu.raw_source.source_row_index != row_index
                    or imu.raw_source.source_row_count != 1
                    or gnss.raw_source.source_row_index > row_index
                    or columns["player_name"][i] != session.metadata.subject_id):
                raise ValueError(f"Source identity or row coverage changed at row {row_index}")
            for sample in (imu, gnss):
                raw = sample.raw_source
                if (raw.timestamp_original != columns["time"][i]
                        or sample.timestamp_raw_ms != imu.timestamp_raw_ms):
                    raise ValueError(f"Source timestamp changed at row {row_index}")
                for name, value in zip(raw.columns, raw.values):
                    if not native_equal(value, columns[name][i]):
                        raise ValueError(f"Native value changed at row {row_index}, column {name}")
            row_index += 1
    if (row_index != session.metadata.provenance.source_row_count
            or row_index != len(session.imu)
            or sum(s.raw_source.source_row_count for s in session.gnss) != row_index):
        raise ValueError("Source row coverage/count mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=Path("outputs/v0b1_soccermon_inventory/extracted_manifest.json"))
    parser.add_argument("--output", type=Path,
                        default=Path("outputs/v0b2_soccermon_importer/validation_summary.json"))
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text())["sessions"]
    results = []
    for i, entry in enumerate(entries, 1):
        path = Path(entry["extracted_path"])
        expected = entry["sha256"]
        if sha256(path) != expected:
            raise ValueError(f"Manifest checksum mismatch: {path}")
        session = import_soccermon_session(path)
        if session.metadata.provenance.sha256 != expected:
            raise ValueError(f"Importer checksum mismatch: {path}")
        verify_native_rows(path, session)
        if sha256(path) != expected:
            raise ValueError(f"Source changed during validation: {path}")
        result = summarize_soccermon_session(session)
        result.update(session_label=f"S{i}", sha256=expected,
                      native_rows_verified=True, source_hash_unchanged=True)
        results.append(result)
        print(json.dumps({k: result[k] for k in ["session_label", "source_rows", "imu_samples",
                         "gnss_candidates", "invalid_coordinate_source_rows", "duration_s"]}), flush=True)
        del session
        gc.collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "session_count": len(results), "total_source_rows": sum(r["source_rows"] for r in results),
        "total_imu_samples": sum(r["imu_samples"] for r in results),
        "total_gnss_candidates": sum(r["gnss_candidates"] for r in results),
        "scope": "Every source row/value; no movement metrics or physical frequency claims",
        "sessions": results,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
