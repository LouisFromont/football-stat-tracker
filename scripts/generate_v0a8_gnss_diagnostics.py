"""Generate the static V0A.8 raw-GNSS diagnostic outputs."""

from __future__ import annotations

import csv
import html
import math
from dataclasses import dataclass
from pathlib import Path

from football_stat_tracker.data_model import (
    ContinuousGroundTruth,
    GroundTruthAlignment,
    TrackingSession,
)
from football_stat_tracker.gnss import total_gnss_distance_m
from football_stat_tracker.gnss_diagnostics import (
    CumulativeDistancePoint,
    GnssSegmentDiagnostic,
    HorizontalAccuracyStatistics,
    LocalGnssPoint,
    SegmentStatistics,
    calculate_distance_error,
    cumulative_gnss_distance,
    gnss_segment_diagnostics,
    local_gnss_coordinates,
    summarize_horizontal_accuracy,
    summarize_segments,
)
from football_stat_tracker.importers.walking import import_walking_session


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPOSITORY_ROOT / "data/raw/walking/data"
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "outputs/v0a8_gnss_diagnostics"
SESSION_PATHS = (
    "subject_14/14_2",
    "subject_14/14_6",
    "subject_16/16_2",
    "subject_17/17_0",
    "subject_18/18_0",
    "subject_8/8_4",
)

BLUE = "#2563eb"
ORANGE = "#ea580c"
RED = "#dc2626"
GREEN = "#15803d"
PURPLE = "#7e22ce"
GRAY = "#64748b"
LIGHT_GRAY = "#cbd5e1"
GRID = "#e2e8f0"
TEXT = "#0f172a"


@dataclass(frozen=True, slots=True)
class SessionDiagnostic:
    session: TrackingSession
    cumulative: tuple[CumulativeDistancePoint, ...]
    segments: tuple[GnssSegmentDiagnostic, ...]
    segment_statistics: SegmentStatistics
    accuracy_statistics: HorizontalAccuracyStatistics
    local_points: tuple[LocalGnssPoint, ...]
    raw_distance_m: float


class Svg:
    def __init__(self, width: int, height: int, title: str) -> None:
        self.width = width
        self.height = height
        self.title = title
        self.elements: list[str] = []

    def add(self, markup: str) -> None:
        self.elements.append(markup)

    def save(self, path: Path) -> None:
        content = "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
                f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">',
                f"<title>{html.escape(self.title)}</title>",
                '<rect width="100%" height="100%" fill="white"/>',
                '<style>text{font-family:Arial,sans-serif;fill:#0f172a}'
                '.axis{stroke:#334155;stroke-width:1}.grid{stroke:#e2e8f0;stroke-width:1}'
                '.plot-frame{fill:none;stroke:#94a3b8;stroke-width:1}</style>',
                *self.elements,
                "</svg>",
            ]
        )
        path.write_text(content, encoding="utf-8")


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    diagnostics = {
        relative_path.split("/")[-1]: _diagnose_session(
            import_walking_session(DATA_ROOT / relative_path)
        )
        for relative_path in SESSION_PATHS
    }
    _write_summary_csv(diagnostics)
    _write_segment_statistics_csv(diagnostics)
    _write_accuracy_statistics_csv(diagnostics)
    _write_extreme_segments_csv(diagnostics)
    _write_extreme_speed_segments_csv(diagnostics)
    _write_14_6_suspect_segments_csv(diagnostics["14_6"])
    _write_cumulative_figure(diagnostics)
    _write_trajectory_figure(diagnostics)
    _write_segment_figure(diagnostics)
    _write_accuracy_figure(diagnostics)
    _write_14_6_overview(diagnostics["14_6"])


def _diagnose_session(session: TrackingSession) -> SessionDiagnostic:
    segments = gnss_segment_diagnostics(session.gnss)
    return SessionDiagnostic(
        session=session,
        cumulative=cumulative_gnss_distance(session.gnss),
        segments=segments,
        segment_statistics=summarize_segments(segments),
        accuracy_statistics=summarize_horizontal_accuracy(session.gnss),
        local_points=local_gnss_coordinates(session.gnss),
        raw_distance_m=total_gnss_distance_m(session.gnss),
    )


def _write_summary_csv(diagnostics: dict[str, SessionDiagnostic]) -> None:
    path = OUTPUT_DIRECTORY / "session_distance_errors.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "session",
                "gnss_points",
                "duration_s",
                "gnss_distance_m",
                "reference_distance_m",
                "signed_error_m",
                "relative_error_percent",
                "ground_truth_type",
                "ground_truth_alignment",
                "metadata_fs_gnss_hz",
                "path_curvature",
            ]
        )
        for name, diagnostic in diagnostics.items():
            session = diagnostic.session
            reference = session.metadata.distance_reference_m
            error = calculate_distance_error(diagnostic.raw_distance_m, reference)
            duration = (
                session.metadata.test_end_raw_ms - session.metadata.test_start_raw_ms
            ) / 1000.0
            writer.writerow(
                [
                    name,
                    len(session.gnss),
                    duration,
                    diagnostic.raw_distance_m,
                    reference,
                    error.signed_m,
                    error.relative_percent,
                    session.ground_truth.type.value,
                    session.ground_truth.alignment.value,
                    session.metadata.fs_gnss_hz,
                    session.metadata.path_curvature,
                ]
            )


def _write_segment_statistics_csv(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    path = OUTPUT_DIRECTORY / "segment_statistics.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "session",
                "segment_count",
                "median_distance_m",
                "maximum_distance_m",
                "median_delta_t_s",
                "maximum_delta_t_s",
                "median_geometric_speed_mps",
                "maximum_geometric_speed_mps",
            ]
        )
        for name, diagnostic in diagnostics.items():
            summary = diagnostic.segment_statistics
            writer.writerow(
                [
                    name,
                    summary.count,
                    summary.median_distance_m,
                    summary.maximum_distance_m,
                    summary.median_delta_t_s,
                    summary.maximum_delta_t_s,
                    summary.median_geometric_speed_mps,
                    summary.maximum_geometric_speed_mps,
                ]
            )


def _write_accuracy_statistics_csv(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    path = OUTPUT_DIRECTORY / "horizontal_accuracy_statistics.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["session", "count", "median_m", "mean_m", "maximum_m"])
        for name, diagnostic in diagnostics.items():
            summary = diagnostic.accuracy_statistics
            writer.writerow(
                [name, summary.count, summary.median_m, summary.mean_m, summary.maximum_m]
            )


def _write_extreme_segments_csv(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    path = OUTPUT_DIRECTORY / "extreme_segments_top10.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "session",
                "rank_by_distance",
                "start_s",
                "end_s",
                "delta_t_s",
                "distance_m",
                "geometric_speed_mps",
                "start_accuracy_m",
                "end_accuracy_m",
            ]
        )
        for name, diagnostic in diagnostics.items():
            largest = sorted(
                diagnostic.segments, key=lambda segment: segment.distance_m, reverse=True
            )[:10]
            for rank, segment in enumerate(largest, start=1):
                writer.writerow(
                    [
                        name,
                        rank,
                        segment.start_timestamp_analysis_ms / 1000.0,
                        segment.end_timestamp_analysis_ms / 1000.0,
                        segment.delta_t_s,
                        segment.distance_m,
                        segment.geometric_speed_mps,
                        segment.start_horizontal_accuracy_m,
                        segment.end_horizontal_accuracy_m,
                    ]
                )


def _write_extreme_speed_segments_csv(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    path = OUTPUT_DIRECTORY / "extreme_speeds_top10.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "session",
                "rank_by_speed",
                "start_s",
                "end_s",
                "delta_t_s",
                "distance_m",
                "geometric_speed_mps",
                "start_accuracy_m",
                "end_accuracy_m",
            ]
        )
        for name, diagnostic in diagnostics.items():
            valid_speeds = [
                segment
                for segment in diagnostic.segments
                if segment.geometric_speed_mps is not None
            ]
            fastest = sorted(
                valid_speeds,
                key=lambda segment: segment.geometric_speed_mps,
                reverse=True,
            )[:10]
            for rank, segment in enumerate(fastest, start=1):
                writer.writerow(
                    [
                        name,
                        rank,
                        segment.start_timestamp_analysis_ms / 1000.0,
                        segment.end_timestamp_analysis_ms / 1000.0,
                        segment.delta_t_s,
                        segment.distance_m,
                        segment.geometric_speed_mps,
                        segment.start_horizontal_accuracy_m,
                        segment.end_horizontal_accuracy_m,
                    ]
                )


def _write_14_6_suspect_segments_csv(diagnostic: SessionDiagnostic) -> None:
    path = OUTPUT_DIRECTORY / "14_6_initial_suspect_segments.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "start_s",
                "end_s",
                "delta_t_s",
                "distance_m",
                "geometric_speed_mps",
                "start_accuracy_m",
                "end_accuracy_m",
                "diagnostic_note",
            ]
        )
        for segment in diagnostic.segments:
            if segment.end_timestamp_analysis_ms <= 3_918.0:
                note = (
                    "initial relocation from low-accuracy fix"
                    if segment.distance_m > 80.0
                    else "initial acquisition/stabilization period"
                )
                writer.writerow(
                    [
                        segment.start_timestamp_analysis_ms / 1000.0,
                        segment.end_timestamp_analysis_ms / 1000.0,
                        segment.delta_t_s,
                        segment.distance_m,
                        segment.geometric_speed_mps,
                        segment.start_horizontal_accuracy_m,
                        segment.end_horizontal_accuracy_m,
                        note,
                    ]
                )


def _write_cumulative_figure(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    svg = _new_six_panel_svg("Distance GNSS cumulée dans le temps")
    for panel_index, (name, diagnostic) in enumerate(diagnostics.items()):
        series = [
            (
                "GNSS brut",
                BLUE,
                [
                    (point.timestamp_analysis_ms / 1000.0, point.distance_m)
                    for point in diagnostic.cumulative
                ],
            )
        ]
        ground_truth = diagnostic.session.ground_truth
        if (
            isinstance(ground_truth, ContinuousGroundTruth)
            and ground_truth.alignment
            not in (
                GroundTruthAlignment.NOT_ALIGNED_TO_TEST_START,
                GroundTruthAlignment.UNAVAILABLE,
            )
            and all(
                sample.distance_analysis_m is not None
                for sample in ground_truth.samples
            )
        ):
            series.append(
                (
                    "Référence continue",
                    ORANGE,
                    [
                        (
                            sample.timestamp_analysis_ms / 1000.0,
                            sample.distance_analysis_m,
                        )
                        for sample in ground_truth.samples
                    ],
                )
            )
        subtitle = f"{name} — GT {ground_truth.type.value}, {ground_truth.alignment.value}"
        _line_panel(svg, *_panel_geometry(panel_index), subtitle, "temps [s]", "distance [m]", series)
    svg.save(OUTPUT_DIRECTORY / "cumulative_distance_over_time.svg")


def _write_trajectory_figure(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    svg = _new_six_panel_svg("Trajectoires GNSS brutes en coordonnées locales")
    for panel_index, (name, diagnostic) in enumerate(diagnostics.items()):
        _trajectory_panel(
            svg,
            *_panel_geometry(panel_index),
            f"{name} — courbure {diagnostic.session.metadata.path_curvature}",
            diagnostic.local_points,
        )
    svg.save(OUTPUT_DIRECTORY / "gnss_trajectories_local_xy.svg")


def _write_segment_figure(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    svg = _new_six_panel_svg("Distance de chaque segment GNSS brut")
    for panel_index, (name, diagnostic) in enumerate(diagnostics.items()):
        points = [
            (segment.end_timestamp_analysis_ms / 1000.0, segment.distance_m)
            for segment in diagnostic.segments
        ]
        maximum = diagnostic.segment_statistics.maximum_distance_m
        title = f"{name} — max {maximum:.3f} m"
        _line_panel(
            svg,
            *_panel_geometry(panel_index),
            title,
            "temps de fin [s]",
            "distance segment [m]",
            [("segment", PURPLE, points)],
        )
    svg.save(OUTPUT_DIRECTORY / "segment_distance_over_time.svg")


def _write_accuracy_figure(
    diagnostics: dict[str, SessionDiagnostic]
) -> None:
    svg = _new_six_panel_svg("Horizontal accuracy GNSS dans le temps")
    for panel_index, (name, diagnostic) in enumerate(diagnostics.items()):
        points = [
            (sample.timestamp_analysis_ms / 1000.0, sample.horizontal_accuracy_m)
            for sample in diagnostic.session.gnss
            if sample.horizontal_accuracy_m is not None
            and math.isfinite(sample.horizontal_accuracy_m)
        ]
        summary = diagnostic.accuracy_statistics
        title = f"{name} — médiane {summary.median_m:.3f} m, max {summary.maximum_m:.3f} m"
        _line_panel(
            svg,
            *_panel_geometry(panel_index),
            title,
            "temps [s]",
            "horizontal accuracy [m]",
            [("accuracy", GREEN, points)],
        )
    svg.save(OUTPUT_DIRECTORY / "horizontal_accuracy_over_time.svg")


def _write_14_6_overview(diagnostic: SessionDiagnostic) -> None:
    svg = Svg(1400, 1390, "Diagnostic détaillé de la session 14_6")
    svg.add('<text x="700" y="32" text-anchor="middle" font-size="24" font-weight="bold">Diagnostic détaillé — 14_6</text>')
    positions = ((30, 55), (710, 55), (30, 500), (710, 500), (30, 945), (710, 945))
    panel_size = (660, 400)
    marker_time = 2.918

    cumulative_points = [
        (point.timestamp_analysis_ms / 1000.0, point.distance_m)
        for point in diagnostic.cumulative
    ]
    _line_panel(
        svg,
        *positions[0],
        *panel_size,
        "Distance cumulée GNSS brute (sans courbe GT : NOT_ALIGNED)",
        "temps [s]",
        "distance [m]",
        [("GNSS brut", BLUE, cumulative_points)],
        vertical_markers=[(marker_time, "saut 83,912 m")],
    )
    _trajectory_panel(
        svg,
        *positions[1],
        *panel_size,
        "Trajectoire locale complète — segment initial en rouge",
        diagnostic.local_points,
        highlighted_prefix=5,
    )
    segment_distance = [
        (segment.end_timestamp_analysis_ms / 1000.0, segment.distance_m)
        for segment in diagnostic.segments
    ]
    _line_panel(
        svg,
        *positions[2],
        *panel_size,
        "Distance par segment",
        "temps de fin [s]",
        "distance [m]",
        [("segment", PURPLE, segment_distance)],
        vertical_markers=[(marker_time, "83,912 m")],
    )
    speeds = [
        (segment.end_timestamp_analysis_ms / 1000.0, segment.geometric_speed_mps)
        for segment in diagnostic.segments
        if segment.geometric_speed_mps is not None
    ]
    _line_panel(
        svg,
        *positions[3],
        *panel_size,
        "Vitesse géométrique diagnostique",
        "temps de fin [s]",
        "vitesse [m/s]",
        [("distance / Δt", RED, speeds)],
        vertical_markers=[(marker_time, "45,090 m/s")],
    )
    accuracy = [
        (sample.timestamp_analysis_ms / 1000.0, sample.horizontal_accuracy_m)
        for sample in diagnostic.session.gnss
        if sample.horizontal_accuracy_m is not None
    ]
    _line_panel(
        svg,
        *positions[4],
        *panel_size,
        "Horizontal accuracy",
        "temps [s]",
        "accuracy [m]",
        [("accuracy", GREEN, accuracy)],
        vertical_markers=[(marker_time, "fin du saut")],
    )
    early_points = tuple(
        point for point in diagnostic.local_points if point.timestamp_analysis_ms <= 10_000
    )
    _trajectory_panel(
        svg,
        *positions[5],
        *panel_size,
        "Zoom spatial des 10 premières secondes",
        early_points,
        highlighted_prefix=5,
    )
    svg.save(OUTPUT_DIRECTORY / "14_6_diagnostic_overview.svg")


def _new_six_panel_svg(title: str) -> Svg:
    svg = Svg(1400, 1120, title)
    svg.add(
        f'<text x="700" y="32" text-anchor="middle" font-size="24" '
        f'font-weight="bold">{html.escape(title)}</text>'
    )
    return svg


def _panel_geometry(index: int) -> tuple[int, int, int, int]:
    return 30 + (index % 2) * 680, 55 + (index // 2) * 350, 660, 315


def _line_panel(
    svg: Svg,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    x_label: str,
    y_label: str,
    series: list[tuple[str, str, list[tuple[float, float]]]],
    vertical_markers: list[tuple[float, str]] | None = None,
) -> None:
    margin_left, margin_right, margin_top, margin_bottom = 72, 20, 42, 54
    plot_x = x + margin_left
    plot_y = y + margin_top
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    all_points = [point for _, _, points in series for point in points]
    if not all_points:
        return
    x_values = [point[0] for point in all_points]
    y_values = [point[1] for point in all_points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(0.0, min(y_values)), max(y_values)
    if x_max == x_min:
        x_max = x_min + 1.0
    if y_max == y_min:
        y_max = y_min + 1.0
    y_max *= 1.05

    sx = lambda value: plot_x + (value - x_min) / (x_max - x_min) * plot_width
    sy = lambda value: plot_y + plot_height - (value - y_min) / (y_max - y_min) * plot_height

    svg.add(f'<text x="{x + width / 2}" y="{y + 20}" text-anchor="middle" font-size="15" font-weight="bold">{html.escape(title)}</text>')
    for tick in range(6):
        fraction = tick / 5
        tick_x = plot_x + fraction * plot_width
        tick_y = plot_y + plot_height - fraction * plot_height
        x_value = x_min + fraction * (x_max - x_min)
        y_value = y_min + fraction * (y_max - y_min)
        svg.add(f'<line class="grid" x1="{tick_x:.2f}" y1="{plot_y}" x2="{tick_x:.2f}" y2="{plot_y + plot_height}"/>')
        svg.add(f'<line class="grid" x1="{plot_x}" y1="{tick_y:.2f}" x2="{plot_x + plot_width}" y2="{tick_y:.2f}"/>')
        svg.add(f'<text x="{tick_x:.2f}" y="{plot_y + plot_height + 19}" text-anchor="middle" font-size="11">{_format_tick(x_value)}</text>')
        svg.add(f'<text x="{plot_x - 8}" y="{tick_y + 4:.2f}" text-anchor="end" font-size="11">{_format_tick(y_value)}</text>')
    svg.add(f'<rect class="plot-frame" x="{plot_x}" y="{plot_y}" width="{plot_width}" height="{plot_height}"/>')

    for label, color, points in series:
        coordinates = " ".join(f"{sx(px):.2f},{sy(py):.2f}" for px, py in points)
        svg.add(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>')
    if len(series) > 1:
        legend_x = plot_x + 8
        for label, color, _ in series:
            svg.add(f'<line x1="{legend_x}" y1="{plot_y + 14}" x2="{legend_x + 22}" y2="{plot_y + 14}" stroke="{color}" stroke-width="3"/>')
            svg.add(f'<text x="{legend_x + 28}" y="{plot_y + 18}" font-size="11">{html.escape(label)}</text>')
            legend_x += 145

    for marker_x, label in vertical_markers or []:
        if x_min <= marker_x <= x_max:
            mapped_x = sx(marker_x)
            svg.add(f'<line x1="{mapped_x:.2f}" y1="{plot_y}" x2="{mapped_x:.2f}" y2="{plot_y + plot_height}" stroke="{RED}" stroke-width="1.5" stroke-dasharray="5 4"/>')
            svg.add(f'<text x="{mapped_x + 5:.2f}" y="{plot_y + 14}" font-size="11" fill="{RED}">{html.escape(label)}</text>')

    svg.add(f'<text x="{plot_x + plot_width / 2}" y="{y + height - 8}" text-anchor="middle" font-size="12">{html.escape(x_label)}</text>')
    svg.add(f'<text x="{x + 15}" y="{plot_y + plot_height / 2}" text-anchor="middle" font-size="12" transform="rotate(-90 {x + 15} {plot_y + plot_height / 2})">{html.escape(y_label)}</text>')


def _trajectory_panel(
    svg: Svg,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    points: tuple[LocalGnssPoint, ...],
    highlighted_prefix: int = 0,
) -> None:
    if not points:
        return
    margin_left, margin_right, margin_top, margin_bottom = 72, 25, 42, 54
    plot_x = x + margin_left
    plot_y = y + margin_top
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    min_x, max_x = min(p.x_m for p in points), max(p.x_m for p in points)
    min_y, max_y = min(p.y_m for p in points), max(p.y_m for p in points)
    range_x = max(max_x - min_x, 1.0)
    range_y = max(max_y - min_y, 1.0)
    scale = min(plot_width / (range_x * 1.08), plot_height / (range_y * 1.08))
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    sx = lambda value: plot_x + plot_width / 2 + (value - center_x) * scale
    sy = lambda value: plot_y + plot_height / 2 - (value - center_y) * scale

    svg.add(f'<text x="{x + width / 2}" y="{y + 20}" text-anchor="middle" font-size="15" font-weight="bold">{html.escape(title)}</text>')
    svg.add(f'<rect class="plot-frame" x="{plot_x}" y="{plot_y}" width="{plot_width}" height="{plot_height}"/>')
    coordinates = " ".join(f"{sx(p.x_m):.2f},{sy(p.y_m):.2f}" for p in points)
    svg.add(f'<polyline points="{coordinates}" fill="none" stroke="{BLUE}" stroke-width="1.6" stroke-linejoin="round"/>')
    if highlighted_prefix > 1:
        prefix = points[:highlighted_prefix]
        prefix_coordinates = " ".join(f"{sx(p.x_m):.2f},{sy(p.y_m):.2f}" for p in prefix)
        svg.add(f'<polyline points="{prefix_coordinates}" fill="none" stroke="{RED}" stroke-width="3" stroke-linejoin="round"/>')
    svg.add(f'<circle cx="{sx(points[0].x_m):.2f}" cy="{sy(points[0].y_m):.2f}" r="4" fill="{GREEN}"/>')
    svg.add(f'<circle cx="{sx(points[-1].x_m):.2f}" cy="{sy(points[-1].y_m):.2f}" r="4" fill="{RED}"/>')
    svg.add(f'<text x="{plot_x + plot_width / 2}" y="{y + height - 8}" text-anchor="middle" font-size="12">x local [m]</text>')
    svg.add(f'<text x="{x + 15}" y="{plot_y + plot_height / 2}" text-anchor="middle" font-size="12" transform="rotate(-90 {x + 15} {plot_y + plot_height / 2})">y local [m]</text>')
    svg.add(f'<text x="{plot_x + 8}" y="{plot_y + 16}" font-size="11">étendue x={range_x:.1f} m, y={range_y:.1f} m</text>')


def _format_tick(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1000:
        return f"{value:.0f}"
    if absolute >= 100:
        return f"{value:.0f}"
    if absolute >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


if __name__ == "__main__":
    main()
