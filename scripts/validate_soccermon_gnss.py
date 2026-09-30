"""Compare GNSS geometry and vendor speed in the existing SoccerMon subset.

Imports complete canonical sessions one at a time. Outputs are local ignored
diagnostics, not reference accuracy or playing-distance claims. No download,
sprint detection, clock reconstruction, location export or raw-data mutation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform

import numpy as np

from football_stat_tracker.gnss import total_gnss_distance_m
from football_stat_tracker.gnss_robust import (
    RobustGnssConfig, SegmentDecision, estimate_robust_gnss_distance,
)
from football_stat_tracker.gnss_validation import build_candidate_series, integrate_vendor_speed
from football_stat_tracker.importers.soccermon import import_soccermon_session


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def distribution(values):
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return {"count": 0, "mean": None, "median": None, "p95": None, "max": None}
    return {"count": len(array), "mean": float(array.mean()),
            "median": float(np.median(array)), "p95": float(np.quantile(array, .95)),
            "max": float(array.max())}


def speed_comparison(geometric, vendor, mask):
    g, v = geometric[mask], vendor[mask]
    difference = g - v
    return {
        "count": len(g), "geometric_mps": distribution(g), "vendor_left_mps": distribution(v),
        "bias_geom_minus_vendor_mps": float(difference.mean()) if len(g) else None,
        "mae_mps": float(np.abs(difference).mean()) if len(g) else None,
        "rmse_mps": float(np.sqrt(np.mean(difference ** 2))) if len(g) else None,
        "p95_absolute_difference_mps": float(np.quantile(np.abs(difference), .95)) if len(g) else None,
        "pearson_r": (float(np.corrcoef(g, v)[0, 1])
                      if len(g) > 1 and np.std(g) > 0 and np.std(v) > 0 else None),
    }


def evaluate_session(session, label, max_interval_s=.1):
    """Metrics plus plotting arrays, with explicit all-link/common-input support."""
    series = build_candidate_series(session.gnss)
    samples = series.samples
    robust = estimate_robust_gnss_distance(samples)  # Original 15 m/s, 30 s rules.
    vendor = integrate_vendor_speed(series, max_interval_s=max_interval_s)
    segments = robust.segment_assessments
    dt = np.array([s.delta_t_s for s in segments])
    distance = np.array([s.distance_m for s in segments])
    geometric = np.array([s.geometric_speed_mps for s in segments], dtype=float)
    left = np.array([s.speed_mps for s in samples[:-1]], dtype=float)
    accepted = np.array([s.decision in (SegmentDecision.ACCEPTED, SegmentDecision.ACCEPTED_GAP_CHORD)
                         for s in segments], dtype=bool)
    common = np.array(vendor.eligible, dtype=bool)
    broken = np.array(series.break_before[1:], dtype=bool)
    repeated = np.array([(a.latitude_deg, a.longitude_deg) == (b.latitude_deg, b.longitude_deg)
                         for a, b in zip(samples, samples[1:])], dtype=bool)
    time = np.array([s.timestamp_analysis_ms / 1000 for s in samples])
    span = ((session.gnss[-1].timestamp_raw_ms - session.gnss[0].timestamp_raw_ms) / 1000
            if session.gnss else 0.0)
    longest_hold = hold = 0.0
    for d, same, ok in zip(dt, repeated, common):
        hold = hold + d if same and ok else 0.0
        longest_hold = max(longest_hold, hold)
    reason_counts = Counter(vendor.reasons)
    reason_durations = {reason: math.fsum(d for d, r in zip(dt, vendor.reasons) if r == reason)
                        for reason in reason_counts}
    source_counts = Counter(reason for _, reason in series.exclusions)
    invalid_indices = [i for i, r in series.exclusions if r == "invalid_coordinates"]
    raw = total_gnss_distance_m(samples)
    if not math.isclose(raw, robust.raw_distance_m, rel_tol=1e-12, abs_tol=1e-9):
        raise ValueError("Raw/robust input support mismatch")
    summary = {
        "session": label, "recording_id": session.metadata.recording_id,
        "sha256": session.metadata.provenance.sha256 if session.metadata.provenance else None,
        "source_rows": session.metadata.provenance.source_row_count if session.metadata.provenance else None,
        "imu_samples_preserved": len(session.imu), "source_gnss_candidates": len(session.gnss),
        "retained_candidates": len(samples), "exclusions": dict(source_counts),
        "invalid_coordinate_candidates": len(invalid_indices),
        "invalid_coordinate_source_rows": sum(session.gnss[i].raw_source.source_row_count
                                               for i in invalid_indices if session.gnss[i].raw_source),
        "duplicate_candidate_time_groups": series.duplicate_time_groups,
        "conflicting_candidate_time_groups": series.conflicting_time_groups,
        "source_duplicate_timestamp_rows": (session.metadata.provenance.source_row_count
                                            - len(set(s.timestamp_raw_ms for s in session.gnss))
                                            if session.metadata.provenance else None),
        "source_interval_counts_ms": dict(Counter(
            b.timestamp_raw_ms - a.timestamp_raw_ms for a, b in zip(session.gnss, session.gnss[1:]))),
        "valid_link_interval_counts_ms": dict(Counter(round(d * 1000) for d in dt)),
        "recording_span_s": span, "valid_link_span_s": vendor.total_link_duration_s,
        "max_valid_link_interval_s": float(dt.max()) if len(dt) else None,
        "clock_gap_links": int(np.count_nonzero(dt > max_interval_s)),
        "links_crossing_excluded_groups": int(broken.sum()),
        "unsupported_coordinate_or_gap_chord_m": math.fsum(distance[broken | (dt > max_interval_s)]),
        "repeated_coordinate_links": int(repeated.sum()),
        "repeated_supported_links_with_positive_vendor_speed": int((repeated & common & (left > 0)).sum()),
        "longest_supported_coordinate_hold_s": longest_hold,
        "raw_haversine_m": raw, "robust_m": robust.estimated_distance_m,
        "robust_rejected_links": robust.rejected_segments,
        "robust_rejected_distance_m": robust.rejected_distance_m,
        "robust_legacy_gap_links": robust.gap_count,
        "robust_legacy_uncertain_chord_m": robust.uncertain_distance_m,
        "vendor_left_m": vendor.distance_m,
        "vendor_supported_duration_s": vendor.supported_duration_s,
        "vendor_coverage_percent": 100 * vendor.supported_duration_s / span if span else None,
        "vendor_exclusion_counts": dict(reason_counts),
        "vendor_reason_duration_s": reason_durations,
        "raw_common_input_m": math.fsum(distance[common]),
        "robust_common_input_m": math.fsum(distance[common & accepted]),
        "robust_common_accepted_duration_s": math.fsum(dt[common & accepted]),
        "vendor_zero_common_duration_s": math.fsum(dt[common & (left == 0)]),
        "raw_vendor_zero_common_m": math.fsum(distance[common & (left == 0)]),
        "robust_vendor_zero_common_m": math.fsum(distance[common & accepted & (left == 0)]),
        "common_input_speed_comparison": speed_comparison(geometric, left, common),
        "accepted_common_speed_comparison": speed_comparison(geometric, left, common & accepted),
        "all_link_geometric_speed_mps": distribution(geometric),
        "vendor_candidate_speed_mps": distribution([s.speed_mps for s in samples]),
        "independently_identifiable_fixes": None,
        "uncertainty_flags": ["no_independent_ground_truth", "receiver_fix_freshness_unknown",
                              "vendor_filter_and_clock_phase_unknown", "native_quality_scale_unknown",
                              "recording_is_not_verified_playing_time"],
    }
    if len(invalid_indices):
        summary["uncertainty_flags"].append("invalid_coordinates_excluded")
    if np.any(dt > max_interval_s) or np.any(broken):
        summary["uncertainty_flags"].append("discontinuous_support")
    if robust.rejected_segments:
        summary["uncertainty_flags"].append("implausible_geometric_links")
    if series.conflicting_time_groups:
        summary["uncertainty_flags"].append("conflicting_time_groups_quarantined")
    if reason_counts.get("unusable_vendor_speed"):
        summary["uncertainty_flags"].append("unusable_vendor_speed")
    sensitivities = []
    for speed_limit in (10., 12., 15., 20.):
        result = estimate_robust_gnss_distance(samples, RobustGnssConfig(max_speed_mps=speed_limit))
        sensitivities.append({"session": label, "experiment": "geometric_speed_limit",
                              "parameter": speed_limit, "distance_m": result.estimated_distance_m,
                              "excluded_links": result.rejected_segments,
                              "flagged_links": result.gap_count,
                              "uncertain_chord_m": result.uncertain_distance_m})
    for gap_limit in (.1, .2, 1., 2., 30.):
        result = estimate_robust_gnss_distance(samples, RobustGnssConfig(gap_threshold_s=gap_limit))
        sensitivities.append({"session": label, "experiment": "legacy_gap_flag_threshold",
                              "parameter": gap_limit, "distance_m": result.estimated_distance_m,
                              "excluded_links": result.rejected_segments, "flagged_links": result.gap_count,
                              "uncertain_chord_m": result.uncertain_distance_m})
        alt = integrate_vendor_speed(series, max_interval_s=gap_limit)
        sensitivities.append({"session": label, "experiment": "vendor_max_interval_counterfactual",
                              "parameter": gap_limit, "distance_m": alt.distance_m,
                              "supported_duration_s": alt.supported_duration_s,
                              "excluded_links": len(alt.eligible) - sum(alt.eligible)})
    for convention in ("left", "right", "trapezoidal"):
        alt = integrate_vendor_speed(series, max_interval_s=max_interval_s, convention=convention)
        sensitivities.append({"session": label, "experiment": "vendor_weighting_same_support",
                              "parameter": convention, "distance_m": alt.distance_m,
                              "supported_duration_s": alt.supported_duration_s})
    sensitivities.append({"session": label, "experiment": "robust_excluding_discontinuities",
                          "parameter": max_interval_s,
                          "distance_m": math.fsum(distance[accepted & ~broken & (dt <= max_interval_s)]),
                          "supported_duration_s": math.fsum(dt[accepted & ~broken & (dt <= max_interval_s)])})
    picks = {}
    if len(dt):
        picks[int(np.argmax(geometric))] = "largest_geometric_speed"
        gap_mask = broken | (dt > max_interval_s)
        if np.any(gap_mask):
            picks[int(np.argmax(np.where(gap_mask, dt, -1)))] = "longest_discontinuity"
        if np.any(common):
            picks[int(np.argmax(np.where(common, np.abs(geometric - left), -1)))] = "largest_supported_speed_difference"
    anomalies = []
    for i, reason in picks.items():
        a, b = samples[i:i+2]
        item = {"session": label, "example": reason, "interval_index": i,
                "start_elapsed_s": float(time[i]), "end_elapsed_s": float(time[i+1]),
                "dt_s": float(dt[i]), "distance_m": float(distance[i]),
                "geometric_mps": float(geometric[i]), "vendor_left_mps": a.speed_mps,
                "vendor_right_mps": b.speed_mps, "robust_decision": segments[i].decision.value,
                "vendor_support": vendor.reasons[i],
                "original_candidate_start_indices": list(series.source_indices[i]),
                "original_candidate_end_indices": list(series.source_indices[i+1])}
        for endpoint, sample in (("start", a), ("end", b)):
            if sample.raw_source:
                item[endpoint + "_source_row"] = sample.raw_source.source_row_index
                for field in ("hacc", "hdop", "signal_quality", "num_satellites"):
                    item[endpoint + "_native_" + field] = sample.raw_source.get(field)
        anomalies.append(item)
    arrays = {"time": time, "dt": dt, "distance": distance, "geometric": geometric,
              "vendor": np.array([s.speed_mps for s in samples], dtype=float),
              "common": common, "accepted": accepted, "broken": broken,
              "raw_cumulative": np.r_[0., np.cumsum(distance)] if len(samples) else np.array([]),
              "robust_cumulative": np.r_[0., np.cumsum(np.where(accepted, distance, 0.))] if len(samples) else np.array([]),
              "vendor_cumulative": np.r_[0., np.cumsum(vendor.interval_distances_m)] if len(samples) else np.array([])}
    return summary, arrays, anomalies, sensitivities


def plot_session(summary, a, anomalies, output):
    import matplotlib.pyplot as plt

    label = summary["session"]
    t = a["time"]
    if not len(t):
        return
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True, constrained_layout=True)
    for ax in axes:
        ax.scatter(t[1:] / 60, a["geometric"], s=1, alpha=.5, color="tab:orange", label="Geometry: displacement / dt")
        ax.scatter(t / 60, a["vendor"], s=1, color="tab:blue", label="Vendor observations")
        ax.set_ylabel("Speed (m/s)")
        ax.grid(alpha=.2)
    axes[0].set_yscale("symlog", linthresh=5)
    axes[0].set_ylim(bottom=0)
    axes[0].set_title(f"{label} — full speed range (symlog); exported candidates, freshness unknown")
    axes[0].legend(markerscale=4, loc="upper right")
    axes[1].set_ylim(-.2, 12)
    for values, tt, color in ((a["geometric"], t[1:], "tab:orange"), (a["vendor"], t, "tab:blue")):
        high = values > 12
        axes[1].scatter(tt[high] / 60, np.full(high.sum(), 11.8), marker="^", s=9, color=color)
    axes[1].set_title("0–12 m/s display window; triangles show values above the display range")
    axes[1].set_xlabel("Elapsed recording time (minutes)")
    fig.savefig(output / f"{label}_speed.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)
    for key, title, color in (("raw_cumulative", "A: raw Haversine (all valid links)", "tab:orange"),
                              ("robust_cumulative", "B: original robust 15 m/s, 30 s", "tab:green"),
                              ("vendor_cumulative", "C: vendor left integral (supported links only)", "tab:blue")):
        ax.step(t / 60, a[key] / 1000, where="post", label=title, color=color, lw=1.2)
    for i in np.flatnonzero(~a["common"]):
        ax.axvspan(t[i] / 60, t[i+1] / 60, color="gray", alpha=.25)
    ax.set(xlabel="Elapsed recording time (minutes)", ylabel="Accumulated distance (km)",
           title=f"{label} — C coverage {summary['vendor_coverage_percent']:.3f}%; gray = unsupported C intervals")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=.2)
    fig.savefig(output / f"{label}_cumulative_distance.png", dpi=160)
    plt.close(fig)

    if anomalies:
        fig, axes = plt.subplots(len(anomalies), 1, figsize=(12, 3 * len(anomalies)),
                                 squeeze=False, constrained_layout=True)
        for row, example in enumerate(anomalies):
            i = example["interval_index"]
            window = (t >= t[i] - 3) & (t <= t[i+1] + 3)
            links = window[1:]
            ax = axes[row, 0]
            vendor_line = a["vendor"].copy()
            vendor_line[1:][~a["common"]] = np.nan
            ax.plot(t[window], vendor_line[window], "-", color="tab:blue", lw=.8)
            ax.scatter(t[window], a["vendor"][window], s=9, color="tab:blue", label="Vendor (candidate observations)")
            ax.plot(t[1:][links], a["geometric"][links], ".", color="tab:orange", label="Geometry (interval average)")
            ax.axvspan(t[i], t[i+1], color="gray", alpha=.2)
            # Keep low-speed windows linear so ordinary m/s ticks stay readable.
            # Extreme jumps need symlog to show vendor observations near zero.
            if np.any(a["geometric"][links] > 12) or np.any(a["vendor"][window] > 12):
                ax.set_yscale("symlog", linthresh=5)
            ax.set_ylim(bottom=0)
            ax.set(xlabel="Elapsed recording time (seconds)", ylabel="Speed (m/s)",
                   title=f"{label}: {example['example'].replace('_', ' ')} — dt={example['dt_s']:g}s, d={example['distance_m']:.2f}m; "
                         f"{example['robust_decision'].replace('_', ' ')}; C={example['vendor_support'].replace('_', ' ')}")
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
        fig.savefig(output / f"{label}_anomalous_segments.png", dpi=160)
        plt.close(fig)


def plot_intervals(summaries, output):
    import matplotlib.pyplot as plt

    rows = math.ceil(len(summaries) / 3)
    fig, axes = plt.subplots(rows, 3, figsize=(13, 3 * rows), squeeze=False, constrained_layout=True)
    for ax, summary in zip(axes.flat, summaries):
        counts = summary["valid_link_interval_counts_ms"]
        intervals = sorted(counts, key=int)
        ax.bar([str(x) for x in intervals], [counts[x] for x in intervals], color="tab:blue")
        ax.set_yscale("log")
        ax.set(title=summary["session"], xlabel="Valid-coordinate link dt (ms)", ylabel="Link count (log)")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(axis="y", alpha=.2)
    for ax in list(axes.flat)[len(summaries):]:
        ax.set_visible(False)
    fig.suptitle("Observed clock intervals after coordinate exclusions — not independent-fix sampling rates")
    fig.savefig(output / "gnss_intervals.png", dpi=160)
    plt.close(fig)


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("outputs/v0b1_soccermon_inventory/extracted_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/v0b3_gnss_validation"))
    parser.add_argument("--max-interval-s", type=float, default=.1,
                        help="Primary vendor integration continuity limit; default 0.1 s")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    if not math.isfinite(args.max_interval_s) or args.max_interval_s <= 0:
        parser.error("--max-interval-s must be finite and positive")
    entries = json.loads(args.manifest.read_text())["sessions"]
    if not entries:
        raise ValueError("Empty session manifest")
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.no_plots:
        os.environ.setdefault("MPLCONFIGDIR", str((args.output / "mpl_cache").resolve()))
        import matplotlib
        matplotlib.use("Agg")
        (args.output / "figures").mkdir(exist_ok=True)
    summaries, anomalies, sensitivities = [], [], []
    for number, entry in enumerate(entries, 1):
        path = Path(entry["extracted_path"])
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"Manifest checksum mismatch: {path}")
        session = import_soccermon_session(path)
        if session.metadata.provenance.sha256 != entry["sha256"]:
            raise ValueError(f"Importer checksum mismatch: {path}")
        summary, arrays, examples, sensitivity = evaluate_session(session, f"S{number}", args.max_interval_s)
        if not args.no_plots:
            plot_session(summary, arrays, examples, args.output / "figures")
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"Source changed during analysis: {path}")
        summary["source_hash_unchanged"] = True
        summaries.append(summary)
        anomalies.extend(examples)
        sensitivities.extend(sensitivity)
        print(json.dumps({k: summary[k] for k in ("session", "retained_candidates", "raw_haversine_m", "robust_m",
                                                  "vendor_left_m", "vendor_coverage_percent")}), flush=True)
        del session, arrays
        gc.collect()
    if not args.no_plots:
        plot_intervals(summaries, args.output / "figures")
    payload = {"method_version": "v0b3.1", "python": platform.python_version(), "numpy": np.__version__,
               "robust_config": {"max_speed_mps": 15., "gap_threshold_s": 30.},
               "vendor_convention": "left", "vendor_max_interval_s": args.max_interval_s,
               "vendor_requires_both_endpoint_speeds": True, "sessions": summaries,
               "anomaly_examples": anomalies, "sensitivity": sensitivities}
    # Missing/non-finite optional observations in anomaly examples remain explicit nulls.
    def sanitize(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {k: sanitize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize(v) for v in value]
        return value
    payload = sanitize(payload)
    (args.output / "validation_summary.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    flat = [{k: v for k, v in summary.items() if not isinstance(v, dict)} for summary in payload["sessions"]]
    write_csv(args.output / "comparison.csv", flat)
    write_csv(args.output / "sensitivity.csv", payload["sensitivity"])
    write_csv(args.output / "anomalies.csv", payload["anomaly_examples"])
    write_csv(args.output / "speed_comparison.csv", [
        {"session": s["session"], "support": support, **s[support]}
        for s in payload["sessions"] for support in ("common_input_speed_comparison", "accepted_common_speed_comparison")])
    write_csv(args.output / "interval_distribution.csv", [
        {"session": s["session"], "dt_ms": dt, "link_count": count}
        for s in payload["sessions"] for dt, count in s["valid_link_interval_counts_ms"].items()])
    return payload


if __name__ == "__main__":
    main()
