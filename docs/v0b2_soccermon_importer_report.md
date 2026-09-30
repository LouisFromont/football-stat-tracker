# V0B.2 — SoccerMon importer

Completed 2026-09-30. The importer returns a canonical `TrackingSession` while
retaining native sensor values, original timestamp text, source row references
and recording provenance. All nine existing subset recordings were imported
and checked against every source row. No timestamps were reconstructed, and no
sprint detection, fusion, filtering, ML or threshold optimization was added.

## Baseline and evidence

**OBSERVED:** the initial working tree was clean. Commit `9969661` contains V0A,
V0B.1, both prior reports and the existing 44 tests. Both reports, source and
tests were read before editing. The project uses standard-library unittest;
the baseline passed all 44 tests with zero skips in the existing `.venv`.
The preliminary `python3 -m pytest` command could not run because pytest was
not installed; no dependency was installed to change the test framework.

Evidence labels:

- **DOCUMENTED:** explicitly stated by an authoritative source.
- **OBSERVED:** measured in the nine local files or repository.
- **INFERRED:** an engineering policy or interpretation.
- **UNKNOWN:** not established by the available evidence.

The current request explicitly includes minimal canonical mapping in V0B.2,
advancing the staging-only scope proposed in the earlier V0B.1 report.

**DOCUMENTED:** the authors list degrees for position, m/s for vendor speed,
g for acceleration axes, deg/s for gyro axes, bpm for heart rate and m/s² for
the vendor impulse. They give nominal export rates of 10 Hz for GNSS/auxiliary
fields and 100 Hz for IMU axes, and describe millisecond time strings. Quality
code scales and gravity inclusion are unspecified.
[Official Table 3](https://www.nature.com/articles/s41597-024-03386-x/tables/3?error=cookies_not_supported).
The paper describes STATSports APEX hardware and qualifies firmware processing
as likely; it does not establish per-recording independent criterion data.
[Data descriptor](https://www.nature.com/articles/s41597-024-03386-x).
The [official dataset page](https://datasets.simula.no/soccermon/) and
[accompanying repository](https://github.com/simula/soccermon) did not resolve
the encoding or precise timing questions. No further dataset was downloaded.

## Actual schema and conventions

**OBSERVED, all nine files:** 17 nullable fields, one row group, SNAPPY,
fastparquet 0.8.1 producer, pandas 1.4.2 metadata, no unit/timezone metadata.

| Source fields | Arrow / Parquet type | Source semantics |
|---|---|---|
| `player_name`, `time` | string / BYTE_ARRAY (String) | One constant TeamB-player identifier; time of day |
| `lat`, `lon`, `speed` | double / DOUBLE | Degrees, vendor m/s |
| `heart_rate`, `hacc`, `hdop`, `signal_quality`, `num_satellites` | int64 / INT64 | Native bpm/quality/count values; quality scales UNKNOWN |
| `inst_acc_impulse` | double / DOUBLE | Vendor-derived m/s² |
| `accl_x/y/z` | double / DOUBLE | Documented g; gravity, axis orientation and calibration UNKNOWN |
| `gyro_x/y/z` | double / DOUBLE | Documented deg/s; independent unit and orientation verification UNKNOWN |

The real identity column is `player_name`, rather than Table 3's `id`.
No altitude, heading, magnetometer, independent truth or activity labels occur
in these files. The date and team context are present in the path/filename.

**OBSERVED:** all time strings have one fractional digit. Source order is
nondecreasing. Approximately ten IMU rows share each timestamp; the axes usually
change within those groups. Every GNSS field, heart rate and impulse is constant
within each group. Partial boundary groups have five rows, or four in one S7
group. Adjacent distinct timestamps are usually 100 ms apart, with rare gaps.

**INFERRED:** this is a mixed-cadence export onto a coarse stored time grid.
Row density near 100 rows/s does not establish physical IMU timing.
**UNKNOWN:** clock phase, rounding/truncation, IMU intervals within groups,
decimation, timezone, gap causes and receiver-fix freshness. No midnight crossing
was observed; its general interpretation remains UNKNOWN.

**OBSERVED:** adjacent different time groups sometimes have identical coordinates
(counts S1–S9: 2,447; 1,694; 377; 1,476; 695; 2,478; 1,182; 3,797; 3,398).
Successive groups often change their encoded position/quality values, but neither
changes nor unchanged coordinates prove a fresh fix. Stationary positions,
rounding and stale updates remain indistinguishable (**UNKNOWN**).

**OBSERVED:** there are no nulls, NaNs or infinities in this subset, and no
out-of-range latitude/longitude. However, S2/S7/S9 contain exact zero pairs.
These occur alongside positive satellite counts. Heart rate is zero throughout;
hacc spans 0–7, hdop 1–31, signal quality 0–359 and satellites 0–23. Hacc is zero
in 4,517,340 rows; zero satellite counts occur in 150 rows. **INFERRED:** heart-rate
zeros may signify unavailable readings; **UNKNOWN:** their sentinel semantics.
Non-null values are therefore not automatically valid measurements.

## Architecture and canonical mapping

The existing numerical modules and Walking importer are unchanged. New model
members have defaults, preserving existing constructors and Walking outputs:

- `TrackingSession.ground_truth` and `SessionMetadata.gt_type` permit `None`.
  Absence is explicit; no vendor metric is substituted as truth.
- Optional `RecordingProvenance` carries absolute source path, SHA-256, row
  count, column names/types, original Parquet key/value metadata bytes, timestamp
  basis, producer, row groups and filename date when available.
- Optional `RawSensorSample` carries original time text, native values with
  shared column names, and a zero-based contiguous source row range. IMU ranges
  always contain one row; GNSS ranges record repeated exports.
- GNSS gains optional coordinate status and observation kind. These describe
  SoccerMon candidates without changing existing geometry code.

This generic sidecar is smaller than adding separate canonical fields for every
unresolved vendor code or forcing device axes into Walking's rotation labels.
It also allows all 17 columns to be reconstructed by joining GNSS row ranges,
IMU rows and the constant identity. Present null and absent optional column are
distinguishable through the source column lists.

| SoccerMon source | Canonical mapping |
|---|---|
| `player_name` | `metadata.subject_id`, unchanged, including TeamB prefix |
| Filename stem | `metadata.recording_id`; full resolved path and content hash preserve provenance |
| Parsed `time` | `timestamp_raw_ms`, exact local milliseconds since midnight |
| Original `time` and row order | `raw_source.timestamp_original`, `source_row_index` |
| `lat/lon` | Canonical degrees when numerically usable; originals always in GNSS raw sidecar |
| `speed` | `speed_mps`, explicitly vendor-derived; original retained |
| `hacc/hdop/signal_quality/num_satellites` | Native GNSS raw sidecar; no quality filtering or rescaling |
| `heart_rate/inst_acc_impulse` | GNSS raw sidecar as auxiliary fields, without claiming they are GNSS measurements |
| `accl_x/y/z`, `gyro_x/y/z` | IMU raw sidecar, documented source units; legacy IMU numerical fields remain `None` |
| No independent truth | `ground_truth=None`, `gt_type=None`, `distance_reference_m=None` |
| Unknown physical cadence | `fs_acc_hz=None`, `fs_gnss_hz=None`; documented nominal rates are separately labeled in provenance context |

Dates matching `YYYY-MM-DD-player.parquet` are calendar-validated; the player
suffix must match the source identity. Arbitrary filenames are supported with
date unavailable. One file is one recording; multiple identities in a file are
rejected. There is no reliable marker for concatenated sessions of the same
player, so the importer does not invent boundaries or split files.

## Timestamp policy

**INFERRED engineering policy:** accept only exact `HH:mm:ss` with zero to three
fractional digits; validate ranges and parse with integer arithmetic. Unsupported
precision, timezone strings, date-time strings or null times produce clear errors.
No time-of-day value is converted into an epoch or assigned UTC.

Analysis time is raw time minus the minimum stored time of day. The legacy
`test_start_raw_ms`/`test_end_raw_ms` slots contain the minimum/maximum time-of-day
values, representing the recording span, not verified playing or test time.
Source order and all repeats remain unchanged. Backwards intervals are retained
and counted; no sorting or midnight rollover is applied. `duration_s` is unavailable
when any interval is negative; `time_of_day_span_s` remains a descriptive range,
not an elapsed-duration claim. A future estimated timeline would need separate
fields and explicit assumptions; none is implemented here.

## GNSS deduplication and invalid-data policies

**INFERRED engineering policy:** collapse only consecutive rows with identical
original time text and identical values across every present GNSS/auxiliary field.
Carry the first row index and full range count. Never merge across different
time strings, across intervening values, or solely by latitude/longitude. Preserve
within-time conflicts as multiple candidates and report groups with multiple
candidates. This policy also works across Arrow batch/Parquet row-group boundaries.
Signed zero differences are retained; NaN-bearing candidates are conservatively
kept separately. This is reversible export compression, not a fix-acquisition
inference. Each entry has `observation_kind="timestamp_group_candidate"`.
Independently identifiable fix counts are `None`, rather than zero or the number
of groups. A stationary player's groups are preserved.

Coordinates receive `usable`, `missing`, `non_finite`, `out_of_range` or
`zero_pair`. Exact `(0,0)` is treated as an invalid-position sentinel candidate
for this importer (**INFERRED**, supported by the subset anomalies). A single
zero axis remains legal. Invalid canonical coordinate pairs are `None`; raw
values and source ranges remain intact. `usable` denotes numerical geographic
usability, not known accuracy, freshness or correct location.

No quality threshold, satellite rule, speed rule, clipping or imputation is
applied. Negative/zero/non-finite sensor and vendor measurements remain raw.
Sensor nulls remain `None`. Unknown quality units keep `horizontal_accuracy_m`
unset. Existing distance functions skip invalid canonical positions and connect
the preceding valid point to the following valid point; they do not reconstruct
the missing path. V0B.3 must account for those gaps explicitly.

Required columns are `player_name`, `time`, `lat`, `lon` and six IMU axes.
Optional numeric columns are speed, quality, heart rate and impulse. Integer,
floating and all-null numeric columns are accepted without string coercion;
identity/time must be strings with nonmissing values. Empty, corrupt, missing,
duplicate-column, wrong-type or multi-player files raise `SoccerMonImportError`.
Unknown extra columns are rejected explicitly to avoid silent data loss.

## Units

Only time strings are converted, exactly, into integer milliseconds. Position
degrees and vendor m/s values need no conversion. Native IMU axes are retained:
conversion of g by 9.80665 would change numerical units but would not resolve
gravity semantics; deg/s to rad/s would require ×π/180 but would not resolve axis
mapping/calibration. Neither transformation is performed. Source units are
available as `SOURCE_UNITS` in the importer. Hacc/HDOP/signal quality are never
assumed to be metres or rescaled based on plausibility.

## Tests and real-data validation

`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`:
**72 tests passed, zero skips**. This comprises the original 44, one model test,
25 importer/time-parser tests and two validation-audit tests. Synthetic Parquet cases cover valid/native
values; timestamps and ordering; stationary positions; repeated exports;
coordinate/quality/auxiliary conflicts; signed zeros, nulls, NaN and infinity;
invalid geographic coordinates; missing optional/required fields; absent truth;
backwards/midnight times; multiple players and recordings; identity/date mismatch;
batch boundaries; full row reconstruction; malformed files and schemas.
Existing real Walking imports, ground-truth alignment and V0A numerical tests pass.
The audit tests confirm rejection of changed sensor values and manifest hash
mismatch before importing an untrusted file. Validation checks also run with
Python assertions disabled.

`scripts/validate_soccermon_imports.py` imports manifest-selected files one at a
time, expands GNSS source ranges, checks every original timestamp, identity and
native sensor value, and verifies SHA-256 before/import/after against the V0B.1
manifest. All nine passed. Total: **4,987,174 source rows = 4,987,174 preserved
IMU samples; 498,725 GNSS candidates**. All original file hashes are unchanged.

S labels follow V0B.1 manifest order. Player prefixes below identify the full
IDs/paths already listed in that report. Independently identifiable fixes are
**UNKNOWN in every session**. All sessions share the ambiguities listed above;
none has within-group conflicts, negative intervals or observed midnight crossing.

| Session | Date | Player prefix | Source rows | IMU samples | GNSS candidates | Invalid candidates / source rows | Duplicate timestamp rows | Duration (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| S1 | 2020-06-17 | afc13e53 | 644,460 | 644,460 | 64,447 | 0 / 0 | 580,013 | 6,445.3 |
| S2 | 2020-06-17 | 48bfd4ea | 580,445 | 580,445 | 58,045 | 1 / 10 | 522,400 | 5,805.0 |
| S3 | 2020-08-27 | afc13e53 | 51,130 | 51,130 | 5,114 | 0 / 0 | 46,016 | 512.3 |
| S4 | 2020-08-27 | 48bfd4ea | 437,530 | 437,530 | 43,754 | 0 / 0 | 393,776 | 4,376.3 |
| S5 | 2020-11-19 | afc13e53 | 714,225 | 714,225 | 71,423 | 0 / 0 | 642,802 | 7,143.2 |
| S6 | 2020-11-19 | 48bfd4ea | 696,320 | 696,320 | 69,633 | 0 / 0 | 626,687 | 6,964.4 |
| S7 | 2020-11-19 | 70b74270 | 673,009 | 673,009 | 67,302 | 15 / 150 | 605,707 | 6,731.0 |
| S8 | 2020-06-17 | 789547e7 | 582,780 | 582,780 | 58,279 | 0 / 0 | 524,501 | 5,828.4 |
| S9 | 2020-06-17 | 247a8333 | 607,275 | 607,275 | 60,728 | 346 / 3,460 | 546,547 | 6,073.5 |

Invalid pairs total **362 candidates / 3,620 raw rows**. Timestamp repeats total
**4,488,449 rows**; the row-adjacent interval median is 0 ms. Positive stored
intervals below describe the encoded clock, not physical sample frequencies:

| Session | Positive stored intervals in ms (count) |
|---|---|
| S1 | 100 (64,444), 200 (1), 700 (1) |
| S2 | 100 (58,041), 200 (2), 500 (1) |
| S3 | 100 (5,109), 200 (2), 300 (1), 700 (1) |
| S4 | 100 (43,751), 200 (1), 1,000 (1) |
| S5 | 100 (71,419), 200 (1), 300 (1), 800 (1) |
| S6 | 100 (69,630), 200 (1), 1,200 (1) |
| S7 | 100 (67,298), 200 (2), 800 (1) |
| S8 | 100 (58,276), 200 (1), 600 (1) |
| S9 | 100 (60,725), 200 (1), 800 (1) |

The minimum and median positive interval are 100 ms in every recording. No
physical IMU frequency or independent GNSS-fix rate is claimed.

Reproduce from the repository root with the existing subset and project environment:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python scripts/validate_soccermon_imports.py
```

The ignored [validation JSON](../outputs/v0b2_soccermon_importer/validation_summary.json)
contains counts, intervals, ambiguity labels and checksums without raw coordinates.
The committed tables above retain the concise results for a fresh checkout.
README provides a one-recording import example.

## Limitations and safe V0B.3 use

The nine-file evidence does not guarantee other SoccerMon schemas. Unknown
columns/types require an explicit importer extension. Arrow parsing is batched,
but returned canonical streams are eager tuples with O(rows) memory; load one
recording at a time. The full dataset is outside this importer validation scope.
Provenance dates are filename-derived, not timezone-aware observation dates;
file stems are not guaranteed globally unique after arbitrary renaming. Schema
column types and original metadata are retained, but this is not a byte-for-byte
Parquet serializer; the content hash anchors the unchanged original file.

V0B.3 can safely use ordered IMU native axes for descriptive source-unit plots,
timestamp-group GNSS candidates for coordinate/quality/gap inspection, vendor
speed as a comparison signal, explicit coordinate statuses, and provenance for
audits. Consumers must handle `ground_truth=None` and unset legacy IMU fields.
Time derivatives within IMU groups and truth-relative error metrics are not
supported. Quality zero meanings, hacc scale, precise timing, GNSS freshness,
gravity/orientation, gyro calibration and playing-time labels remain UNKNOWN.

Recommended next step: characterize candidate GNSS gaps and native quality
encodings, and seek authoritative device/export clarification for timing and
IMU conventions before introducing calibrated time-dependent metrics.

## Local milestones and changed files

- `5d3b3db`: optional ground truth and sensor provenance support; model test;
  package exports. All 45 tests passed before committing.
- `e382b04`: SoccerMon importer and 25 focused tests; importer exports.
  All 70 tests passed before committing.
- Final milestone: this report, README example and reproducible validation script.

Changed files: `src/football_stat_tracker/data_model.py`, package and importer
`__init__.py`, `importers/soccermon.py`, `tests/test_data_model.py`,
`tests/test_soccermon_importer.py`, `tests/test_soccermon_validation.py`,
`scripts/validate_soccermon_imports.py`,
`README.md`, and this report. The prior reports remain unchanged. Commits contain
source, tests and documentation only; no datasets, Parquet, archives, environment,
caches, personal traces or large generated outputs are staged. No push or history
rewrite was performed.
