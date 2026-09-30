# V0B preparation report — SoccerMon

Prepared on 2026-09-30. No SoccerMon archive was locally available during
this audit. Labels have the following strict meanings:

- **DOCUMENTED**: stated by the SoccerMon paper, dataset page, or accompanying
  public material.
- **INFERRED**: a proposed interpretation or engineering choice, not yet
  verified against the local archive.
- **UNKNOWN**: requires inspection of the downloaded files.

Primary sources:

- [SoccerMon data descriptor](https://www.nature.com/articles/s41597-024-03386-x)
- [SoccerMon dataset page](https://datasets.simula.no/soccermon/)
- [Zenodo dataset DOI](https://doi.org/10.5281/zenodo.10033832)
- [Official accompanying repository](https://github.com/simula/soccermon)

## 1. Current Football Stat Tracker architecture

`data_model.py` provides an immutable, source-independent object graph:

- `TrackingSession` contains `SessionMetadata`, a tuple of `GnssSample`, a
  tuple of `ImuSample`, and one typed ground-truth object.
- GNSS samples use numeric raw and analysis timestamps in milliseconds, WGS84-
  shaped latitude/longitude fields, optional altitude, source speed, heading,
  and horizontal accuracy.
- IMU samples use the same two timestamp concepts, three acceleration axes,
  three acceleration-including-gravity axes, and three rotation-rate fields.
- Ground truth is mandatory and is either a continuous distance series or one
  final distance, with explicit alignment semantics.

`importers/walking.py` is the dataset boundary. It reads Walking CSV files,
validates required columns, sorts and clips streams to the test window,
normalizes timestamps, maps missing optional values to `None`, and handles
continuous/final ground truth without leaking Walking parsing into the core.

`gnss.py` contains the untouched raw baseline: validated Haversine distance and
the sum between successive valid positions. `gnss_diagnostics.py` contains
source-independent segment, speed, accuracy, cumulative-distance, and local-
projection diagnostics. `gnss_robust.py` adds an auditable configurable segment
classifier while preserving the raw baseline. Scripts generate CSV/SVG outputs;
the standard-library unittest suite covers the model-facing behavior and real
Walking sessions.

### Directly reusable

- **DOCUMENTED from repository audit**: `GnssSample` latitude, longitude,
  source speed, and horizontal-accuracy slots correspond conceptually to
  published SoccerMon fields.
- **DOCUMENTED from repository audit**: raw Haversine distance and most GNSS
  diagnostic functions are source-independent.
- **INFERRED**: the robust estimator's mechanism is reusable after cadence and
  timestamp mapping are verified, but its V0A configuration must not silently
  become a SoccerMon-tuned configuration.
- **DOCUMENTED from repository audit**: importer isolation, immutable results,
  explicit missing values, and synthetic tests are reusable patterns.

### Walking-specific

- CSV filenames/columns, `events.csv`, `metadata_tracks.csv`, test-window
  clipping, continuous reference-distance interpolation, `path_curvature`, and
  the six-session evaluation scripts.
- `test_start_raw_ms`/`test_end_raw_ms` names and mandatory distance ground
  truth reflect the Walking experiment.
- Walking IMU field names and the unresolved alpha/beta/gamma rotation mapping.

### Assumptions that may fail for football

- A session must have distance ground truth. SoccerMon documents none for each
  ordinary session.
- Raw timestamps must already be numeric milliseconds. SoccerMon documents
  time-of-day strings with millisecond granularity; date is carried by archive
  hierarchy, and timezone is unknown.
- All data is eagerly materialized as Python object tuples. This is acceptable
  for a laptop subset but inappropriate for the full ~93 GB dataset.
- `ImuSample` cannot represent heart rate, HDOP, signal quality, satellite
  count, absolute acceleration impulse, or magnetometer values.
- Accelerometer axes in canonical units are m/s², while SoccerMon publishes g.
- The current rotation names do not safely express documented x/y/z gyroscope
  axes or an explicit unit.
- One Parquet record contains mixed nominal cadences (10 Hz and 100 Hz). A
  naive row-for-row GNSS mapping could duplicate/interleave observations and
  corrupt geometric-speed calculations.
- Activity type, team, season, calendar date, player position, device ID, and
  recording provenance have no clean canonical home.
- Football sessions are longer, intermittent, and may include bench/warm-up or
  off-pitch periods. A full file is not automatically equivalent to playing
  time.

## 2. SoccerMon objective structure and evidence status

| Statement | Status |
|---|---|
| Data came from two professional teams in the Norwegian women's Toppserien during 2020–2021. | **DOCUMENTED** |
| Objective data came from STATSports APEX units and includes 10,075 player-session reports from 76 anonymized players. | **DOCUMENTED** |
| Published objective data totals about 92.3 GB and uses Apache Parquet. | **DOCUMENTED** |
| Objective hierarchy is team → year → month → day; public secondary documentation describes one daily ZIP containing one Parquet file per player/session on that date. | **DOCUMENTED** |
| `objective-TeamB-2020.zip`'s exact internal root names, counts, and compression nesting match that description. | **UNKNOWN** |
| Each objective report is measurements from one sensor unit during one worn session, with one record per measurement and 17 published parameters. | **DOCUMENTED** |
| Filenames and player IDs are anonymized/randomized; the same anonymized player IDs link objective and subjective data. | **DOCUMENTED** |
| GNSS coordinates are present as latitude/longitude degrees. | **DOCUMENTED** |
| GNSS hardware is multi-constellation at 10 Hz. Published lat/lon, speed and GNSS-quality fields are listed at 10 Hz. | **DOCUMENTED** |
| Device hardware includes a 952 Hz tri-axial accelerometer and gyroscope plus a 10 Hz magnetometer; exported accelerometer and gyroscope columns are documented at 100 Hz. | **DOCUMENTED** |
| Why/how 952 Hz hardware data becomes 100 Hz exported data. | **UNKNOWN** |
| Raw magnetometer axes are included in the released Parquet files. | **UNKNOWN**; they are absent from the published 17-column table. |
| Firmware likely pre-filtered the GNSS data. | **DOCUMENTED** as the authors' qualification, not as a known filter specification. |
| Exact Parquet physical/logical types, row-group layout, nullability, compression, and metadata. | **UNKNOWN** |
| Missing values use nulls, NaN, sentinels, repeated samples, or a mixture. | **UNKNOWN** |
| `time` contains time of day (`HH:mm:ss.SSS`); timezone, UTC offset, midnight behavior, and whether date also appears in-file are known. | Time format **DOCUMENTED**; remaining details **UNKNOWN**. |
| `speed` is sensor-calculated m/s. | **DOCUMENTED**; it is vendor-derived and not ground truth. |
| An independent criterion trajectory/distance is supplied for every session. | **UNKNOWN/NOT DOCUMENTED**. The paper describes a separate seven-player two-lap validation exercise, not a per-session criterion stream in the published 17 fields. |
| Activity labels distinguish match, team training, individual training, warm-up, and bench periods inside objective files. | **UNKNOWN** |

### Published objective fields

| Field | Published meaning/unit | Nominal rate | Evidence status |
|---|---|---:|---|
| `time` | time of record, `HH:mm:ss.SSS` | n/a | **DOCUMENTED** |
| `id` | sensor ID replaced by anonymized athlete ID | n/a | **DOCUMENTED** |
| `heart_rate` | beats/min | 10 Hz | **DOCUMENTED** |
| `lat`, `lon` | degrees | 10 Hz | **DOCUMENTED** |
| `speed` | sensor-calculated m/s | 10 Hz | **DOCUMENTED** |
| `hacc` | horizontal accuracy; unit not stated in Table 3 | 10 Hz | **DOCUMENTED**, unit **UNKNOWN** |
| `hdop` | horizontal dilution of precision | 10 Hz | **DOCUMENTED** |
| `signal_quality` | GNSS signal quality | 10 Hz | **DOCUMENTED**, encoding **UNKNOWN** |
| `num_satellites` | satellites used | 10 Hz | **DOCUMENTED** |
| `inst_acc_impulse` | absolute acceleration, m/s² | 10 Hz | **DOCUMENTED**; vendor processing semantics beyond this label **UNKNOWN** |
| `accl_x/y/z` | acceleration along device axes, g | 100 Hz | **DOCUMENTED**; gravity inclusion and axis orientation **UNKNOWN** |
| `gyro_x/y/z` | angular rate along device axes, deg/s | 100 Hz | **DOCUMENTED**; axis orientation/sign convention **UNKNOWN** |

No published altitude or heading column appears in the 17-field table.

## 3. Proposed mapping — do not implement before schema inspection

| SoccerMon source | Meaning/unit | Canonical target | Mapping decision |
|---|---|---|---|
| hierarchy date + `time` | date plus millisecond time of day | `timestamp_raw_ms`, `timestamp_analysis_ms` | **Conversion required**; timezone/raw-preservation issue unresolved |
| `id` | anonymized player/unit ID | `SessionMetadata.subject_id` | **Direct concept**, verify type/stability |
| archive/member identity | player-session report | `recording_id` | **Conversion required**; preserve full provenance |
| team/year/month/day | context | no adequate field | **Unsupported**; propose structured provenance/context metadata |
| file min/max time | worn-session bounds | `test_start_raw_ms`, `test_end_raw_ms` | **INFERRED conversion**, naming is awkward |
| `lat` | degrees | `GnssSample.latitude_deg` | **Direct** after validity/null inspection |
| `lon` | degrees | `GnssSample.longitude_deg` | **Direct** after validity/null inspection |
| `speed` | vendor-calculated m/s | `GnssSample.speed_mps` | **Direct as source metric**, never ground truth |
| `hacc` | horizontal accuracy, unit unknown | `GnssSample.horizontal_accuracy_m` | **Unknown** until unit verified; do not assume meters |
| no altitude | — | `GnssSample.altitude_m` | `None` |
| no heading | — | `GnssSample.heading_deg` | `None` |
| `accl_x/y/z` | g | `ImuSample.accel_x/y/z_mps2` | **Conversion required** (`× 9.80665`) only after gravity semantics verified |
| `gyro_x/y/z` | deg/s | current alpha/beta/gamma fields | **Unsupported safely**; propose explicit x/y/z fields with stated unit |
| `heart_rate` | beats/min | no field | **Unsupported**; propose separate physiological stream/sample |
| `hdop`, `signal_quality`, `num_satellites` | GNSS quality | no fields | **Unsupported**; propose GNSS quality extensions or sidecar |
| `inst_acc_impulse` | vendor absolute acceleration, m/s² | no field | **Unsupported**; retain as vendor-derived sidecar, not truth |
| magnetometer | hardware exists, published column absent | no field | **Unknown/unsupported** |
| ordinary session ground truth | none documented | mandatory `GroundTruth` | **Model mismatch**; propose explicit `NoGroundTruth`/optional truth |
| 10 Hz/100 Hz nominal rates | stream metadata | `fs_gnss_hz`, `fs_acc_hz` | **Direct metadata** after measured cadence validation |
| STATSports APEX | device | `SessionMetadata.device` | **Direct** |
| no path curvature | — | `path_curvature` | `None` |

Do not add the proposed fields until real schemas and values have been inspected.
An initial loader should preserve all source columns in a raw/typed staging
representation before reducing them into `TrackingSession`.

## 4. Walking versus SoccerMon

Walking is a controlled short-path experiment with explicit test windows,
smartphone data, CSV streams, and continuous/final reference distance.
SoccerMon is naturalistic professional football, Parquet, longer player-session
records, mixed sensor cadences, anonymized identities, vendor-calculated
signals, richer GNSS quality, heart rate, and no documented ordinary-session
criterion distance. SoccerMon movement is intermittent and unconstrained; full
file duration can include non-playing activity. Raw coordinates can still
reveal venues even though player identities are anonymized.

## 5. Minimal representative Team B 2020 subset

Target **9 core Parquet reports**, with an upper bound of **12 reports or 2 GiB
uncompressed**, whichever is reached first. Keep the selected raw daily ZIPs
and Parquet files below `data/raw/soccermon/`; never rewrite them.

Selection is deterministic and does not use cleanliness, agreement with an
expected result, or future metric quality:

1. Inventory every daily archive name and size without extraction.
2. Select three non-empty dates at the 10th, 50th, and 90th percentiles of the
   sorted available dates (early/mid/late season).
3. From those dates, select three anonymized IDs present on all three dates. If
   fewer than three intersect, take all repeated IDs and fill remaining slots
   by a stable SHA-256 ordering of `(date, member path)`.
4. This yields 3 dates × 3 players = 9 core reports, separating temporal from
   between-player variation where possible.
5. If the core does not expose both ordinary and visibly dynamic IMU/GNSS
   behavior, add at most three reports from the same three dates: longest
   duration, largest 99.9th-percentile vendor speed, and largest
   99.9th-percentile acceleration magnitude. These are transparent stress
   cases added to—not substituted for—the unbiased core. They are not labels,
   thresholds, or ground truth.
6. If activity/match labels are actually present, replace no core sample;
   instead use the three optional slots to cover missing documented activity
   categories.

This subset is intended for schema/cadence/quality work and first football
characterization, not population inference.

## 6. Inspection utilities prepared

- `scripts/inspect_zip_archive.py`: central-directory inventory without
  extraction; reports counts, sizes, suffixes, depth, and top-level hierarchy.
- `scripts/extract_zip_members.py`: exact-member extraction only; rejects path
  traversal, missing selections, and overwrites.
- `scripts/inspect_parquet.py`: Parquet schema/metadata/row-group report, bounded
  missing/non-finite/range profile, and optional timestamp cadence estimate.
  It imports `pyarrow` lazily; `pyarrow` is not installed in the current
  environment.

## 7. Exact first procedure when the archive is complete

Assumed local path (verify before use):
`data/raw/soccermon/objective-TeamB-2020.zip`.

```bash
mkdir -p outputs/v0b1_soccermon_inventory
python3 scripts/inspect_zip_archive.py \
  data/raw/soccermon/objective-TeamB-2020.zip \
  --manifest-out outputs/v0b1_soccermon_inventory/outer_members.txt \
  > outputs/v0b1_soccermon_inventory/outer_summary.json
```

Review the JSON and manifest. Create
`outputs/v0b1_soccermon_inventory/selected_daily_members.txt` containing exactly
the three selected daily ZIP member names, then extract only those:

```bash
python3 scripts/extract_zip_members.py \
  data/raw/soccermon/objective-TeamB-2020.zip \
  data/raw/soccermon/subset/daily_archives \
  --manifest outputs/v0b1_soccermon_inventory/selected_daily_members.txt
```

For each extracted daily ZIP, run `inspect_zip_archive.py` first. Build an exact
Parquet-member manifest and use `extract_zip_members.py` again into
`data/raw/soccermon/subset/parquet/`. Do not use recursive/full extraction.

After adding `pyarrow` to an isolated project environment, inspect schemas
before naming any columns:

```bash
python3 scripts/inspect_parquet.py \
  data/raw/soccermon/subset/parquet/**/*.parquet \
  > outputs/v0b1_soccermon_inventory/parquet_metadata.json
```

After confirming that `time` really exists and its physical type:

```bash
python3 scripts/inspect_parquet.py \
  --profile --max-rows 250000 --time-column time \
  data/raw/soccermon/subset/parquet/**/*.parquet \
  > outputs/v0b1_soccermon_inventory/parquet_profiles.json
```

Record checksums and selection reasons in a small manifest; never edit the raw
files. Then implement a staging loader against observed schema/types and only
after that decide canonical model changes.

## 8. V0B implementation sequence

1. **V0B.1 — Inspect/select subset:** archive inventory, deterministic sample,
   raw checksums, schema/types/null/cadence report, and session boundaries.
2. **V0B.2 — Build loader:** first a lossless SoccerMon staging model and
   validation errors; no guessed columns or units.
3. **V0B.3 — Canonical mapping:** decide timestamp provenance, no-ground-truth,
   gyroscope, GNSS-quality, heart-rate, and context changes; add tests before
   mapping into `TrackingSession`.
4. **V0B.4 — Validate streams:** ordering, duplicates, gaps, measured sampling
   rates, coordinate ranges, missing/sentinel values, mixed-cadence behavior,
   player-ID stability, and cross-stream time alignment.
5. **V0B.5 — Characterize movement:** plot trajectories and distributions of
   raw/vendor speed and IMU axes; describe sessions and anomalies without
   inventing activity labels or thresholds.
6. **V0B.6 — First metrics:** raw/robust GNSS distance with full audit, duration,
   observed vendor speed summaries, and simple unit-verified IMU summaries.
   Vendor metrics remain comparisons, never truth.

Sprint detection, filtering/fusion, Kalman methods, ML, and high-intensity
threshold selection are explicitly deferred.

## 9. Risks and questions for real-data inspection

- Is the download complete and CRC-valid?
- What exact hierarchy and nested-ZIP layout does this particular archive use?
- Does one Parquet always equal exactly one player and one session? Can a player
  have multiple sessions on one date?
- Are player ID and filename identities stable and equivalent?
- What are every column's Parquet types and null/sentinel conventions?
- Are 10 Hz values null, repeated, or independently timestamped among 100 Hz
  rows?
- Is `time` a string, time logical type, timestamp, or number? What timezone and
  midnight rules apply?
- Is `hacc` measured in metres?
- Do accelerometer axes include gravity? What are device orientation and signs?
- Are gyroscope values truly deg/s in the files, and what is axis orientation?
- Are magnetometer samples absent as the published table suggests?
- What are the encodings/ranges for signal quality and satellite count?
- Are activity type, match/training status, playing position, or period markers
  present anywhere in the archive?
- Is the paper's two-lap validation session identifiable, and is any independent
  criterion representation actually distributed?
- Do coordinates include off-pitch/private-location periods requiring special
  handling in generated outputs?
