# V0B.3 — SoccerMon GNSS distance and speed validation

Investigation date: 2026-09-30. This is a consistency and sensitivity study of
the existing nine-recording subset, not validation against measured distance.

## Executive findings

**OBSERVED:** total distances are **53.754 km** from raw coordinate geometry,
**52.429 km** from the unchanged robust estimator, and **42.036 km** from
conservatively supported vendor-speed integration. The first two totals include
endpoint links across discontinuities; the third excludes them. On the same
eligible input intervals, the robust estimate is **52.208 km**, still **24.2%**
above the vendor integral. Per-session excess ranges from **10.6% to 144.8%**.

The 15 m/s geometric rejection rule removes 230 extreme links, but leaves
**8.806 km** accumulated on supported intervals whose left-end vendor speed is
zero. **INFERRED:** coordinate drift, differing vendor processing, or signal
alignment could account for much of the disagreement. **UNKNOWN:** which
observable better represents actual movement. Zero vendor speed is not an
independent stationary label, and agreement would not establish accuracy.

The current robust estimator remains useful for auditable geometry and extreme
jump rejection. Its 30 s gap flag is too coarse for this continuity audit, and
its speed threshold alone does not suppress low-speed accumulation. No estimator
is a scientifically validated winner. Carry the vendor integral as a labelled
device-derived distance proxy alongside robust geometry and coverage; do not
publish either as verified football playing distance or use these results to
calibrate sprint thresholds.

## Baseline and scope

The working tree was clean at `b7a97c4`, following the importer, IMU investigation
and external-methods milestones. The V0A evaluation artifacts, V0B preparation
and real-data reports, [importer report](v0b2_soccermon_importer_report.md),
[IMU investigation](v0b2_imu_timestamp_investigation.md) and
[external methods review](v0b2_external_methods_review.md), model, importer,
geometry, diagnostics, robust estimator and tests were read before changes.
The baseline suite passed **81 tests**, with no skips.

The script imports each complete recording through the existing SoccerMon
importer, one at a time. All **4,987,174 source rows and IMU samples** remain
preserved; all nine source SHA-256 hashes match the extraction manifest before
and after analysis. There are **498,725 canonical GNSS candidates**, of which
**362** have invalid coordinates and **498,363** are retained for calculations.
Raw recordings, canonical sessions, importer, filters and IMU clocks are unchanged.
No sprint, acceleration, fusion or clock-reconstruction algorithm was added.

Evidence labels below mean: **DOCUMENTED** in existing source/documentation;
**OBSERVED** calculated from this subset; **ASSUMED** an explicitly chosen
analysis convention; **INFERRED** an interpretation; **UNKNOWN** unresolved.

**DOCUMENTED:** the publication describes degrees for coordinates and m/s for
sensor-calculated speed; the importer retains those values without conversion.
See the source references and native-quality caveats in the importer report.
Nominal 10 Hz export documentation does not prove independently fresh receiver
fixes every 100 ms. There is no independent distance ground truth, verified
playing-time annotation, receiver sequence counter or documented vendor speed
filter/clock phase in these recordings.

## Candidate and timestamp policy

`src/football_stat_tracker/gnss_validation.py` provides a separate immutable
analysis view, rather than changing the importer or canonical model.

1. Require finite original and analysis timestamps with a constant offset.
   Refuse reversals, including unresolved midnight rollover; do not sort,
   manufacture missing clocks or unwrap time-of-day.
2. Preserve source order, original sample objects and original timestamps.
   Each retained representative records all original canonical candidate
   indices; source objects still contain their original time text, source row
   ranges, native fields and recording provenance.
3. For equal timestamps, combine equivalent exported fields into one
   representative. If coordinates, speed, quality or other native fields
   conflict, quarantine the entire timestamp group, flag it, and break
   integration continuity. NaN-bearing or signed-zero-distinct exports are not
   silently declared equivalent. No same-time representative is selected by
   averaging or arbitrary last-row selection.
4. Exclude unusable, missing, non-finite, out-of-range and `(0,0)` coordinates
   from calculations. A single zero axis is valid geography. Exclusions retain
   their original indices; source records remain available. Any removed group
   between retained endpoints breaks vendor-integration support.
5. Keep identical coordinates at successive distinct timestamps. They may
   describe a stationary receiver or a held export; coordinates alone cannot
   determine whether a fix is fresh.

**OBSERVED:** the importer already collapses identical GNSS exports within each
stored timestamp group. The analysis therefore encounters **zero duplicate
canonical candidate timestamp groups, zero conflicting groups and zero
reversals** across the nine sessions. The source files nevertheless contain
**4,488,449 repeated-timestamp rows**, predominantly separate IMU samples, which
are preserved. These counts must not be conflated. The analysis view's additional
same-time handling is exercised by synthetic tests, not claimed as a real-data
conflict finding. The number of independently identifiable GNSS fixes remains
**UNKNOWN**, not 498,363.

## Distance definitions and support

**A — raw Haversine:** use existing `total_gnss_distance_m` between every
successive retained valid coordinate. No speed or quality cutoff. Links across
removed records or clock gaps remain endpoint chords, not recovered trajectories.

**B — existing robust:** use existing `estimate_robust_gnss_distance` with its
unchanged **15 m/s** geometric-speed cutoff and **30 s** gap threshold. A link
above the speed cutoff contributes zero. A sufficiently slow link above the gap
threshold still contributes its endpoint chord and is additionally marked
uncertain. A gap flag is not a distance exclusion. No native quality thresholds
are applied to either geometry method.

**C — vendor integral:** **ASSUMED** left rectangles, `speed[i] * actual_dt`,
with seconds derived from original millisecond clock differences. Require both
endpoint speeds to be finite and nonnegative, even though only the left speed
is weighted. Zero is valid. Require no excluded candidate group between the
endpoints and **0 < dt <= 0.1 s**. The 100 ms continuity limit is a conservative
choice based on observed export spacing, not a physical receiver-rate claim.
No first/last extension, gap filling, position-speed agreement gate or vendor
speed clipping is used. Supported missing/invalid speed cases occur in tests;
none exclude additional real-data intervals in this run.

C is a subtotal over supported intervals, not an estimate for the missing time.
Coverage is supported duration divided by original first-to-last candidate span,
including loss at invalid recording boundaries. The overall span is **49,879.4 s**,
with **49,831.9 s (99.905%)** supported by C. High time coverage does not imply
high distance accuracy or fresh fixes. A/B use broader input support, so the
report also calculates **A_common and B_common** on exactly C's eligible input
intervals. B still applies its own rejection within that set; its accepted
duration is recorded separately. This distinction prevents attributing all
method differences to filtering when their input time coverage differs.

Cumulative plots credit each interval at its right endpoint. A flat C curve over
an excluded interval means unsupported distance, not demonstrated inactivity.
Geometric speed is interval displacement divided by elapsed time, displayed at
the right endpoint; vendor speed is a candidate observation. Comparing geometry
with the left-end vendor value is another declared convention, not proof that
their temporal phase matches. No acceleration is calculated from these signals.

## Nine-session results

Labels follow manifest order and the earlier reports. All records are TeamB;
identity here is the retained original player identifier, not a new anonymization.

| Session | Recording date | Player identifier |
|---|---|---|
| S1 | 2020-06-17 | afc13e53-2c77-48cb-8a78-743663bbb84f |
| S2 | 2020-06-17 | 48bfd4ea-e9e2-45b5-befc-3383cae87fdf |
| S3 | 2020-08-27 | afc13e53-2c77-48cb-8a78-743663bbb84f |
| S4 | 2020-08-27 | 48bfd4ea-e9e2-45b5-befc-3383cae87fdf |
| S5 | 2020-11-19 | afc13e53-2c77-48cb-8a78-743663bbb84f |
| S6 | 2020-11-19 | 48bfd4ea-e9e2-45b5-befc-3383cae87fdf |
| S7 | 2020-11-19 | 70b74270-f655-43cc-a188-1ebc7a828b95 |
| S8 | 2020-06-17 | 789547e7-1325-4153-a98d-5ecd497f3668 |
| S9 | 2020-06-17 | 247a8333-f7b0-b7d2-cda8-056c3d15eef7 |

**OBSERVED** main totals; distances in metres, rounded for display:

| Session | A raw | B robust | C vendor | C coverage % | B rejected links | Uncertainty flags |
|---|---:|---:|---:|---:|---:|---|
| S1 | 6,177.53 | 5,965.76 | 4,993.67 | 99.986 | 31 | U, G, J |
| S2 | 4,592.16 | 4,566.97 | 2,406.83 | 99.983 | 4 | U, G, I, J |
| S3 | 187.22 | 187.22 | 76.11 | 99.727 | 0 | U, G |
| S4 | 3,086.49 | 3,025.25 | 1,815.09 | 99.973 | 17 | U, G, J |
| S5 | 11,414.79 | 11,363.50 | 10,238.70 | 99.982 | 3 | U, G, J |
| S6 | 6,665.37 | 6,656.13 | 5,833.25 | 99.980 | 2 | U, G, J |
| S7 | 10,890.25 | 10,874.24 | 9,828.50 | 99.958 | 8 | U, G, I, J |
| S8 | 3,740.19 | 3,701.27 | 2,632.23 | 99.986 | 9 | U, G, J |
| S9 | 6,999.72 | 6,089.16 | 4,211.70 | 99.396 | 156 | U, G, I, J |
| Total | 53,753.72 | 52,429.50 | 42,036.08 | 99.905 | 230 | U, G, I, J |

U = no independent ground truth; fix freshness, vendor processing/phase and
quality scales unknown; recording span is not verified playing time.
G = discontinuous support; I = invalid coordinates excluded;
J = geometric links exceed the existing 15 m/s guard. Detailed named flags are
in the machine-readable table. They indicate uncertainty, not validated error.

| Session | Source rows = preserved IMU | Source candidates | Retained | Invalid | Span (s) | Valid links >100 ms | Links crossing exclusions | Maximum valid link dt (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S1 | 644,460 | 64,447 | 64,447 | 0 | 6,445.3 | 2 | 0 | 0.7 |
| S2 | 580,445 | 58,045 | 58,044 | 1 | 5,805.0 | 3 | 0 | 0.5 |
| S3 | 51,130 | 5,114 | 5,114 | 0 | 512.3 | 4 | 0 | 0.7 |
| S4 | 437,530 | 43,754 | 43,754 | 0 | 4,376.3 | 2 | 0 | 1.0 |
| S5 | 714,225 | 71,423 | 71,423 | 0 | 7,143.2 | 3 | 0 | 0.8 |
| S6 | 696,320 | 69,633 | 69,633 | 0 | 6,964.4 | 2 | 0 | 1.2 |
| S7 | 673,009 | 67,302 | 67,287 | 15 | 6,731.0 | 4 | 1 | 1.6 |
| S8 | 582,780 | 58,279 | 58,279 | 0 | 5,828.4 | 2 | 0 | 0.6 |
| S9 | 607,275 | 60,728 | 60,382 | 346 | 6,073.5 | 13 | 11 | 25.7 |

There are **23 source clock intervals >100 ms**, with maximum 1.2 s. Removing
invalid coordinates yields **35 longer valid-coordinate links**, including 12
links across removed groups. S2's single invalid coordinate is at a boundary;
it loses support without creating an interior bridge. S9's 25.7 s valid link is
an invalid-coordinate outage, not a 25.7 s gap in the source clock labels.
Minimum, median and p95 retained-link intervals are 100 ms in every session.
The CSV gives every interval count, including rare 200–25,700 ms links.

## Common-support speed and distance comparison

Distances below use C-eligible input intervals; C equals its main-table total.
Bias, mean absolute difference and Pearson correlation use the further subset
accepted by B. They compare observables and are **not ground-truth errors**.
Statistics weight intervals equally; all eligible real-data intervals are 100 ms.

| Session | A_common (m) | B_common (m) | B_common above C (%) | Geometric-minus-vendor bias (m/s) | Mean absolute difference (m/s) | Pearson r | B distance with left vendor speed zero (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 | 6,174.81 | 5,963.04 | 19.41 | 0.151 | 0.358 | 0.803 | 812.30 |
| S2 | 4,574.78 | 4,564.34 | 89.64 | 0.372 | 0.518 | 0.526 | 1,743.24 |
| S3 | 186.34 | 186.34 | 144.82 | 0.216 | 0.269 | 0.485 | 100.27 |
| S4 | 3,082.02 | 3,020.78 | 66.43 | 0.276 | 0.396 | 0.528 | 955.88 |
| S5 | 11,365.07 | 11,358.31 | 10.94 | 0.157 | 0.358 | 0.888 | 1,009.00 |
| S6 | 6,661.72 | 6,655.75 | 14.10 | 0.118 | 0.263 | 0.849 | 717.65 |
| S7 | 10,884.93 | 10,868.91 | 10.59 | 0.155 | 0.369 | 0.905 | 981.40 |
| S8 | 3,740.04 | 3,701.12 | 40.61 | 0.183 | 0.329 | 0.803 | 1,002.74 |
| S9 | 6,704.93 | 5,889.41 | 39.83 | 0.279 | 0.461 | 0.683 | 1,483.86 |
| Total | 53,374.63 | 52,208.02 | 24.20 | — | — | — | 8,806.35 |

The last column accounts for 86.6% of the net aggregate B_common-minus-C
difference, arithmetically; it does not establish that 86.6% is erroneous drift.
On zero-left-vendor intervals A accumulates **9,809.03 m** before B's guard.
The JSON/CSV also contain unfiltered common-input speed comparisons, RMSE,
95th-percentile differences, maxima and accepted durations. Extreme geometric
jumps strongly affect unfiltered correlation and RMSE; report the support mask
alongside any future use of those statistics.

There are **17,196 exactly repeated coordinate links**, including **907 supported
links with positive left vendor speed**. Longest uninterrupted exact-coordinate
holds range from 0.5 to 1.3 s. These observations are compatible with coordinate
quantization, held fixes or small movement; they do not identify receiver fix
freshness. Distinct-time stationary coordinates contribute zero geometric
distance, while vendor speed is retained independently.

## Sensitivity and anomalies

The geometric guard is a sensitivity experiment, not threshold optimization.
No labelled football path or known true speed supports selecting a new value.
The full output also includes 12 m/s.

| Session | B at 10 m/s (m) | B at 15 m/s (m) | B at 20 m/s (m) |
|---|---:|---:|---:|
| S1 | 5,937.45 | 5,965.76 | 5,980.07 |
| S2 | 4,541.27 | 4,566.97 | 4,568.49 |
| S3 | 187.22 | 187.22 | 187.22 |
| S4 | 3,011.80 | 3,025.25 | 3,030.62 |
| S5 | 11,358.93 | 11,363.50 | 11,363.50 |
| S6 | 6,655.04 | 6,656.13 | 6,659.40 |
| S7 | 10,862.19 | 10,874.24 | 10,882.15 |
| S8 | 3,699.04 | 3,701.27 | 3,706.46 |
| S9 | 5,891.94 | 6,089.16 | 6,188.76 |

**OBSERVED:** varying the existing gap flag from 0.1 through 30 s leaves B's
total unchanged, because it marks accepted chords rather than discarding them.
The default 30 s rule flags zero links in this subset. Excluding discontinuous
geometry separately reduces aggregate B by **221.47 m**, to 52.208 km, without
changing the estimator. The large remaining vendor discrepancy is not explained
by these missing-time chords.

Counterfactual vendor holds allowing 0.2, 1, 2 or 30 s links still refuse links
across quarantined coordinates. They change C by zero in eight sessions and by
at most **0.0772 m** in S8, because left-end speed is usually zero at source
clock gaps. This is a property of these data, not justification for bridging
future gaps. Right and trapezoidal weighting on identical short-link support
change C by at most **0.0758 m** per session. Small weighting sensitivity cannot
validate the native speed algorithm or its timing phase.

Representative **OBSERVED** anomalies, reproducible from source indices/row
ordinals in `anomalies.csv` (no geographic traces exported):

- S1: a 127.72 m displacement in 0.1 s implies **1,277.25 m/s**, while both
  vendor endpoint speeds are zero. B rejects the link.
- S3: a 0.706 m displacement in 0.1 s implies **7.06 m/s**, with both vendor
  speeds zero. B accepts it, illustrating why surviving the 15 m/s guard does
  not validate a football speed peak or establish a sprint.
- S9: a 135.64 m displacement in 0.1 s implies **1,356.38 m/s**, versus vendor
  0.742 to 0 m/s. B rejects it; C retains its independently supported vendor
  contribution. Native `hacc` changes from 0 to 7: zero must not be interpreted
  as demonstrated zero-metre uncertainty.
- S9: elapsed 6,022.9–6,048.6 s bridges invalid coordinates. Its **117.31 m**
  endpoint chord implies 4.56 m/s, so B accepts it and its 30 s rule does not
  flag it. C excludes the interval. Neither the chord nor zero vendor endpoint
  speeds reconstructs the intervening movement.
- S7: a 1.6 s invalid-coordinate bridge contributes a small 0.22 m chord to B
  but breaks C support. Discontinuity handling must not depend solely on jump
  magnitude.

**INFERRED:** the Walking-era 15 m/s guard remains an effective rejection of
obvious corrupt jumps but is insufficient for football peak-speed validity or
low-speed distance drift. The 30 s gap flag is unsuitable as the only continuity
audit. Neither finding justifies silently changing V0A or choosing thresholds to
force agreement with vendor speed. Native quality scales and vendor filtering
remain unknown; no `hacc`, `hdop`, signal or satellite-count gate was adopted.

## Reproduction, plots and tests

Use the existing environment with `requirements-v0b1.txt` installed and the
existing subset/extraction manifest. From the repository root:

```sh
PYTHONPATH=src .venv/bin/python scripts/validate_soccermon_gnss.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The script accepts `--manifest`, `--output`, `--max-interval-s` and `--no-plots`.
The report uses the default 0.1 s limit. Results and **28 diagnostic PNGs** are
saved under the ignored `outputs/v0b3_gnss_validation/` directory:

- [Full per-session comparison](../outputs/v0b3_gnss_validation/comparison.csv),
  [complete JSON](../outputs/v0b3_gnss_validation/validation_summary.json),
  [speed comparisons](../outputs/v0b3_gnss_validation/speed_comparison.csv),
  [sensitivities](../outputs/v0b3_gnss_validation/sensitivity.csv),
  [interval counts](../outputs/v0b3_gnss_validation/interval_distribution.csv),
  and [anomaly provenance](../outputs/v0b3_gnss_validation/anomalies.csv).
- Each S1–S9 has speed, cumulative-distance and anomalous-segment plots. Examples:
  [S1 speeds](../outputs/v0b3_gnss_validation/figures/S1_speed.png),
  [S2 cumulative distance](../outputs/v0b3_gnss_validation/figures/S2_cumulative_distance.png),
  [S9 anomalies](../outputs/v0b3_gnss_validation/figures/S9_anomalous_segments.png).
- [All-session interval distributions](../outputs/v0b3_gnss_validation/figures/gnss_intervals.png).

Full-range speeds use symlog; the companion linear display marks values above
12 m/s with triangles. Values are not clipped from calculations. Low-speed
anomaly windows use linear axes; extreme windows use symlog. Gray spans show
selected anomalies or unsupported C intervals. All session plots and the
interval panel were visually inspected. Local outputs contain aggregate metrics,
elapsed-time diagnostics and source ordinals, not coordinates or raw player
trajectories. They are intentionally absent from Git; the report retains the
essential aggregate tables.

**20 new automated tests** cover equivalent/conflicting timestamps, original
time/provenance retention, reversals, invalid coordinates including single-zero
axes, empty/short series, gaps, stationary positions, missing/negative/non-finite
vendor speed, actual irregular intervals, left/right/trapezoidal weighting,
support/cumulative reconciliation, unchanged source hashes, and separate
synthetic Parquet recordings imported end-to-end. The complete suite passes
**101 tests with no skips**, including existing Walking/V0A/importer/IMU tests.

## What can safely follow

A is a corruption and accumulation diagnostic. B is an auditable geometric
baseline with rejected-link and continuity accounting. C is a reproducible
vendor-derived subtotal with explicitly missing coverage. For exploratory
session summaries, present B and C together and identify their input support;
if one provisional number is needed for compatibility with STATSports, use C
as a **vendor-speed distance proxy**, not validated physical distance.

Next, validate on controlled stationary, surveyed straight/turning and stop/start
recordings with independent distance and synchronized video/timing gates. Ask
the authors or STATSports about native quality encodings, fix freshness, speed
derivation and clock alignment. Then specify a football continuity policy and
test any filtering changes against independent measurements. Preserve the
current V0A path and raw observables. Peak speed, acceleration and later sprint
events need stronger temporal and noise validation than agreement of session
totals; no sprint implementation or IMU reconstruction is justified here.
