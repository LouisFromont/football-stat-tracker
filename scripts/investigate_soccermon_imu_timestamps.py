"""Audit SoccerMon IMU time groups without reconstructing sample timestamps.

Reads only time and six native IMU axes from manifest-selected recordings.
Writes aggregate counts/distributions and plots; no row traces or coordinates.
Run with PYTHONPATH=src and the existing project-local analysis environment.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from football_stat_tracker.importers.soccermon import IMU_COLUMNS, parse_soccermon_time_ms


REFERENCE_GROUP_MS = 100  # Inspection reference, not a physical timing assertion.
REFERENCE_GROUP_ROWS = 10
HISTOGRAM_EDGES = np.r_[0., np.geomspace(1e-6, 100., 65)]


def percentage(count, denominator):
    return 100 * int(count) / int(denominator) if denominator else None


def counts(values):
    unique, frequency = np.unique(values, return_counts=True)
    return {str(int(v)): int(n) for v, n in zip(unique, frequency)}


def distribution(values):
    """Quantiles of finite values only; missing counts are reported by callers."""
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    result = {"count": len(finite)}
    if len(finite):
        result.update(zip(("min", "p05", "p25", "median", "p75", "p95", "p99", "max"),
                          map(float, np.quantile(finite, [0, .05, .25, .5, .75, .95, .99, 1]))))
        positive = finite[finite > 0]
        result["smallest_positive"] = float(positive.min()) if len(positive) else None
    else:
        result.update({k: None for k in ("min", "p05", "p25", "median", "p75", "p95", "p99", "max", "smallest_positive")})
    return result


def timestamp_groups(timestamps_ms):
    """Keep contiguous groups in source order; separately count global multiplicity."""
    times = np.asarray(timestamps_ms)
    if times.ndim != 1 or not len(times) or not np.issubdtype(times.dtype, np.integer):
        raise ValueError("Expected a nonempty one-dimensional integer millisecond clock")
    if np.any(times < 0) or np.any(times >= 86400000):
        raise ValueError("Expected local time-of-day milliseconds without midnight repair")
    times = times.astype(np.int64, copy=False)
    delta = np.diff(times)
    starts = np.r_[0, np.flatnonzero(delta != 0) + 1]
    sizes = np.diff(np.r_[starts, len(times)])
    group_delta = np.diff(times[starts])
    _, distinct_sizes = np.unique(times, return_counts=True)
    normal = group_delta == REFERENCE_GROUP_MS
    gaps = group_delta > REFERENCE_GROUP_MS
    monotonic = bool(np.all(delta >= 0))
    stats = {
        "source_rows": len(times), "distinct_timestamp_count": len(distinct_sizes),
        "contiguous_group_count": len(starts),
        "rows_per_distinct_timestamp_distribution": counts(distinct_sizes),
        "contiguous_group_size_distribution": counts(sizes),
        "exactly_ten_group_count": int(np.sum(sizes == REFERENCE_GROUP_ROWS)),
        "exactly_ten_group_percent": percentage(np.sum(sizes == REFERENCE_GROUP_ROWS), len(sizes)),
        "first_group_size": int(sizes[0]), "last_group_size": int(sizes[-1]),
        "first_group_partial_relative_to_ten": bool(sizes[0] < REFERENCE_GROUP_ROWS),
        "last_group_partial_relative_to_ten": bool(sizes[-1] < REFERENCE_GROUP_ROWS),
        "interior_non_ten_group_count": int(np.sum(sizes[1:-1] != REFERENCE_GROUP_ROWS)),
        "source_row_interval_counts_ms": counts(delta),
        "contiguous_group_interval_counts_ms": counts(group_delta),
        "positive_group_interval_summary_ms": distribution(group_delta[group_delta > 0]),
        "adjacent_timestamp_repeat_count": int(np.sum(delta == 0)),
        "noncontiguous_timestamp_recurrences": len(starts) - len(distinct_sizes),
        "timestamp_reversal_count": int(np.sum(delta < 0)),
        "gap_over_100ms_count": int(np.sum(gaps)),
        "non_100ms_positive_interval_count": int(np.sum((group_delta > 0) & ~normal)),
        "off_100ms_grid_group_count": int(np.sum(times[starts] % REFERENCE_GROUP_MS != 0)),
        "elapsed_stored_span_s": float(times[-1] - times[0]) / 1000 if monotonic else None,
        "observed_export_row_density_rows_s": (len(times) - 1) * 1000 / int(times[-1] - times[0])
            if monotonic and times[-1] > times[0] else None,
        # Scalar counterfactual, NOT a timeline or a sampling-frequency fit.
        "stored_span_minus_uniform_100rows_s_span_ms": int(times[-1] - times[0]) - (len(times) - 1) * 10
            if monotonic else None,
        "absent_grid_bins_if_100ms_grid": int(np.sum(group_delta[gaps] // REFERENCE_GROUP_MS - 1))
            if monotonic and np.all(group_delta % REFERENCE_GROUP_MS == 0) else None,
    }
    return starts, sizes, stats


def identity_statistics(values, starts, sizes):
    """Exact encoded-vector equality among finite samples; not a duplication test."""
    finite = np.isfinite(values).all(axis=1)
    eligible_pairs = finite[:-1] & finite[1:]
    equal = np.all(values[:-1] == values[1:], axis=1) & eligible_pairs
    group_ids = np.repeat(np.arange(len(starts)), sizes)
    group_finite = np.logical_and.reduceat(finite, starts)
    equals_first = np.all(values == values[starts[group_ids]], axis=1)
    identical = np.logical_and.reduceat(equals_first, starts) & group_finite
    multirow = sizes > 1
    classifiable = multirow & group_finite
    n_identical = int(np.sum(identical & multirow))
    n_varying = int(np.sum(~identical & classifiable))
    summary = {
        "nonfinite_sample_vector_count": int(np.sum(~finite)),
        "singleton_group_count": int(np.sum(~multirow)),
        "unclassifiable_group_count": int(np.sum(~group_finite)),
        "classifiable_multirow_group_count": int(np.sum(classifiable)),
        "identical_multirow_group_count": n_identical,
        "varying_multirow_group_count": n_varying,
        "identical_group_percent": percentage(n_identical, np.sum(classifiable)),
        "varying_group_percent": percentage(n_varying, np.sum(classifiable)),
        "consecutive_finite_pair_count": int(np.sum(eligible_pairs)),
        "consecutive_identical_vector_count": int(np.sum(equal)),
        "consecutive_identical_vector_percent": percentage(np.sum(equal), np.sum(eligible_pairs)),
        "maximum_identical_finite_vector_run_rows": int(np.max(np.diff(np.r_[0, np.flatnonzero(~equal) + 1, len(values)])))
            if finite.any() else None,
    }
    return summary, eligible_pairs, equal, group_ids


def pair_statistics(differences, norms, eligible, equal, mask):
    selected = mask & eligible
    valid_difference = selected & np.isfinite(differences).all(axis=1) & np.isfinite(norms)
    selected_norms = norms[valid_difference]
    histogram, _ = np.histogram(selected_norms, HISTOGRAM_EDGES)
    return {
        "pair_count": int(np.sum(mask)), "finite_pair_count": int(np.sum(selected)),
        "nonfinite_pair_count": int(np.sum(mask & ~eligible)),
        "nonfinite_difference_count": int(np.sum(selected & ~valid_difference)),
        "identical_vector_count": int(np.sum(mask & equal)),
        "identical_vector_percent": percentage(np.sum(mask & equal), np.sum(selected)),
        "difference_norm": distribution(selected_norms),
        "signed_axis_differences": {axis: distribution(differences[valid_difference, i]) for i, axis in enumerate("xyz")},
        "norm_histogram_counts": histogram.tolist(),
        "norm_histogram_overflow_count": int(np.sum(selected_norms > HISTOGRAM_EDGES[-1])),
    }


def sensor_statistics(values, times, starts, sizes, unit):
    values = np.asarray(values, dtype=float)
    if values.shape != (len(times), 3):
        raise ValueError("Expected one three-axis vector per timestamp row")
    identity, eligible, equal, group_ids = identity_statistics(values, starts, sizes)
    with np.errstate(invalid="ignore", over="ignore"):
        differences = np.diff(values, axis=0)
        norms = np.linalg.norm(differences, axis=1)
    delta = np.diff(times)
    within = delta == 0
    boundary = ~within
    masks = {
        "all_consecutive": np.ones(len(delta), dtype=bool), "within_group": within,
        "all_boundaries": boundary, "boundary_100ms": delta == REFERENCE_GROUP_MS,
        "boundary_gap_over100ms": delta > REFERENCE_GROUP_MS, "boundary_reversal": delta < 0,
    }
    pairs = {name: pair_statistics(differences, norms, eligible, equal, mask) for name, mask in masks.items()}
    full_groups = sizes[group_ids] == REFERENCE_GROUP_ROWS
    offsets = np.arange(len(times)) - starts[group_ids]
    ordinal = {
        str(i + 1): pair_statistics(differences, norms, eligible, equal,
                                   within & full_groups[:-1] & (offsets[:-1] == i))
        for i in range(REFERENCE_GROUP_ROWS - 1)
    }
    ordinal["boundary"] = pair_statistics(differences, norms, eligible, equal,
                                          (delta == REFERENCE_GROUP_MS) & full_groups[:-1] & full_groups[1:])
    within_median = pairs["within_group"]["difference_norm"]["median"]
    boundary_median = pairs["boundary_100ms"]["difference_norm"]["median"]
    middle_median = ordinal["5"]["difference_norm"]["median"]
    other_medians = [ordinal[str(i)]["difference_norm"]["median"] for i in range(1, 10) if i != 5]
    other_reference = float(np.median(other_medians)) if all(v is not None for v in other_medians) else None
    return {
        "native_unit_documented_not_calibrated": unit, "identity": identity,
        "pairs": pairs, "full_ten_row_group_pair_ordinals": ordinal,
        "boundary100ms_to_within_median_norm_ratio": boundary_median / within_median
            if within_median and boundary_median is not None else None,
        # Median-of-medians comparison, not an inferred interval or timing correction.
        "middle_pair_to_other_within_median_ratio": middle_median / other_reference
            if other_reference and middle_median is not None else None,
        "per_axis_identical_consecutive_pair_counts": {
            axis: int(np.sum((values[:-1, i] == values[1:, i]) & eligible)) for i, axis in enumerate("xyz")
        },
    }


def analyze_imu_arrays(timestamps_ms, acceleration, gyroscope):
    starts, sizes, clock = timestamp_groups(timestamps_ms)
    times = np.asarray(timestamps_ms, dtype=np.int64)
    acceleration, gyroscope = np.asarray(acceleration, dtype=float), np.asarray(gyroscope, dtype=float)
    accel = sensor_statistics(acceleration, times, starts, sizes, "g")
    gyro = sensor_statistics(gyroscope, times, starts, sizes, "deg/s")
    joint_identity, *_ = identity_statistics(np.column_stack((acceleration, gyroscope)), starts, sizes)
    # Never compute a six-axis norm mixing acceleration and angular-rate units.
    return {"clock": clock, "accelerometer": accel, "gyroscope": gyro,
            "combined_six_axis_identity": joint_identity}


def inspect_recording(entry):
    path = Path(entry["extracted_path"])
    def digest():
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    if digest() != entry["sha256"]:
        raise ValueError(f"Manifest checksum mismatch: {path}")
    parquet = pq.ParquetFile(path)
    required = ("time", *IMU_COLUMNS)
    schema = parquet.schema_arrow
    if len(set(schema.names)) != len(schema.names) or set(required) - set(schema.names):
        raise ValueError("Missing required or duplicate IMU analysis columns")
    for name in IMU_COLUMNS:
        if not (pa.types.is_floating(schema.field(name).type) or pa.types.is_integer(schema.field(name).type)
                or pa.types.is_null(schema.field(name).type)):
            raise ValueError(f"Non-numeric IMU column: {name}")
    table = parquet.read(columns=list(required))
    text = table["time"].to_pylist()
    parsed = {s: parse_soccermon_time_ms(s) for s in set(text)}
    times = np.fromiter((parsed[s] for s in text), dtype=np.int64, count=len(text))
    acceleration = np.column_stack([table[n].to_numpy(zero_copy_only=False) for n in IMU_COLUMNS[:3]])
    gyroscope = np.column_stack([table[n].to_numpy(zero_copy_only=False) for n in IMU_COLUMNS[3:]])
    result = analyze_imu_arrays(times, acceleration, gyroscope)
    result.update({
        "source_sha256": entry["sha256"], "all_rows_analyzed": len(times) == parquet.metadata.num_rows,
        "source_hash_unchanged": digest() == entry["sha256"],
        "source_schema": [(f.name, str(f.type)) for f in schema],
        "metadata_keys": [k.decode("utf-8", errors="replace") for k in (parquet.metadata.metadata or {})],
        "parquet_created_by": parquet.metadata.created_by,
        "fractional_timestamp_digit_counts": dict(Counter(len(s.split(".")[1]) if "." in s else 0 for s in text)),
        "imu_column_missing_counts": {
            n: {"null": table[n].null_count,
                "nonfinite_including_null": int(np.sum(~np.isfinite(np.asarray(table[n].to_numpy(zero_copy_only=False), dtype=float))))}
            for n in IMU_COLUMNS
        },
    })
    if not result["source_hash_unchanged"]:
        raise ValueError(f"Source changed during inspection: {path}")
    return result


def make_plots(results, output):
    import os
    os.environ.setdefault("MPLCONFIGDIR", str((output / ".matplotlib").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [r["session_label"] for r in results]
    x = np.arange(len(results))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    group_sizes = sorted({int(k) for r in results for k in r["clock"]["contiguous_group_size_distribution"]})
    width = .8 / len(group_sizes)
    for i, size in enumerate(group_sizes):
        axes[0, 0].bar(x + (i - (len(group_sizes) - 1) / 2) * width,
                       [r["clock"]["contiguous_group_size_distribution"].get(str(size), 0) for r in results],
                       width=width, label=f"{size} rows")
    axes[0, 0].set_yscale("log"); axes[0, 0].set_title("Timestamp-group counts (log scale)"); axes[0, 0].legend()
    axes[0, 1].bar(x, [100 - r["clock"]["exactly_ten_group_percent"] for r in results])
    axes[0, 1].set_title("Groups with size other than ten (%)")
    axes[1, 0].bar(x, [r["clock"]["gap_over_100ms_count"] for r in results])
    axes[1, 0].set_title("Stored timestamp gaps >100 ms (count)")
    axes[1, 1].bar(x, [r["clock"]["stored_span_minus_uniform_100rows_s_span_ms"]
                       if r["clock"]["stored_span_minus_uniform_100rows_s_span_ms"] is not None else np.nan for r in results])
    axes[1, 1].set_title("Stored span minus hypothetical uniform 100 rows/s span (ms)")
    for ax in axes.flat:
        ax.set_xticks(x, labels); ax.grid(axis="y", alpha=.2)
    fig.suptitle("SoccerMon stored clock structure — no reconstructed sample timestamps")
    fig.savefig(output / "clock_structure.png", dpi=150); plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    fig2, slots = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    for row, (sensor, unit) in enumerate((("accelerometer", "g"), ("gyroscope", "documented deg/s"))):
        for kind, label in (("within_group", "Within group"), ("boundary_100ms", "100 ms group boundary")):
            median = [r[sensor]["pairs"][kind]["difference_norm"]["median"] for r in results]
            p95 = [r[sensor]["pairs"][kind]["difference_norm"]["p95"] for r in results]
            axes[row, 0].plot(x, median, marker="o", label=label + " median")
            axes[row, 0].plot(x, p95, linestyle="--", label=label + " p95")
            pooled = np.sum([r[sensor]["pairs"][kind]["norm_histogram_counts"] for r in results], axis=0)
            denominator = sum(r[sensor]["pairs"][kind]["difference_norm"]["count"] for r in results)
            centers = np.sqrt(HISTOGRAM_EDGES[1:-1] * HISTOGRAM_EDGES[2:])
            probability = 100 * pooled[1:] / denominator if denominator else np.zeros(len(centers))
            axes[row, 1].plot(centers, np.where(probability > 0, probability, np.nan), label=label)
        axes[row, 0].set_xticks(x, labels); axes[row, 0].set_ylabel(f"Norm of vector difference ({unit})")
        axes[row, 0].set_title(sensor.capitalize() + ": median and p95 differences")
        axes[row, 1].set_xscale("log"); axes[row, 1].set_yscale("log")
        axes[row, 1].set_xlabel(f"Norm of encoded vector difference ({unit})")
        axes[row, 1].set_ylabel("Pairs per fixed log bin (%)")
        axes[row, 1].set_title("Pooled distributions (first bin/overflow counts in JSON)")
        for r in results:
            ordinal = r[sensor]["full_ten_row_group_pair_ordinals"]
            medians = [ordinal[k]["difference_norm"]["median"] for k in [*map(str, range(1, 10)), "boundary"]]
            slots[row].plot(range(1, 11), medians, marker=".", label=r["session_label"])
        slots[row].set_xticks(range(1, 11), [*map(str, range(1, 10)), "Boundary"])
        slots[row].set_ylabel(f"Median norm of difference ({unit})")
        slots[row].set_title(sensor.capitalize() + ": full ten-row groups, adjacent pair positions")
        slots[row].legend(ncol=9, fontsize=8); slots[row].grid(alpha=.2)
    for ax in axes.flat:
        ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.suptitle("Native IMU vector differences — no division by assumed sample intervals")
    fig.savefig(output / "imu_vector_differences.png", dpi=150); plt.close(fig)
    fig2.suptitle("Source-order continuity diagnostic; boundary uses 100 ms-separated full groups")
    fig2.savefig(output / "pair_position_differences.png", dpi=150); plt.close(fig2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("outputs/v0b1_soccermon_inventory/extracted_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/v0b2_imu_timestamp_investigation"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text())["sessions"]
    if not entries:
        raise ValueError("Empty recording manifest")
    if len({e["extracted_path"] for e in entries}) != len(entries):
        raise ValueError("Duplicate recording paths in manifest")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for i, entry in enumerate(entries, 1):
        result = inspect_recording(entry)
        result["session_label"] = f"S{i}"
        results.append(result)
        print(json.dumps({"session": f"S{i}", "rows": result["clock"]["source_rows"],
                          "groups": result["clock"]["contiguous_group_count"],
                          "ten_row_groups_percent": result["clock"]["exactly_ten_group_percent"],
                          "accel_identical_groups": result["accelerometer"]["identity"]["identical_multirow_group_count"],
                          "gyro_identical_groups": result["gyroscope"]["identity"]["identical_multirow_group_count"]}), flush=True)
    summary = {
        "analysis_policy": "Source order; exact numeric equality; finite vector eligibility; no timestamps estimated",
        "inspection_references": {"group_ms": REFERENCE_GROUP_MS, "group_rows": REFERENCE_GROUP_ROWS},
        "norm_histogram_edges": HISTOGRAM_EDGES.tolist(), "norm_histogram_units": "Per sensor's native documented unit",
        "session_count": len(results), "total_rows": sum(r["clock"]["source_rows"] for r in results),
        "total_groups": sum(r["clock"]["contiguous_group_count"] for r in results), "sessions": results,
    }
    (args.output / "aggregate_statistics.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    if not args.no_plots:
        make_plots(results, args.output)


if __name__ == "__main__":
    main()
