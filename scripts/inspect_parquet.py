"""Inspect Parquet metadata and optionally profile a bounded number of rows.

Requires ``pyarrow`` at runtime. The script makes no assumptions about column
names. A time column can be supplied explicitly to estimate sampling cadence.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections.abc import Iterable
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


def _load_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise SystemExit(
            "inspect_parquet.py requires pyarrow; install it in the project "
            "environment before inspecting SoccerMon Parquet files"
        ) from error
    return pa, pq


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _bounded_table(parquet_file: Any, max_rows: int) -> Any:
    tables = []
    remaining = max_rows
    for batch in parquet_file.iter_batches(batch_size=min(65_536, max_rows)):
        if remaining <= 0:
            break
        table = _load_pyarrow()[0].Table.from_batches([batch])
        bounded = table.slice(0, remaining)
        tables.append(bounded)
        remaining -= bounded.num_rows
    if not tables:
        pa, _ = _load_pyarrow()
        return pa.table({})
    pa, _ = _load_pyarrow()
    return pa.concat_tables(tables)


def _finite_numeric(values: Iterable[Any]) -> list[float]:
    return [
        float(value)
        for value in values
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]


def _column_profile(column: Any) -> dict[str, Any]:
    values = column.to_pylist()
    non_null = [value for value in values if value is not None]
    profile: dict[str, Any] = {
        "rows_profiled": len(values),
        "null_count": len(values) - len(non_null),
    }
    numeric = _finite_numeric(non_null)
    if numeric:
        profile.update(
            {
                "finite_numeric_count": len(numeric),
                "non_finite_numeric_count": len(non_null) - len(numeric),
                "minimum": min(numeric),
                "maximum": max(numeric),
            }
        )
    elif non_null:
        rendered = [_json_value(value) for value in non_null[:5]]
        profile["first_values"] = rendered
    return profile


def _time_to_seconds(value: Any, unit: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).timestamp()
    if isinstance(value, str):
        try:
            parsed = time.fromisoformat(value)
        except ValueError:
            return None
        return (
            parsed.hour * 3600.0
            + parsed.minute * 60.0
            + parsed.second
            + parsed.microsecond / 1_000_000.0
        )
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    scale = 0.001 if unit == "milliseconds" else 1.0
    return float(value) * scale


def _cadence_profile(column: Any, unit: str) -> dict[str, Any]:
    timestamps = [
        timestamp
        for value in column.to_pylist()
        if (timestamp := _time_to_seconds(value, unit)) is not None
    ]
    deltas = [right - left for left, right in zip(timestamps, timestamps[1:])]
    positive = [delta for delta in deltas if delta > 0.0]
    result: dict[str, Any] = {
        "valid_timestamp_count": len(timestamps),
        "duplicate_delta_count": sum(delta == 0.0 for delta in deltas),
        "negative_delta_count": sum(delta < 0.0 for delta in deltas),
    }
    if positive:
        median_delta = statistics.median(positive)
        result.update(
            {
                "median_positive_delta_s": median_delta,
                "estimated_frequency_hz": 1.0 / median_delta,
                "minimum_positive_delta_s": min(positive),
                "maximum_positive_delta_s": max(positive),
            }
        )
    return result


def inspect_parquet(
    path: Path,
    profile: bool = False,
    max_rows: int = 250_000,
    time_column: str | None = None,
    time_unit: str = "seconds",
) -> dict[str, Any]:
    """Return metadata and an optional bounded data profile."""

    _, pq = _load_pyarrow()
    parquet_file = pq.ParquetFile(path)
    metadata = parquet_file.metadata
    report: dict[str, Any] = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "rows": metadata.num_rows,
        "row_groups": metadata.num_row_groups,
        "created_by": metadata.created_by,
        "schema": str(parquet_file.schema_arrow),
        "file_metadata": {
            _json_value(key): _json_value(value)
            for key, value in (metadata.metadata or {}).items()
        },
    }
    if profile or time_column is not None:
        table = _bounded_table(parquet_file, max_rows)
        report["profiled_rows"] = table.num_rows
        report["truncated_profile"] = table.num_rows < metadata.num_rows
        if profile:
            report["columns"] = {
                name: _column_profile(table[name]) for name in table.column_names
            }
        if time_column is not None:
            if time_column not in table.column_names:
                raise ValueError(
                    f"Time column {time_column!r} not found; available columns: "
                    f"{table.column_names!r}"
                )
            report["cadence"] = _cadence_profile(table[time_column], time_unit)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--max-rows", type=int, default=250_000)
    parser.add_argument("--time-column")
    parser.add_argument(
        "--time-unit", choices=("seconds", "milliseconds"), default="seconds"
    )
    args = parser.parse_args()
    if args.max_rows <= 0:
        parser.error("--max-rows must be positive")

    reports = [
        inspect_parquet(
            path,
            profile=args.profile,
            max_rows=args.max_rows,
            time_column=args.time_column,
            time_unit=args.time_unit,
        )
        for path in args.files
    ]
    print(json.dumps(reports, indent=2, default=_json_value, sort_keys=True))


if __name__ == "__main__":
    main()
