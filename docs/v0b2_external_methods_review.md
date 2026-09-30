# V0B.2.2 — External SoccerMon methods review

Research date: 2026-09-30. Local baseline: `2659be5`.

## Executive findings

1. **Distance methods are not interchangeable.** CriticalSpeed integrates vendor
   speed with a fixed 0.1 seconds per retained row; Lars Hoel's notebook sums
   coordinate distances after row decimation and quality filtering. Neither is
   independent ground truth. Fixed durations, removed rows, omitted segments and
   unreported gaps can change the answer substantially.
2. **There is no shared sprint definition.** CriticalSpeed counts upward crossings
   of 21 km/h without a minimum duration. Hoel extracts events above 5.5 m/s with a
   one-second duration requirement, but first removes low-speed observations,
   potentially joining separate efforts. The dashboard displays stored events;
   its sprint page does not detect them. Athlelorien's directional “runs” are
   turning-angle segments, not high-speed sprint events.
3. **The IMU clock uncertainty remains unresolved.** The reviewed consumers
   deduplicate or subsample GNSS views, use ordered IMU differences, or aggregate
   coarsely. None supplies the acquisition/export code, finer sample clock,
   packet identifier or synchronization specification needed to establish exact
   timing of the ten different IMU vectors sharing a timestamp. Acceleration
   magnitude, changes in accelerometer axes, vendor `inst_acc_impulse`, and
   change in running speed must remain separate measurements.

These are conclusions from the code references below, not endorsements of
external outputs. No importer, filter, metric, timestamp or test was modified.

## Scope, evidence and reproducibility

Read [V0B preparation](v0b_preparation_report.md),
[V0B.1](v0b1_soccermon_real_data_report.md),
[V0B.2](v0b2_soccermon_importer_report.md), and
[the IMU timestamp investigation](v0b2_imu_timestamp_investigation.md).
There is no standalone V0A Markdown report in this checkout. Its existing
evaluation reports are `outputs/v0a8_gnss_diagnostics/session_distance_errors.csv`
and `outputs/v0a9_gnss_robust/robust_distance_evaluation.csv`; these, the numerical
source, evaluation script and relevant tests were inspected.

The working tree was clean. Existing local commits include `9969661` (V0A and
V0B.1), `5d3b3db`, `e382b04`, `4c35c43` (V0B.2), and `2659be5` (IMU investigation).
The baseline full suite passed **81 tests, no skips**.

Evidence terminology:

- **DOCUMENTED:** a primary publication, manufacturer statement or maintainer
  discussion explicitly says this.
- **OBSERVED / implemented:** directly visible in the pinned source or existing
  local analysis. Static code inspection establishes instructions, not successful
  execution or scientific validity.
- **INFERRED:** a consequence or interpretation of those instructions.
- **UNKNOWN / undocumented:** behavior, provenance or scientific interpretation
  is not established by the inspected sources.

Public GitHub recursive trees, branch/commit metadata and actual source files
were inspected. Downloaded source stayed in `/tmp`, outside this repository.
Git blob hashes were checked against API metadata/tree entries. External
programs were not executed, and no dataset, external code or generated output
was added here. Notebook cell references below are **one-based positions in
`cells`**, including Markdown cells, at the pinned commit.

Searches included GitHub repositories containing `soccermon`, public issues for
`soccermon timestamp`, and web queries combining SoccerMon with timestamp, IMU,
sprints, `inst_acc_impulse` and duplicate timestamps. Publication code-availability
links and dashboard issues led to further implementations. This is a bounded
public-source review, not proof that no private or unindexed method exists.

### Reviewed snapshots

| Repository | Branch and pinned commit | Relevant scope |
|---|---|---|
| [danielfrenandez/CriticalSpeed_shiny][critical-tree] | `master`, `c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1` | Four R scripts and `app.R`; objective summary, moving windows and IMU load |
| [simulamet-host/soccer-dashboard][dashboard-dev-tree] | default `dev`, `dc2fb4a4eeb47a149a7223cccc3f485e48031625` | GPS demo, database consumers; main `f1f3b4307b3d177f4a0688c7c461fbc63ec812bc` also inspected |
| [soccer-dashboard, `v2`][dashboard-v2-tree] | `92862d13ad711517e60e283c349d145efa775918` | Real Parquet mobility view; stored high-intensity-event visualization; projection helpers/tests |
| [simula/soccermon][soccermon-tree] | `main`, `eaa6c888845cda60f30e8f86ebfc48a526662ffb` | Subjective loader, player/team structures, pickle generation and tests |
| [simula/pmsys, Lars Hoel][hoel-tree] | `main`, `3ad81b01572b5633a95a37cdf6dff0e382a14047` | `lars-hoel/FeatureExtraction.ipynb`, `GPSvisualization.ipynb` |
| [framewave-lab/Athlelorien][athle-tree] | `68634b9defe08a0b3f2c179b2a27280b29f29d46` | Loader, production paper cache builder, pitch conversion, player selection, transport and velocity functions |
| [s-ahmed-01/Soccermon-Project][spark-tree] | `c5cdf284d89473a50b2f72c78dedf1f9bedf7047` | `pyspark.py`, matching notebook cell 1, `EDA.py` |
| [idaejin/latent-memory-states][latent-tree] | `4e343ffb94e9cc3eba5b17ac83fc7c3f60a7e9ec` | Daily SQLite feature consumption; upstream objective aggregation unavailable in inspected code |
| [LGURI/injury-forecaster][injury-tree] | `cbcee3408b41251434cbf87f04600f174c72d112` | Actual notebook uses subjective CSV data; objective methods advertised in README not implemented there |

## Comparison of objective implementations

References in the following sections give exact paths and commit-pinned lines.
All cells below describe **implemented instructions**; acquisition semantics and
accuracy remain unknown unless explicitly documented separately.

| Research question | CriticalSpeed | Dashboard `v2` | Hoel feature notebook | Athlelorien paper pipeline | Ahmed Spark prototype |
|---|---|---|---|---|---|
| Repeated IMU timestamps | Full source-order accelerometer differences; no new times | Mobility keeps first row per time; no IMU analysis | Every tenth row for GNSS; IMU axes not loaded | One-second aggregation; no fine IMU clock | All rows retained; sorts by time with tied order unspecified |
| Repeated GNSS exports | First row per unique `time` | First row per unique `time` | Index stride 10, not timestamp grouping | First observation per second by default | Adjacent-coordinate Haversine, no deduplication |
| Invalid `(0,0)` | No coordinate test in speed summary | Drops either zero axis in mobility | Drops either zero axis | Rejects zero pair/range/missing coordinates in pitch attachment | No explicit rejection |
| Distance | Sum `speed × 0.1` | Displays database values/paths; no session total calculation | Haversine in km; zeroes steps >100 m; session loop omits last step | Sum planar steps within directional runs, in metres; not a session-total report | Sum Haversine in metres |
| Speed / acceleration | Vendor speed; accelerometer difference norm for load | Stored `Average_speed`; legacy plots vendor speed/impulse | Vendor speed capped at 9.5 m/s; vendor impulse in metabolic-power formula | Coordinate displacement / observed elapsed time; no physical acceleration metric in reviewed transport path | Raw accel/gyro norms; no running-speed derivative |
| Sprints | Up-crossings >21 km/h | Displays `LH_HIR` rows; no detector | >5.5 m/s events, duration ≥1 s after filtering | Turning-angle runs, not sprints | Not implemented |
| Vendor vs coordinate speed | Vendor only for distance/events/windows | Database/native fields; projection for visualization | Vendor for events/speed, coordinates for distance | Geometry-derived velocities for collective analysis | Coordinates for distance; vendor speed unused |
| Missing / gaps / noise | `na.rm` in summaries; no gap boundary; row-count windows | Whole-row `dropna`, zero-axis removal; map-specific pitch checks | Quality cuts, speed cap, >100 m zeroing; no time-gap break | Empty bins unfilled; phase/identity/gap splits; position/active-player gates | No null/zero/gap guards in Haversine UDF |
| Accelerometer / gyroscope | Accelerometer differences /100; gyro unused | Legacy plots axes; no physical IMU metric | Not loaded for feature extraction | Not used in reviewed GNSS transport pipeline | Sums magnitudes, misleadingly named “change” |

### 1. CriticalSpeed_shiny

**OBSERVED / implemented:** [scripts/2_load_clean_proces_data.R][critical-summary],
`create_database_fast()` / `resume_file()`, lines 53–110:

- Lines 65–69 keep the **first row for each time value in the file**, sort by
  time, and convert native speed from m/s to km/h using 3.6. This is a GNSS
  analysis view; the full frame remains available to its IMU calculation.
- Lines 78–83 calculate total distance as `Σ speed × 0.1`, distance above
  21 km/h using the same rectangles, and sprint count when current speed is
  >21 km/h and the previous value is ≤21. The initial previous value is zero.
  There is no minimum effort duration, recovery duration, hysteresis or gap
  reset. An initially high speed counts as an event.
- Lines 85–93 take consecutive raw `accl_x/y/z` differences in source order,
  sum their Euclidean norms, then divide by 100. This is a PlayerLoad-like
  ordered variation statistic. It does not divide by elapsed time, estimate
  forward acceleration, remove gravity or use gyroscope axes. Its divisor does
  not prove a 100 Hz sample clock or vendor-equivalent calibration.
- Summaries skip NAs using `na.rm`; positive heart rates are used for the mean.
  The metric path has no geographic, satellite, `hacc`, `hdop`, signal-quality,
  negative-speed or finite-value screening. NA exclusion is not a noise filter.
  Original Parquet files are deleted by `load_data()` at line 30 after RDS
  conversion; that workflow is unsuitable for our raw-data provenance policy.

**INFERRED limitations:** fixed 0.1-second weighting ignores actual missing
clock groups and endpoint conventions. It does not multiply distance by ten
because it first deduplicates time. Time-only deduplication can discard
conflicting fields, and sorting conceals original reversals. Threshold chatter
can produce many counted sprints; absent low-speed observations can conceal
recovery. Vendor speed may already be filtered and is not an independent
reference for geometry-derived speed.

**OBSERVED:** [scripts/3_moving_averages.R][critical-windows], lines 31–49 and
109–134, again deduplicates by time, then assumes **20 rows per second** for
rolling windows. [app.R][critical-app], lines 160–183, repeats this in uploaded
session analysis. **INFERRED:** for our observed uninterrupted 100 ms candidate
stream, a labelled 3-second window contains 60 rows spanning 5.9 seconds,
approximately six seconds of row-weighted exposure. Larger windows inherit
the mismatch; gaps lengthen their actual spans further. This conflicts with
both the summary's 0.1-second weighting and our local timestamp evidence.
It does not establish a different physical sampling rate in these files.

The cumulative-sum window implementation has no NA repair, so one missing speed
can contaminate later windows. The app's separate relative repetition count
([app.R, lines 596–601][critical-repetitions]) counts entries above 90% of a
session's maximum moving mean, excluding an initially above-threshold sequence.
It is not the same metric as `sprints_21`. [scripts/4_df_historic_ind_max.R][critical-fit]
also excludes sessions using `MM_3 < 39`; this is a session-level heuristic,
not sensor-level GNSS validation. No running-speed acceleration or exact IMU
timestamp reconstruction was found in these scripts/app.

### 2. soccer-dashboard: branch-specific behavior

The default branch alone gives an incomplete impression. [PR #115][dashboard-pr]
merged the GPS-page changes into `v2`, not `dev`.

**OBSERVED / implemented, `v2`:**
[components/analysis/analysis_gps_mobility.py][dashboard-mobility], lines 15–26,
keeps the first row of each `time`, drops rows with an NA in **any column**, and
removes either-zero-axis coordinates. It displays only the 5–10% slice of the
remaining rows for performance. Lines 116–129 subsample again for animation.
These are visualization choices, not a sampling-frequency measurement or a
safe IMU representation. A missing optional field can remove an otherwise
usable position; the first-row operation can discard within-time conflicts.

[components/analysis/analysis_gps_sprint.py][dashboard-sprints], lines 7–11 and
41–49, fetches `LH_HIR` from MySQL and displays stored start/end coordinates and
average speed. Its plots join event endpoints, not the measured event path.
[utils/data_fetcher.py][dashboard-fetch], lines 7–37, is a SQL consumer, not the
producer of events or distances. **UNKNOWN:** whether the deployed database
was built with exactly Hoel's checked-in notebook version. Matching table/field
names and [issue #101's resource links][dashboard-issue] establish a relevant
lead, not end-to-end provenance.

[utils/gps.py][dashboard-projection], lines 178–199, uses WGS84 geodesic
distance/bearing for pitch geometry; lines 293–365 offer equirectangular,
distance/bearing, Web Mercator and UTM display transformations. The sprint view
selects UTM. These helpers do not calculate total session distance or detect
sprints. `find_pitch()` uses bounding boxes of a small predefined pitch list;
unknown/off-pitch positions may prevent plotting. The sprint page's
`check_range()` call is commented out (line 82), so that optional diagnostic is
not an active cleaning rule. [tests/utils/test_gps.py][dashboard-tests] tests
geometry/projection/map helpers, not sprint detection, timing or distance totals.

**OBSERVED, `dev`:** [src/pages/gps_information.py][dashboard-demo], lines 53–91,
comments out real SQL reads, creates 50 random demo rows and computes Haversine
distance from each coordinate to **itself**, yielding zero; lines 406–421 contain
hardcoded report values. This is a placeholder, not a SoccerMon estimator.
[src/pages/player_gps_report.py][dashboard-legacy] reads SQL and plots vendor
`speed`, `inst_acc_impulse`, stored `distance` and IMU axes; it contains no
producer for those derived database columns. Main's
[streamlit_app/app.py][dashboard-main] routes subjective-data pages. These
branches must not be conflated with `v2` or used to infer upstream algorithms.

### 3. Lars Hoel's objective feature extraction

Exact source: [simula/pmsys, lars-hoel/FeatureExtraction.ipynb][hoel-features].
[GPSvisualization.ipynb][hoel-visual] only consumes event CSVs and plots/subsamples
tracks. The dashboard maintainer explicitly links both the code directory and
[Hoel's 2023 thesis][hoel-thesis] in issue #101. The algorithms below were read
from notebook source, not inferred from the thesis or database.

**OBSERVED / implemented:**

- **Cell 6:** reads time, position, vendor speed/impulse, identity and quality;
  keeps every tenth row (`iloc[::10]`). Requires both coordinate axes nonzero,
  `hacc < 3`, `hdop < 10`, `signal_quality > 100`. This is index decimation, not
  proof of GNSS freshness or timestamp deduplication.
- **Cells 2 and 5:** Haversine returns **kilometres**, with any individual step
  >0.1 km replaced by zero. Session distance is added only when **both** latitude
  and longitude change. Its loop condition also omits the final segment.
  Average/top speeds use vendor speed capped at 9.5 m/s; accumulation excludes
  the final two observations but average divides by `n−1`.
- **Cell 9:** the event input additionally caps speed at 9.5, uses `hdop < 3`,
  `signal_quality > 200`, and **removes speeds ≤5 m/s before detection**.
- **Cell 8:** starts an event at speed >5.5 m/s when the preceding retained
  speed is <5.5 (or the row is initial), scans until a retained speed ≤5.5,
  and keeps durations with `duration.seconds >= 1`. Event distance is converted
  from km to metres. No separate count is calculated; stored event-row count
  would be the count of extracted events.
- **Cell 3:** uses vendor `inst_acc_impulse` and speed in a metabolic-power
  formula, without deriving running acceleration from GNSS or IMU. It returns
  on the first positive impulse inside the loop, rather than averaging the
  session; its `90 - atan(...)` combines a degree-like constant with radian
  trigonometric functions. This is not a validated acceleration metric.

**INFERRED limitations:**

- Taking every tenth row assumes a constant source-export multiplicity. Our
  incomplete first/last groups and timestamp gaps make the alignment arbitrary;
  a conflict or a future irregular group can be skipped. This does not imply
  loss of a group in every local file, nor guarantee one fresh fix per selection.
- Requiring both coordinates to change loses genuine movement along a constant
  latitude or longitude. A fixed 100 m rejection is insensitive to elapsed
  time and silently hides the displacement. Coordinate/quality filtering can
  create new long links; there is no explicit outage report or gap boundary.
- Removing low speeds can join separated efforts: retained high-speed rows
  before and after a removed recovery interval can appear as one event.
  Quality removals cause the same continuity problem. A preceding speed
  **exactly** 5.5 also fails the next event's strict start condition.
- The event accumulator omits the starting row's speed and includes the stopping
  row's speed and segment. At a detected stop, its time endpoint is the preceding
  row, but geographic endpoint is the stopping row. Consequently duration, mean speed and path
  extent need not describe the same interval. Assigning `i = j` inside a Python
  `for` loop does not advance the outer iterator.
- The notebook hardcodes filename substring positions for identity/date, and
  duration parsing has no midnight/clock-reversal policy. Missing-value and
  empty-frame handling is incomplete. Quality code units/threshold validity,
  original row-order guarantee and vendor filtering remain **UNKNOWN**.

This is useful evidence of earlier choices, not a reason to adopt their
thresholds or silent data removal. No IMU axes, sample counter, per-packet clock
or sub-100 ms reconstruction appears in this feature pipeline.

### 4. Athlelorien: explicit coarse GNSS analysis

The primary [September 2026 preprint][athle-paper] links this repository and
describes one-second GNSS transport analysis. It does not validate fine IMU
timing or football sprint events.

**OBSERVED / implemented:** [src/utils/day_loader.py][athle-loader], lines
99–179, combines filename date and time-of-day with a calculated Norwegian
one/two-hour offset, sorts, and defaults to `resample("1s").first()` per file.
An optional branch averages numeric columns. Empty bins are not interpolated
or forward-filled. Pandas `first()` can choose the first non-null value
**per column**, so with missing data an aggregate need not be one intact source
row. Bin labels and coarse selected values do not recover IMU sample times.
The timezone interpretation is an analysis assumption, not clock evidence.

The paper production call chain is
[analysis/levy_paper/scripts/build_multiseason_data_cache.py][athle-cache],
lines 164–179 and 330–364: load the one-second view, calibrate/project a pitch,
label match phases and active players, then build transport tables.
[src/utils/pitch_calibration.py][athle-pitch], lines 262–330, rejects missing,
out-of-range and zero-pair positions, and projects to a rotated local plane
using approximately 111,320 m/degree and the pitch-centre latitude. It includes
heuristic coordinate scaling; we already have documented decimal-degree source
coordinates and should not import that heuristic.

[src/utils/trajectory_stats.py][athle-paths], lines 1510–1656 and 2443–2539,
keeps match/phase/team/source/player identities separate, drops unparseable
time/coordinates, splits paths at observed gaps >2 seconds, and retains paths
with at least 30 observations. Gaps ≤2 seconds can still be bridged. Upstream
[src/utils/player_status.py][athle-status], lines 281–310, applies finite-coordinate
and pitch-depth gates in its active-XI selection; this is not an `hacc`/`hdop`
filter. Those match/selection rules are inappropriate for arbitrary training
sessions without independent activity labels.

[src/utils/collective_stats.py][athle-velocity], lines 130–160, computes planar
velocity as backward coordinate difference divided by **observed** elapsed
seconds within player paths; zero intervals become NaN. Zero/undefined headings
are excluded from collective direction statistics. This uses geometry rather
than vendor speed; exclusion of undefined heading must not become exclusion of
stationary periods in our total-duration or mean-speed metrics.

[src/utils/trajectory_stats.py, compute_turn_runs()][athle-runs], lines 132–240,
segments by change in displacement direction, skips displacement vectors
≤10⁻⁶ m for turning, sums planar segment lengths, and divides length by actual
run duration for mean speed. The production call uses **30°** from
[analysis/levy_paper/util/paper_utils.py][athle-params], line 61; a helper default
of 35° must not be mistaken for the paper configuration. These are directional
runs, **not threshold-defined sprints**. The reviewed path does not derive
physical acceleration or use accelerometer/gyroscope measurements.

**INFERRED:** explicit identity boundaries, observed-time denominators and gap
audits are worth testing. One-second selection suppresses short events and
curved-path detail; it is not sufficient validation for peak sprint speed or
short acceleration efforts. Position noise remains relevant even after pitch
gating. The paper documents smoothing/low-speed-guard sensitivity analyses, but
its production configuration has no temporal smoothing; those results are not
a calibrated filter for our nine files.

### 5. Ahmed's Spark prototype

Exact source: [pyspark.py][spark-code], lines 11–53; the same instructions appear
in [pyspark.ipynb][spark-notebook], cell 1.

**OBSERVED / implemented instructions:** loads a month of Parquet files,
partitions by player, orders by `time`, applies lagged-coordinate Haversine
with radius 6,371,000 m, then groups by player and `to_date(time)` to sum
distance. There is no GNSS deduplication, zero-pair/quality test or time-gap
policy. `accel_change` and `gyro_change` are **vector magnitudes**, not
differences; their sums are neither physical acceleration changes nor integrated
rotation. No speed calculation or sprint detector is present.

**OBSERVED defects:** `Window` is used without an import in both files; the
Haversine UDF has no guard for the first lag's null coordinates. Thus this is
not an established runnable estimator as checked in. Its comment assumes that
`time` includes date, unlike our actual time-only strings. Ordering and lagging
across sessions before daily aggregation can mix different recordings and has
no deterministic tie-breaker for the ten same-time rows. [EDA.py][spark-eda]
only reads files and plots columns versus time.

**INFERRED:** identical repeated positions add zero-length Haversine segments;
their repetition does **not by itself multiply geometric distance by ten**.
However `(0,0)` excursions, position noise, time-only session mixing and conflicts
can corrupt distance. Summing IMU magnitudes weights row counts and has no
demonstrated time, gravity or orientation interpretation.

### 6. Repositories without the requested raw objective algorithms

- **simula/soccermon:** [preprocessing/read_in_data.py][soccermon-reader],
  [preprocessing/data_loader.py][soccermon-model] and
  [preprocessing/run_team_pickle_generation.py][soccermon-pickle] process
  subjective training/wellness/injury reports and build player/team pickles.
  The complete pinned tree and loader tests contain no objective Parquet
  acquisition/conversion, repeated-IMU-time handling, GNSS deduplication,
  coordinate validity rule, distance/speed/acceleration/sprint estimator or
  IMU-axis analysis. This confirms a scoped absence in this snapshot and
  improves on the incomplete tree retrieval reported in V0B.2.1.
- **idaejin/latent-memory-states:** [memory_reps/windows.py][latent-windows],
  lines 15–40, consumes daily `analysis_player_day` SQLite fields including
  `external_speed_sum`, `external_inst_acc_impulse_sum` and objective duration.
  Lines 67–77 and 139–157 retain finite-value observation masks and zero-fill
  missing daily features for model input. These masks are a useful distinction
  between absence and zero, but are not GNSS interpolation. The producer of
  these aggregates is not provided in the inspected pipeline. **UNKNOWN:**
  units, weighting, deduplication and raw-clock handling. A field called
  `speed_sum` is not automatically distance.
- **LGURI/injury-forecaster:** [injury_forecaster.ipynb][injury-notebook] loads
  subjective training-load, wellness and injury CSVs in its early code cells.
  The inspected notebook contains no objective GNSS/IMU processing, despite
  broader README claims. No requested distance/sprint/clock implementation can
  be attributed to those claims.
- **simulamet-host/soccermon-deephit** at
  [9ae6455047d75dad8e17b93c7a084dce85fba5f8][deephit-tree] and
  **mayooueidat-uva/soccermon-data-and-sources** at
  [b3970b31b8848f457efde4075bde54bb772fdafa][mayo-tree] have no implementation
  in their inspected trees. The related `mayooueidat-uva/soccermon-project`
  repository returned an empty-repository API response. These are not evidence
  of an alternative processing method.

## Publications, discussions and timestamp evidence

**DOCUMENTED:** the [SoccerMon descriptor][dataset-paper] states APEX hardware
IMU rates of 952 Hz, Sonra 2.1.4 retrieval, anonymized CSV export and Parquet
conversion. It describes likely receiver firmware prefiltering, without its
algorithm. Its [Table 3][dataset-table] lists nominal exported IMU 100 Hz, GNSS
10 Hz, millisecond-format timestamps, sensor-calculated speed in m/s,
accelerometer axes in g, gyro axes in deg/s, and absolute `inst_acc_impulse` in
m/s². It gives no scale for the native GNSS quality codes. These are export
descriptions, not exact sample-clock observations or forward-acceleration labels.

The descriptor's technical validation uses sprint **distance** above 5.55 m/s,
and acceleration/deceleration distances with ±2.26 m/s², minimum 0.3-second
efforts ending at zero acceleration. It does not provide the processing code
or a sprint-count algorithm there. Those definitions differ from both consumers
above and must not be silently substituted for one another.

**OBSERVED, from our prior investigation:** the nine files contain 4,987,174 IMU
rows, 498,725 contiguous timestamp groups, 99.996992% ten-row groups, varying
accelerometer and gyroscope vectors in every group, and 23 clock gaps of
200–1,200 ms. Source strings have one fractional digit; no finer clock/counter
is present. The unusual middle-pair IMU difference pattern also argues for
investigating export processing before assuming uniform spacing.

**INFERRED:** downstream time deduplication and every-tenth-row selection show
how consumers work around redundancy, not why the exporter creates it.
They do not distinguish packet timestamps, rounding, precision loss, buffering
or sample-rate conversion. No reviewed code demonstrates that successive GNSS
timestamp groups always represent newly acquired fixes. Identical coordinates
across times remain compatible with both a stationary player and stale fixes.

[Dashboard issue #101][dashboard-issue] supplies code/thesis links;
[PR #115][dashboard-pr] establishes the separate `v2` implementation. Neither
documents the acquisition clock. No relevant timing-resolution answer was
found in the public issue search. The [Athlelorien preprint][athle-paper] and
code establish a coarse GNSS workflow, not sub-group IMU timing. The separate
[minute-resolution SoccerMon preprint][minute-paper] describes mean vendor
signals and axis standard deviations, expanding summaries and trailing
five-observation features grouped by session. No linked processing implementation
was found in its inspected HTML; raw timestamp reduction and horizontal-axis
conventions cannot be audited from that description alone.

**UNKNOWN:** hardware-to-export rate reduction, source-row chronological
guarantee, timestamp first/last/arrival phase, GNSS fix age, shared clock origin,
filter latency, sample loss and historical quality encoding. The evidence does
not justify creating precise per-sample times. A separately labelled estimated
timeline remains a possible future experiment, contingent on resolving export
semantics; original canonical timestamps must remain unchanged.

## Comparison with our canonical model and GNSS pipeline

Our [SoccerMon importer](../src/football_stat_tracker/importers/soccermon.py)
and [canonical model](../src/football_stat_tracker/data_model.py) preserve source
timestamps, every IMU row, source order, original native values, row ranges,
file SHA-256 and recording metadata. Ground truth and independently measured
sampling rates can be absent. Only **consecutive identical time text and all
GNSS/auxiliary fields** collapse to one candidate with a retained row range;
conflicts survive and identical positions at later times remain. Candidates
are explicitly not independently verified fixes. This is more traceable than
time-only deduplication, index decimation or destructive conversion.

Coordinate usability is distinct from quality. Missing/non-finite/out-of-range
coordinates and SoccerMon's zero pair remain raw but have unusable canonical
positions. A single zero axis is valid geography. Native `hacc` is retained
without claiming metres; `horizontal_accuracy_m` remains unset. Vendor speed
is a sensor-derived observable, never ground truth. Raw accelerometer/gyro
values stay in their native sidecars; Walking gravity/orientation fields are
not populated by guessing their meaning.

[Raw distance](../src/football_stat_tracker/gnss.py) sums Haversine links between
successive usable positions. It skips invalid samples and therefore bridges
their endpoints; this is displacement across missing data, not knowledge of
the travelled path. The generic geographic function accepts `(0,0)` as a legal
Earth location; the SoccerMon importer applies the dataset-specific sentinel
policy. Preserve this distinction and existing Walking numerical behavior.

[Diagnostics](../src/football_stat_tracker/gnss_diagnostics.py) calculate
geometric speed with actual positive elapsed time. The
[robust estimator](../src/football_stat_tracker/gnss_robust.py) rejects invalid
time, non-positive time and geometric speeds above the configured 15 m/s.
Intervals >30 seconds are gaps; plausible endpoint chords remain in estimated
distance and are also reported as uncertain. It audits horizontal accuracy
without filtering on it. These are conservative V0A anomaly rules, not sprint
thresholds or a fully validated SoccerMon noise filter. The observed 0.2–1.2 s
clock gaps fall below that default threshold; future event analysis needs its
own explicit continuity assessment, including invalid-position outages.

V0A's six-session Walking evaluation also demonstrates why agreement is not
guaranteed: `14_6` distance error improves from +10.194% to +1.811%, whereas
`8_4` changes from −0.697% to −3.366% and includes a 361.436-second gap chord.
Do not tune those fixed rules on SoccerMon to obtain attractive summaries.
There is no independent SoccerMon reference establishing external methods as
more accurate. We currently implement neither sprint detection, physical IMU
reconstruction nor GNSS/IMU fusion, and this review adds none.

## Proposed V0B.3 validation plan

The next engineering step is an **audited GNSS metric comparison**, before
shipping sprint counts or acceleration claims. All items below are proposals;
none has been implemented in this investigation.

| Experiment | Evidence / fixtures | Required output or decision |
|---|---|---|
| Candidate/view integrity | Stationary coordinates at new times, conflicting same-time fields, repeat runs, clock reversals, partial edge groups, multiple players/sessions | Keep raw provenance; quantify exactly what each analysis view excludes. Never equate candidate count with acquired-fix count. |
| Distance comparison | Synthetic known-length straight/constant-axis/out-and-back/curved paths; stationary jitter; zero pairs; irregular intervals and invalid-position outages | Compare existing raw/robust Haversine, WGS84/local-plane geometry, and vendor-speed integrals over an explicit **common valid interval**. Report observed links, rejected links, uncertain chords, coverage and endpoint convention separately. |
| Vendor-speed weighting | Actual positive candidate elapsed times; missing/negative/non-finite speed fixtures; left/right/trapezoidal interval conventions | Reproduce fixed-0.1 weighting as a labelled comparator; compare elapsed-time integration only on intervals permitted by the chosen continuity policy. Do not extend speed through outages or invent the final interval. Agreement is consistency, not accuracy. |
| Temporal scale and noise | Same trajectories at candidate cadence and one-second views; time-based windows; unsmoothed versus declared smoothing experiments | Measure lost curvature and brief peaks, window elapsed spans and stationarity noise. Retain the existing V0A results/configuration; evaluate future SoccerMon policies separately with recorded parameters. |
| Sprint/event definitions | Constant high speed, initial/final high interval, brief spike, threshold equality/chatter, two efforts separated by recovery, missing recovery, gap, conflicting clock values | Write an operational definition before coding: speed source, threshold/units, minimum observed duration, recovery/hysteresis, start/end convention and censoring. Contrast crossings with sustained events. Gaps/missing rows must not manufacture continuity. Do not optimize thresholds without labelled evidence. |
| Acceleration semantics | Constant speed and controlled speed ramps; geometric speed uncertainty; vendor impulse alongside GNSS differences; zero/negative elapsed intervals | Keep signed running-speed change separate from absolute vendor impulse and IMU axis variation. Define temporal support and filtering latency; make acceleration undefined where support is insufficient. Never divide within-group IMU differences by invented 10 ms. |
| IMU descriptive summaries | Native-axis magnitude/variation and per-group spreads, retaining row counts, missingness and boundary flags | Test time-free or coarse labelled summaries without claiming forward acceleration, orientation or exact timing. Sensor units remain separate; no integration/fusion until clocks and gravity conventions are resolved. |
| Independent validation | New controlled stationary, straight, turning and stop/start recordings with surveyed distance and synchronized timing gates/video | Estimate distance error, peak-speed/acceleration uncertainty, and event precision/recall with declared labels. Vendor output alone cannot validate a reconstruction of that vendor's signals. |

Methods worth testing are explicit identity/phase/gap segmentation, elapsed-time
denominators, separate vendor-versus-geometric measurements, time-based demand
windows, and missingness masks. Test any quality rule only after confirming its
native encoding and measuring excluded coverage. Do not adopt silent 100 m
zeroing, blanket single-axis-zero rejection, every-tenth-row fix identification,
global time deduplication of IMU, mislabeled norm sums, or low-speed removal
before event segmentation.

### Questions for dataset authors and STATSports

No messages were sent. Request these concrete artifacts/answers next:

1. One original Sonra 2.1.4 CSV matching a published Parquet file, plus exact
   conversion code/configuration and original numeric time formatting. Were
   fractions rounded/truncated, or did rows already share timestamps in CSV?
2. Hardware/firmware and raw-export version; what produces the documented
   952-to-100 Hz difference? Is there decimation, resampling, filtering or
   batching, and does the position-five pattern correspond to an internal block?
3. Is source row order chronological per IMU sample? Does a group timestamp
   denote first/last sample, a GNSS epoch, packet formation/arrival or export
   time? Supply packet layout, sample counter/alternative clock and edge-group
   clipping rules if available.
4. GNSS/IMU clock synchronization, phase, latency and drift guarantees; meaning
   of absent timestamp groups. Are there missing samples, or only missing labels?
5. GNSS fix-epoch/age/validity metadata distinguishing new stationary fixes from
   stale exports; behavior of `(0,0)` with positive satellite counts.
6. Historical units/scales/sentinels for `hacc`, `hdop` and `signal_quality`,
   including whether zero means missing, perfect quality or another code.
7. How are `speed` and `inst_acc_impulse` computed, filtered and aligned? Does
   impulse represent speed-change magnitude, body acceleration or another
   vendor definition? What gravity, axes, orientation and gyro calibration
   conventions apply to the exported IMU?
8. Can the descriptor's distance, sprint-distance and acceleration-distance
   validation code and effort-boundary rules be released? Can dashboard database
   producers/version metadata identify which feature-extraction revision ran?

Without those answers, original order and timestamp-group membership are
recoverable; precise intra-group timing and absolute sensor alignment are not.

## Validation and limitations

Full baseline and post-report checks:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
git diff --check
git diff --cached --check
```

Both suite runs passed **81 tests, no skips**. This covers the existing Walking
and SoccerMon imports, canonical model, GNSS distance/diagnostics/robust rules,
real-data validation tools and IMU investigation functions. No new tests are
needed for a documentation-only change. Source URLs, pinned paths/lines and
downloaded blob identities were reviewed; external pipelines were not run, so
their runtime outputs and deployed database provenance remain unverified.

GitHub trees were complete for the reviewed implementation snapshots. Searches
are not exhaustive. The thesis PDF was linked as a discovery source; its text
was not used to establish algorithms. A further [Sensors article](https://www.mdpi.com/1424-8220/26/13/4228)
(`10.3390/s26134228`) surfaced in search, but its publisher endpoint returned
HTTP 429; no methods are attributed to that inaccessible source. The nine local
recordings are an existing subset, not evidence of every dataset export version.
No raw data, precise player trace, generated output, external source code or
secret belongs in this report's commit. The only changed file is this report.

[critical-tree]: https://github.com/danielfrenandez/CriticalSpeed_shiny/tree/c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1
[critical-summary]: https://github.com/danielfrenandez/CriticalSpeed_shiny/blob/c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1/scripts/2_load_clean_proces_data.R#L53-L110
[critical-windows]: https://github.com/danielfrenandez/CriticalSpeed_shiny/blob/c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1/scripts/3_moving_averages.R#L31-L134
[critical-app]: https://github.com/danielfrenandez/CriticalSpeed_shiny/blob/c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1/app.R#L149-L202
[critical-repetitions]: https://github.com/danielfrenandez/CriticalSpeed_shiny/blob/c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1/app.R#L596-L601
[critical-fit]: https://github.com/danielfrenandez/CriticalSpeed_shiny/blob/c9f3fdeb39904db0a8b22fdfe799d12d7a8bb0c1/scripts/4_df_historic_ind_max.R#L12-L40
[dashboard-dev-tree]: https://github.com/simulamet-host/soccer-dashboard/tree/dc2fb4a4eeb47a149a7223cccc3f485e48031625
[dashboard-v2-tree]: https://github.com/simulamet-host/soccer-dashboard/tree/92862d13ad711517e60e283c349d145efa775918
[dashboard-main]: https://github.com/simulamet-host/soccer-dashboard/blob/f1f3b4307b3d177f4a0688c7c461fbc63ec812bc/streamlit_app/app.py
[dashboard-mobility]: https://github.com/simulamet-host/soccer-dashboard/blob/92862d13ad711517e60e283c349d145efa775918/components/analysis/analysis_gps_mobility.py#L12-L29
[dashboard-sprints]: https://github.com/simulamet-host/soccer-dashboard/blob/92862d13ad711517e60e283c349d145efa775918/components/analysis/analysis_gps_sprint.py#L7-L51
[dashboard-fetch]: https://github.com/simulamet-host/soccer-dashboard/blob/92862d13ad711517e60e283c349d145efa775918/utils/data_fetcher.py#L7-L37
[dashboard-projection]: https://github.com/simulamet-host/soccer-dashboard/blob/92862d13ad711517e60e283c349d145efa775918/utils/gps.py#L178-L365
[dashboard-tests]: https://github.com/simulamet-host/soccer-dashboard/blob/92862d13ad711517e60e283c349d145efa775918/tests/utils/test_gps.py
[dashboard-demo]: https://github.com/simulamet-host/soccer-dashboard/blob/dc2fb4a4eeb47a149a7223cccc3f485e48031625/src/pages/gps_information.py#L53-L91
[dashboard-legacy]: https://github.com/simulamet-host/soccer-dashboard/blob/dc2fb4a4eeb47a149a7223cccc3f485e48031625/src/pages/player_gps_report.py#L150-L180
[dashboard-issue]: https://github.com/simulamet-host/soccer-dashboard/issues/101
[dashboard-pr]: https://github.com/simulamet-host/soccer-dashboard/pull/115
[hoel-tree]: https://github.com/simula/pmsys/tree/3ad81b01572b5633a95a37cdf6dff0e382a14047/lars-hoel
[hoel-features]: https://github.com/simula/pmsys/blob/3ad81b01572b5633a95a37cdf6dff0e382a14047/lars-hoel/FeatureExtraction.ipynb
[hoel-visual]: https://github.com/simula/pmsys/blob/3ad81b01572b5633a95a37cdf6dff0e382a14047/lars-hoel/GPSvisualization.ipynb
[hoel-thesis]: https://home.simula.no/~paalh/students/LarsHoel-UiO.2023.pdf
[athle-tree]: https://github.com/framewave-lab/Athlelorien/tree/68634b9defe08a0b3f2c179b2a27280b29f29d46
[athle-loader]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/src/utils/day_loader.py#L99-L179
[athle-cache]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/analysis/levy_paper/scripts/build_multiseason_data_cache.py#L330-L364
[athle-pitch]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/src/utils/pitch_calibration.py#L262-L330
[athle-status]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/src/utils/player_status.py#L281-L310
[athle-paths]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/src/utils/trajectory_stats.py#L1510-L1656
[athle-velocity]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/src/utils/collective_stats.py#L130-L160
[athle-runs]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/src/utils/trajectory_stats.py#L132-L240
[athle-params]: https://github.com/framewave-lab/Athlelorien/blob/68634b9defe08a0b3f2c179b2a27280b29f29d46/analysis/levy_paper/util/paper_utils.py#L56-L72
[athle-paper]: https://arxiv.org/html/2609.15541v1
[spark-tree]: https://github.com/s-ahmed-01/Soccermon-Project/tree/c5cdf284d89473a50b2f72c78dedf1f9bedf7047
[spark-code]: https://github.com/s-ahmed-01/Soccermon-Project/blob/c5cdf284d89473a50b2f72c78dedf1f9bedf7047/pyspark.py#L11-L53
[spark-notebook]: https://github.com/s-ahmed-01/Soccermon-Project/blob/c5cdf284d89473a50b2f72c78dedf1f9bedf7047/pyspark.ipynb
[spark-eda]: https://github.com/s-ahmed-01/Soccermon-Project/blob/c5cdf284d89473a50b2f72c78dedf1f9bedf7047/EDA.py
[soccermon-tree]: https://github.com/simula/soccermon/tree/eaa6c888845cda60f30e8f86ebfc48a526662ffb
[soccermon-reader]: https://github.com/simula/soccermon/blob/eaa6c888845cda60f30e8f86ebfc48a526662ffb/preprocessing/read_in_data.py#L78-L127
[soccermon-model]: https://github.com/simula/soccermon/blob/eaa6c888845cda60f30e8f86ebfc48a526662ffb/preprocessing/data_loader.py
[soccermon-pickle]: https://github.com/simula/soccermon/blob/eaa6c888845cda60f30e8f86ebfc48a526662ffb/preprocessing/run_team_pickle_generation.py
[latent-tree]: https://github.com/idaejin/latent-memory-states/tree/4e343ffb94e9cc3eba5b17ac83fc7c3f60a7e9ec
[latent-windows]: https://github.com/idaejin/latent-memory-states/blob/4e343ffb94e9cc3eba5b17ac83fc7c3f60a7e9ec/memory_reps/windows.py#L15-L157
[injury-tree]: https://github.com/LGURI/injury-forecaster/tree/cbcee3408b41251434cbf87f04600f174c72d112
[injury-notebook]: https://github.com/LGURI/injury-forecaster/blob/cbcee3408b41251434cbf87f04600f174c72d112/injury_forecaster.ipynb
[deephit-tree]: https://github.com/simulamet-host/soccermon-deephit/tree/9ae6455047d75dad8e17b93c7a084dce85fba5f8
[mayo-tree]: https://github.com/mayooueidat-uva/soccermon-data-and-sources/tree/b3970b31b8848f457efde4075bde54bb772fdafa
[dataset-paper]: https://www.nature.com/articles/s41597-024-03386-x?error=cookies_not_supported
[dataset-table]: https://www.nature.com/articles/s41597-024-03386-x/tables/3?error=cookies_not_supported
[minute-paper]: https://arxiv.org/html/2609.03790v1
