# V0B.1 — SoccerMon real-data inspection

Completed 2026-09-30. **V0B.1 is complete:** the original archive is verified,
nine deterministic sessions are extracted, every selected row is profiled, and
eight figures are generated. No canonical model or importer implementation was
changed. No sprint detection, filtering, fusion, or ML was performed.

Evidence labels throughout:

- **DOCUMENTED**: explicit public source statement.
- **OBSERVED**: measured in this local archive, these nine files, or the repository.
- **INFERRED**: an interpretation or proposed engineering decision.
- **UNKNOWN**: unavailable or not established by this inspection.

All schema/value findings apply to the selected subset, not automatically to
all SoccerMon files. Read the [preparation report](v0b_preparation_report.md)
for the earlier architecture audit.

## 1. Verified archive structure

**OBSERVED:** `data/raw/soccermon/objective-TeamB-2020.zip` is
16,445,257,849 bytes (15.315 GiB). Its central directory has
1,983 entries: 146 directories and 1,837 files, all `.parquet`. There are no
nested daily ZIPs or ancillary files in this archive. The actual hierarchy is:

```text
2020/YYYY-MM/YYYY-MM-DD/YYYY-MM-DD-TeamB-PLAYER_UUID.parquet
```

There are 138 nonempty dates from 2020-06-01 through 2020-12-13.
The complete ZIP would expand to 28,404,940,775 bytes;
it was never extracted in full. Every file was decompressed into memory for CRC
verification, discarded, and only the selected nine were subsequently written.

**OBSERVED:** all 1,837 CRC checks passed. The complete local file's MD5 is
`c68f9d77ebaf042ab3e75a0714587c3c`, matching the checksum **DOCUMENTED** by
[Zenodo](https://zenodo.org/records/10033832). This establishes download completeness
against the published artifact. SHA-256:

```text
a22f2cc514706646519645477f42a3025002b90422fb2b3af99b25840ab6b480
```

The archive's byte size and modification timestamp stayed unchanged throughout.
[Verification JSON](../outputs/v0b1_soccermon_inventory/archive_verification.json)
and [final checks](../outputs/v0b1_soccermon_inventory/reproduction_check.json)
record this evidence.

[Machine-readable inventory](../outputs/v0b1_soccermon_inventory/outer_inventory.json)
contains every member's path, compressed/uncompressed bytes, extension, CRC32,
compression method and ZIP modification date. ZIP dates are local DOS timestamps
without a timezone, and describe file modification, not recording dates. Session
dates are taken from the hierarchy. A [plain member list](../outputs/v0b1_soccermon_inventory/outer_members.txt)
is also available.

## 2. Exact subset selection and size

**INFERRED selection policy, OBSERVED feasibility:** sort nonempty dates and take
zero-based index `floor(p × (138 − 1))` for p = 0.1, 0.5, 0.9. Indices 13, 68,
123 select **June 17, August 27, November 19**. The reusable script resolves
colliding quantile indices on small inventories by taking the nearest unused
index, with lower index winning a tie; no collision occurs here.

Only two filename player IDs intersect all three dates, so 3 players × 3 dates
is infeasible. Keep both players on all dates, ordered by SHA-256 of the UTF-8
player UUID. Fill three remaining slots from the same dates by increasing
SHA-256 of UTF-8 `date + "\n" + exact_member_path`. This follows the preparation
report's fallback and uses no sensor values, cleanliness, duration, or outcomes.
The result is five players and three dates, distributed 4/2/3 by date.

C = common-player core; F = deterministic fallback. Exact ZIP members:

| Session | Exact member path | ZIP-uncompressed bytes | Reason |
|---|---|---:|---|
| S1 | `2020/2020-06/2020-06-17/2020-06-17-TeamB-afc13e53-2c77-48cb-8a78-743663bbb84f.parquet` | 18,292,900 | C |
| S2 | `2020/2020-06/2020-06-17/2020-06-17-TeamB-48bfd4ea-e9e2-45b5-befc-3383cae87fdf.parquet` | 15,865,529 | C |
| S3 | `2020/2020-08/2020-08-27/2020-08-27-TeamB-afc13e53-2c77-48cb-8a78-743663bbb84f.parquet` | 1,368,218 | C |
| S4 | `2020/2020-08/2020-08-27/2020-08-27-TeamB-48bfd4ea-e9e2-45b5-befc-3383cae87fdf.parquet` | 12,188,403 | C |
| S5 | `2020/2020-11/2020-11-19/2020-11-19-TeamB-afc13e53-2c77-48cb-8a78-743663bbb84f.parquet` | 21,268,719 | C |
| S6 | `2020/2020-11/2020-11-19/2020-11-19-TeamB-48bfd4ea-e9e2-45b5-befc-3383cae87fdf.parquet` | 19,782,523 | C |
| S7 | `2020/2020-11/2020-11-19/2020-11-19-TeamB-70b74270-f655-43cc-a188-1ebc7a828b95.parquet` | 19,887,706 | F |
| S8 | `2020/2020-06/2020-06-17/2020-06-17-TeamB-789547e7-1325-4153-a98d-5ecd497f3668.parquet` | 15,342,477 | F |
| S9 | `2020/2020-06/2020-06-17/2020-06-17-TeamB-247a8333-f7b0-b7d2-cda8-056c3d15eef7.parquet` | 16,606,373 | F |

**OBSERVED:** total extracted size is **140,602,848 bytes
(134.089 MiB; 0.130947 GiB)**,
well below the 2,147,483,648-byte limit. No daily archives were retained because
none exist inside this ZIP. Exact paths are preserved below
`data/raw/soccermon/subset/`. The selected Parquet files' internally uncompressed
page sizes total 897,697,479 bytes, and
decoded Arrow buffers total 907,042,350 bytes;
these are also below 2 GiB, though Python/plot working memory is additional.

Available disk space was checked before verification and immediately before
extraction: 282,624,000,000 bytes before extraction, against 140,602,848 bytes
plus a 256 MiB reserve. The subset was initially empty. Extraction used the
existing exact-member utility, which creates files exclusively and refuses
existing destinations. Raw data and `.venv` are Git-ignored.

[Selection](../outputs/v0b1_soccermon_inventory/selection.json),
[exact member manifest](../outputs/v0b1_soccermon_inventory/selected_parquet_members.txt),
[extracted manifest with per-file SHA-256 and MD5](../outputs/v0b1_soccermon_inventory/extracted_manifest.json),
and [disk check](../outputs/v0b1_soccermon_inventory/disk_before_extraction.json)
provide reproduction evidence. The selection was replayed from the inventory
and produced the identical paths and byte total.

No optional stress cases were added. **OBSERVED:** S3 is a short, mostly low
vendor-speed record, whereas S5/S7 have higher vendor-speed values and broader
IMU variability. Thus the core already supplies contrasting measured behavior.
**UNKNOWN:** whether any file represents a match, team/individual training,
bench time, or warm-up. These are observations, not activity labels or ground
truth. Nine sessions are a schema/quality sample, not a population estimate.

## 3. Actual Parquet schema and units

**OBSERVED:** all nine schemas are identical, contain 17 nullable fields, and
have one row group. All columns use SNAPPY compression. The producer is
`fastparquet-python version 0.8.1 (build 0)`; pandas metadata names version 1.4.2,
has no index/partition columns, and carries no sensor units or timezone.

The identity field is **`player_name`, not `id`**. Each file contains one constant
`TeamB-UUID` value matching its filename. No altitude, heading, magnetometer,
activity label, criterion trajectory, or distance ground-truth field was found.

Physical types and source units are kept separate:

| Actual field(s) | Arrow / Parquet type | Unit or meaning; evidence |
|---|---|---|
| `player_name` | string / BYTE_ARRAY with String logical type | OBSERVED anonymized `TeamB-UUID`; identity continuity beyond this subset unverified |
| `time` | string / BYTE_ARRAY with String logical type | OBSERVED time of day; one fractional digit in every selected row |
| `lat`, `lon` | double / DOUBLE | DOCUMENTED degrees |
| `speed` | double / DOUBLE | DOCUMENTED vendor-calculated m/s |
| `heart_rate` | int64 / INT64 | DOCUMENTED beats/min |
| `hacc` | int64 / INT64 | DOCUMENTED horizontal accuracy; unit/scale UNKNOWN |
| `hdop` | int64 / INT64 | DOCUMENTED horizontal dilution of precision; exported encoding/scale UNKNOWN |
| `signal_quality` | int64 / INT64 | DOCUMENTED signal quality; encoding UNKNOWN |
| `num_satellites` | int64 / INT64 | DOCUMENTED satellite count |
| `inst_acc_impulse` | double / DOUBLE | DOCUMENTED absolute acceleration, m/s²; vendor processing UNKNOWN |
| `accl_x`, `accl_y`, `accl_z` | double / DOUBLE | DOCUMENTED g; gravity/orientation UNKNOWN |
| `gyro_x`, `gyro_y`, `gyro_z` | double / DOUBLE | DOCUMENTED deg/s; independent unit/axis verification UNKNOWN |

Unit evidence comes from [the authors' Table 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC11139986/#Tab3).
That table gives nominal 10 Hz for GNSS/quality/heart rate/impulse and 100 Hz for
accelerometer and gyroscope exports. Its millisecond-format timestamp description
does not match the observed 0.1-second representation. The dataset descriptor
also qualifies receiver firmware processing as likely; its implementation is
unknown. Source speed is vendor-derived, never independent ground truth.

[Existing utility metadata output](../outputs/v0b1_soccermon_inventory/parquet_metadata.json)
and [full profiles](../outputs/v0b1_soccermon_analysis/full_profiles.json) include
exact schema, nullability, physical/logical types, compression, metadata,
per-column ranges and quantiles for every file.

## 4. Timestamps and observed sampling

**OBSERVED:** every time string parses exactly as time of day, such as
`09:07:39.7`. Every file is nondecreasing in stored order. No midnight crossing,
negative interval, or malformed time was observed. All positive intervals are
multiples of 100 ms; the median positive interval is 100 ms in each file.
Raw adjacent timestamp median is zero because timestamps repeat.

| Session | First → last source time | Duration (min) | Rows | Row density (Hz) | Unique time bins | Duplicate rows | Largest interval (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| S1 | 09:07:39.7 → 10:55:05.0 | 107.422 | 644,460 | 99.9890 | 64,447 | 580,013 | 700 |
| S2 | 09:08:55.7 → 10:45:40.7 | 96.750 | 580,445 | 99.9904 | 58,045 | 522,400 | 500 |
| S3 | 11:25:31.7 → 11:34:04.0 | 8.538 | 51,130 | 99.8028 | 5,114 | 46,016 | 700 |
| S4 | 11:22:05.7 → 12:35:02.0 | 72.938 | 437,530 | 99.9769 | 43,754 | 393,776 | 1000 |
| S5 | 10:56:01.7 → 12:55:04.9 | 119.053 | 714,225 | 99.9866 | 71,423 | 642,802 | 800 |
| S6 | 10:55:55.6 → 12:52:00.0 | 116.073 | 696,320 | 99.9826 | 69,633 | 626,687 | 1200 |
| S7 | 10:51:50.0 → 12:44:01.0 | 112.183 | 673,009 | 99.9863 | 67,302 | 605,707 | 800 |
| S8 | 09:08:55.6 → 10:46:04.0 | 97.140 | 582,780 | 99.9895 | 58,279 | 524,501 | 600 |
| S9 | 09:08:09.8 → 10:49:23.3 | 101.225 | 607,275 | 99.9875 | 60,728 | 546,547 | 800 |

Across 4,987,174 rows there are 498,725 distinct per-file time bins and
4,488,449 repeated timestamp rows (89.9998%). Almost every
contiguous bin contains ten rows; partial boundary bins contain five rows, with
one four-row bin in S7. Every GNSS/quality field, heart rate and
`inst_acc_impulse` is constant inside each bin: **zero within-bin conflicts**.
Accelerometer and gyroscope axes usually change between the ten rows.

**INFERRED:** the export packs approximately 100 IMU records/s onto a 10 Hz
stored timestamp grid. Row density is `(rows − 1) / (last_time − first_time)`;
it is not an independently measured IMU timing frequency. **UNKNOWN:** precise
IMU timing/phase, rounding or truncation, gap causes, timezone/UTC offset, and
midnight handling outside this subset. Do not fabricate 10 ms timestamps.

GNSS bin cadence is approximately 10 Hz, but a bin is not guaranteed to contain
a fresh receiver fix. Coordinates also repeat between some bins; stationary
behavior, precision rounding and stale updates cannot be separated here.
Full profiles include per-field within-bin changes, unchanged-coordinate bin
counts, raw/bin interval distributions, and coordinate/GNSS-tuple change intervals.
Change intervals measure changes of encoded values, not receiver measurement
freshness. Plotting the first row per bin is explicitly a display proxy.

## 5. GNSS and IMU data quality

**OBSERVED, every row:** no null, NaN, or infinity occurs in any selected field.
No latitude outside ±90°, longitude outside ±180°, negative speed, negative
`hacc`, or nonpositive `hdop` occurs. This does not establish measurement validity.

All 4,987,174 heart-rate values equal zero. **INFERRED:** these likely represent
unavailable heart-rate measurements; actual sentinel semantics are UNKNOWN.
`hacc` spans 0–7 and equals zero in 4,517,340 rows (90.58%).
Zero cannot safely mean perfect accuracy. `hdop` spans 1–31, signal quality 0–359,
and satellite count 0–23. Their native encodings are retained without rescaling.

Zero satellite counts occur in 140 rows of S2 and 10 rows of S8. Exact `(0,0)`
coordinates occur in **three** files (the earlier progress estimate of four was
corrected by the completed counts):

| Session | Raw zero-pair rows | Time bins | Example source time | Example satellites / hacc / hdop / signal quality |
|---|---:|---:|---|---|
| S2 | 10 | 1 | 10:45:40.7 | 18 / 7 / 31 / 290 |
| S7 | 150 | 15 | 10:53:53.5 | 9 / 7 / 31 / 147 |
| S9 | 3,460 | 346 | 10:48:32.8 | 16 / 7 / 31 / 98 |

These coordinates pass simple degree-range checks. They produce enormous
artificial trajectory excursions and still coexist with positive satellite
counts; satellite count alone cannot validate position. **INFERRED:** exact
zero pairs are unavailable/invalid-position candidates, not real football
movement. They remain unchanged in raw data and appear in the complete raw
figure. The separate local view inserts visual gaps for exact zero pairs and
states how many were omitted. The local projection is only an approximation
near the session origin; million-metre excursions in the raw figure are anomaly
illustrations, not physically meaningful projected tracks.

The observed per-session movement summaries are:

| Session | Vendor speed p99.9 / max (m/s) | Zero vendor speed (%) | Acceleration norm median / p99.9 / max (g) | Gyroscope norm max (documented deg/s) |
|---|---:|---:|---:|---:|
| S1 | 5.936 / 6.906 | 34.92 | 1.131 / 5.244 / 11.449 | 3.050 |
| S2 | 4.164 / 5.006 | 58.25 | 1.133 / 5.787 / 13.097 | 3.671 |
| S3 | 1.714 / 2.053 | 72.84 | 1.132 / 3.176 / 4.845 | 1.608 |
| S4 | 3.044 / 3.953 | 50.21 | 1.143 / 4.922 / 15.271 | 5.116 |
| S5 | 7.081 / 7.928 | 17.00 | 1.128 / 5.886 / 13.319 | 3.301 |
| S6 | 4.506 / 6.206 | 26.57 | 1.134 / 5.356 / 13.455 | 4.156 |
| S7 | 6.639 / 7.758 | 25.60 | 1.137 / 6.602 / 13.629 | 6.596 |
| S8 | 4.728 / 6.003 | 58.18 | 1.137 / 4.740 / 11.154 | 3.879 |
| S9 | 6.275 / 7.311 | 48.42 | 1.124 / 6.366 / 11.666 | 3.013 |

Norms are descriptive calculations `sqrt(x² + y² + z²)` from source axes,
not raw sensor columns, translational acceleration, loads or criterion metrics.
`inst_acc_impulse` remains a separate vendor-derived field. The acceleration
norm's approximately 1.13 g median is **OBSERVED**; gravity inclusion or
calibration bias remains **UNKNOWN**. Extremes up to 15.271 g are suspicious
inspection candidates; impacts, device handling and clipping cannot be separated
without supporting information. No values were clipped or replaced.

Gyroscope numeric magnitudes are small (maximum norms 1.608–6.596). The paper's
deg/s unit is retained as DOCUMENTED, but the file supplies no calibration/unit
metadata. Do not infer radians/s or rescale from plausible motion alone. No
orientation, linear acceleration, rotation angle, sensor fusion, or sprint
classification was calculated.

Identical schemas conceal large differences in duration, motion distributions,
quality encodings, timestamp gaps and zero-position occurrences. S3's low-speed
pattern cannot establish rest or an activity category; S9's nonzero trajectory
also extends several hundred metres, whose context remains UNKNOWN.

## 6. Generated figures and interpretation

All panels use manifest order S1–S9. Axes have independent ranges; compare
numbers as well as shapes. All eight PNGs were opened and visually checked.

| Figure | Interpretation |
|---|---|
| [Local GNSS trajectories](../outputs/v0b1_soccermon_analysis/gnss_trajectories_local_view.png) | Approximate local east/north metres. Exact zero pairs are omitted for display and leave gaps; counts are annotated. No pitch, venue, or activity label is assumed. |
| [Raw GNSS trajectories](../outputs/v0b1_soccermon_analysis/gnss_trajectories.png) | Retains zero pairs, exposing large excursions in S2/S7/S9. Green/red denote first/last bin. |
| [Speed versus time](../outputs/v0b1_soccermon_analysis/speed_vs_time.png) | Vendor speed from the first row per stored time bin. Source m/s, no truth comparison or intensity thresholds. |
| [Acceleration magnitude](../outputs/v0b1_soccermon_analysis/acceleration_magnitude_vs_time.png) | Source-axis norm in g; 10 s median line and finite min–max envelope retain extremes. Gravity semantics remain unresolved. |
| [Gyroscope magnitude](../outputs/v0b1_soccermon_analysis/gyroscope_magnitude_vs_time.png) | Same 10 s display aggregation; units explicitly labeled as documented deg/s. |
| [Sampling intervals](../outputs/v0b1_soccermon_analysis/sampling_intervals.png) | Exact raw adjacent interval counts on a logarithmic count axis; 0 and 100 ms dominate, with rare gaps. |
| [GNSS quality](../outputs/v0b1_soccermon_analysis/gnss_quality.png) | 10 s median/min–max of native hacc/hdop codes and satellite counts; not calibrated accuracy. Signal-quality ranges and anomalies are in the full profiles. |
| [Missing values](../outputs/v0b1_soccermon_analysis/missing_values.png) | Null/NaN/infinity percentage is zero throughout. Possible zero sentinels are separate in the [CSV](../outputs/v0b1_soccermon_analysis/missing_values.csv). |

Plot aggregation is display-only. Profile statistics use every original row;
GNSS statistics therefore are row-weighted repeated exports, not independent-fix
statistics. Raw axes and vendor-derived quantities remain separately named in
[full_profiles.json](../outputs/v0b1_soccermon_analysis/full_profiles.json).
No plots interpolate IMU timestamps between shared bins.

## 7. Compatibility with V0A and differences from Walking

**OBSERVED repository compatibility; INFERRED next-step decisions:**

| SoccerMon evidence | TrackingSession compatibility / required decision |
|---|---|
| `player_name` has constant `TeamB-UUID` | Reuse `subject_id` concept after explicit prefix handling; preserve original identity and exact member as recording provenance. |
| Degree `lat/lon`, vendor m/s `speed` | Existing GNSS fields are reusable after separate validity flags and bin semantics are defined. Preserve vendor origin for speed. |
| No altitude, heading or path curvature | Optional existing fields can remain `None`; do not manufacture values. |
| String time of day plus hierarchy date | Parse losslessly; retain raw text/date/row ordinal. Analysis elapsed time can be derived, but epoch timestamps require a timezone policy. Never guess UTC. |
| Repeated GNSS fields, distinct IMU rows | Preserve raw row order; do not deduplicate whole rows by timestamp. A staged GNSS bin view needs audited conflicts and explicit freshness uncertainty. |
| `hacc` unit/encoding unknown, mostly zero | Do not populate `horizontal_accuracy_m` with these integer codes. Preserve in a quality sidecar until unit/zero semantics are resolved. |
| Accelerometer g | Numerical conversion to m/s² is ×9.80665 if chosen later; gravity semantics determine the correct canonical acceleration fields. Keep source g meanwhile. |
| Gyroscope x/y/z, documented deg/s | Current alpha/beta/gamma fields have no safe established correspondence. Propose explicit axes/unit metadata before canonical mapping; conversion to rad/s, if chosen, is ×π/180. |
| No ordinary-session criterion field | Mandatory `GroundTruth` and `gt_type` are mismatched. Decide explicit no-ground-truth representation in V0B.3; do not substitute vendor speed/distance. |
| Heart rate, HDOP, signal quality, satellites, impulse | Preserve all typed columns in staging/sidecars; canonical fields do not currently cover them. Keep vendor impulse separate from measured axes. |
| Date/team/year/provenance, uncertain cadence and units | Structured metadata should preserve archive/member hashes, player string, recording bounds, raw timestamp representation, documented versus inferred rates, unit evidence and unknowns. |
| Near 100 rows/s in files up to two hours | Prefer row-group/batch staging over millions of eager Python sample objects. Existing GNSS calculations can be reused after timestamp/validity policy; V0A configuration must remain unchanged. |

Walking supplies controlled test windows and continuous/final distance references,
CSV streams and smartphone-specific fields. The inspected SoccerMon subset
contains longer worn-device records, mixed row/bin cadences, wearable IMU axes,
vendor metrics, richer quality fields and no criterion column. Its entire file
is a recording window, not verified playing time. Walking's timestamp sorting,
window clipping, distance alignment and reference-error evaluation cannot be
transferred unchanged. V0A's six real-session importer checks still pass.

## 8. Remaining uncertainties

- Timezone, clock rounding/truncation, true IMU sample times, ordering inside each bin,
  export interpolation/decimation, and receiver-fix freshness.
- `hacc` units/encoding and zero semantics; HDOP and signal-quality scaling;
  behavior of `(0,0)` coordinates alongside positive satellite counts.
- Accelerometer gravity inclusion, bias, axis orientation, saturation/handling
  artifacts; independent verification of gyroscope unit/axis conventions.
- Why the short S3 record ends after 8.54 minutes, why gaps occur, and what
  parts of longer files represent playing, pauses, warm-up or handling.
- Activity/match labels, independent criterion data, calendar-midnight behavior,
  other-file schema variation and identifier/device stability beyond this sample.
- The selected files cannot resolve the paper's separate validation exercise;
  no per-session criterion was located here. No additional dataset was downloaded.

## 9. Recommended V0B.2 implementation plan

1. Build a separate lossless SoccerMon staging reader, returning typed batches
   plus immutable source metadata, raw time strings, hierarchy date, player
   string and row ordinal. Keep every observed column and file hash.
2. Validate schema differences explicitly, allow documented/observed timestamp
   representations deliberately, and report missing/invalid values without
   modifying source data. Flag candidate sentinels separately from nulls.
3. Represent stored 100 ms bins and ordered IMU rows faithfully. A GNSS view
   may take one consistent tuple per bin with conflict reporting, while exposing
   unknown measurement freshness. Keep exact IMU timestamps unavailable rather
   than silently reconstructing 10 ms spacing.
4. Add synthetic fixtures for repeated-bin axes, conflicting GNSS values,
   zero-position codes, missing values, gaps, backwards times/midnight,
   multiple identities and schema mismatch. Validate the nine-file manifest
   with bounded integration checks and unchanged raw hashes.
5. Before V0B.3 canonical mapping, decide no-ground-truth support, timestamp
   provenance, axis/unit representation and quality/context sidecars. Resolve
   `hacc` and IMU semantics through authoritative evidence where possible.
   Keep V0A behavior covered by its existing tests.

V0B.2 should stop at validated staging, with canonical model changes considered
separately. Sprint detection, filtering/fusion, Kalman methods and ML remain
deferred.

## 10. Files created or modified and reproduction

Created:

- `scripts/prepare_soccermon_subset.py`: deterministic selection, full CRC/checksum
  verification, budget/disk checks, exact extraction and per-file checksums.
- `scripts/analyze_soccermon_subset.py`: full subset schema/cadence/anomaly profiling
  and explicit plotting proxies; no canonical importer.
- `tests/test_soccermon_inspection.py` and `tests/test_soccermon_analysis.py`.
- `requirements-v0b1.txt`, `.venv/` and this report.
- `data/raw/soccermon/subset/`: exactly the nine ignored Parquet files above.
- `outputs/v0b1_soccermon_inventory/`: outer inventory/member list, selection,
  extracted/checksum manifest, disk checks, archive verification, environment,
  preservation/reproduction checks, utility hashes, test results and log.
- `outputs/v0b1_soccermon_analysis/`: eight PNG figures, full profiles,
  Parquet metadata, analysis summary, missing-value CSV and local Matplotlib cache.

Modified: only `scripts/inspect_zip_archive.py`, adding machine-readable details
for each ZIP member. Existing inspection/extraction behavior is retained.
Existing extractor, Parquet inspector, V0A source/tests/outputs, preparation report
and `.gitignore` were not edited. The workspace already contained untracked
project files; none were committed or pushed.
[Baseline preservation check](../outputs/v0b1_soccermon_inventory/preservation_check.json)
records the existing-file comparison.

Reproduce from repository root with Python 3.13 (the audited runtime is 3.13.5,
macOS arm64; pinned dependency versions are in `requirements-v0b1.txt`):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-v0b1.txt
# On a fresh/empty subset only; performs full verification again.
.venv/bin/python scripts/prepare_soccermon_subset.py \
  data/raw/soccermon/objective-TeamB-2020.zip --extract
# On the existing subset, rerun read-only inspection/figure generation directly.
.venv/bin/python scripts/analyze_soccermon_subset.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

To independently replay extraction while keeping the current raw subset, supply
`--output data/raw/soccermon/subset/reproduction` and
`--reports outputs/v0b1_soccermon_reproduction`, then pass that extracted manifest
to the analyzer with its own `--output`. The preparer checks the entire cumulative
subset root against 2 GiB and refuses any existing selected destination. Do not
repeat extraction into the same destination. Analysis may replace its generated
outputs; raw files are read-only.

## 11. Validation and test results

`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`:
**44 tests passed, zero skips** in the final run. This includes the existing
V0A GNSS/robustness/Walking importer suite, existing inspection helper tests,
five new inventory/selection/budget guards and three new sensor-audit tests.
New cases cover archive-order independence, insufficient common players,
quantile collisions, ambiguous filenames, cumulative budget/free-space failure,
precise timestamp parsing, backwards times, missing-bin plot aggregation,
preservation of IMU rows sharing a timestamp, conflicting GNSS tuples,
zero coordinates and checksum mismatch.

An initial invocation lacked `PYTHONPATH=src` and could not import the package;
that command was corrected. A synthetic small-inventory test exposed colliding
date indices; the selection helper now chooses distinct dates deterministically.
The actual 138-date selection was unaffected and its replay was verified.
[Test log](../outputs/v0b1_soccermon_inventory/tests.log) and
[machine-readable results](../outputs/v0b1_soccermon_inventory/test_results.json)
record the successful final command.

Additional validation: all archive CRCs and official MD5 passed; all selected
file sizes and SHA-256 checks matched after analysis; current utility selection
reproduced exact members; source ZIP size/mtime remained unchanged; raw data and
local environment are ignored by Git; existing V0A files match baseline hashes;
all eight figures were visually inspected. No anomalies were silently repaired.
