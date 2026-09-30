"""Evaluate the fixed V0A.9 robust GNSS rules on selected Walking sessions."""

from __future__ import annotations

import csv
from pathlib import Path

from football_stat_tracker.gnss_diagnostics import calculate_distance_error
from football_stat_tracker.gnss_robust import (
    RobustGnssConfig,
    estimate_robust_gnss_distance,
)
from football_stat_tracker.importers.walking import import_walking_session


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPOSITORY_ROOT / "data/raw/walking/data"
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "outputs/v0a9_gnss_robust"
SESSION_PATHS = (
    "subject_14/14_2",
    "subject_14/14_6",
    "subject_16/16_2",
    "subject_17/17_0",
    "subject_18/18_0",
    "subject_8/8_4",
)
# Fixed from physical/operational reasoning before evaluating ground truth.
CONFIG = RobustGnssConfig(max_speed_mps=15.0, gap_threshold_s=30.0)


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT_DIRECTORY / "robust_distance_evaluation.csv"
    decisions_path = OUTPUT_DIRECTORY / "segment_decisions.csv"

    with summary_path.open("w", newline="", encoding="utf-8") as summary_file, decisions_path.open(
        "w", newline="", encoding="utf-8"
    ) as decisions_file:
        summary = csv.writer(summary_file)
        decisions = csv.writer(decisions_file)
        summary.writerow(
            [
                "session",
                "reference_distance_m",
                "raw_distance_m",
                "robust_distance_m",
                "raw_error_percent",
                "robust_error_percent",
                "analyzed_segments",
                "rejected_segments",
                "rejected_distance_m",
                "gaps",
                "gap_duration_s",
                "uncertain_distance_m",
                "max_speed_mps",
                "gap_threshold_s",
            ]
        )
        decisions.writerow(
            [
                "session",
                "start_s",
                "end_s",
                "delta_t_s",
                "distance_m",
                "geometric_speed_mps",
                "is_gap",
                "decision",
                "start_accuracy_m",
                "end_accuracy_m",
            ]
        )

        for relative_path in SESSION_PATHS:
            session = import_walking_session(DATA_ROOT / relative_path)
            result = estimate_robust_gnss_distance(session.gnss, CONFIG)
            reference = session.metadata.distance_reference_m
            raw_error = calculate_distance_error(result.raw_distance_m, reference)
            robust_error = calculate_distance_error(
                result.estimated_distance_m, reference
            )
            summary.writerow(
                [
                    session.metadata.recording_id,
                    reference,
                    result.raw_distance_m,
                    result.estimated_distance_m,
                    raw_error.relative_percent,
                    robust_error.relative_percent,
                    result.total_segments,
                    result.rejected_segments,
                    result.rejected_distance_m,
                    result.gap_count,
                    result.total_gap_duration_s,
                    result.uncertain_distance_m,
                    CONFIG.max_speed_mps,
                    CONFIG.gap_threshold_s,
                ]
            )
            for assessment in result.segment_assessments:
                if assessment.decision.value != "accepted":
                    decisions.writerow(
                        [
                            session.metadata.recording_id,
                            assessment.start_timestamp_analysis_ms / 1000.0,
                            assessment.end_timestamp_analysis_ms / 1000.0,
                            assessment.delta_t_s,
                            assessment.distance_m,
                            assessment.geometric_speed_mps,
                            assessment.is_gap,
                            assessment.decision.value,
                            assessment.start_horizontal_accuracy_m,
                            assessment.end_horizontal_accuracy_m,
                        ]
                    )


if __name__ == "__main__":
    main()
