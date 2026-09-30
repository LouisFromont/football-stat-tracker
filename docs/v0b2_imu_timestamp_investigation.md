# V0B.2.1 — SoccerMon IMU timestamp investigation

Investigation completed 2026-09-30 using the existing nine-file TeamB 2020
subset. This is a temporal-evidence audit, not timestamp reconstruction.

## Executive summary

**OBSERVED:** 4,987,174 rows form 498,725 distinct, contiguous timestamp groups.
99.996992% of groups contain ten rows. Every group contains varying
accelerometer vectors and varying gyroscope vectors. Stored times have only
one fractional digit and usually advance by 100 ms. Thus the repeated clock
labels do not represent ten copies of one sensor vector.

**INFERRED:** the strongest explanation is that the export retains a sequence
of differing IMU records while exposing a coarser clock shared by ten rows.
This identifies the loss of temporal detail, not its mechanism. Per-sample
rounding/truncation, packet timestamps, and precision reduction during export
remain observationally compatible. They may occur together.

**OBSERVED:** the difference between rows five and six of full ten-row groups
has a median norm 1.18–1.33 times the reference for the other within-group
positions, consistently across both sensors and all nine sessions. This
previously unreported pattern weakens an assumption of uniform spacing.
It does not establish a longer physical interval or a five-sample packet.

**Recommendation:** retain the importer policy. Exact sample timing is not
recoverable from these files. A nominal 10 ms timeline could support explicitly
conditional exploratory sensitivity analysis, but is not sufficiently verified
for production motion timing, integration or GNSS synchronization. Obtain export
clock semantics and investigate the middle-pair pattern before implementing it.

Evidence labels throughout: **DOCUMENTED** means explicitly stated in a primary
source; **OBSERVED** means computed from local files/repository; **INFERRED**
means an interpretation; **UNKNOWN** means not established by available evidence.

## Baseline and scope

The working tree was clean. V0A/V0B.1 were committed in `9969661`; V0B.2 was
committed in `5d3b3db`, `e382b04`, and `4c35c43`. Read the V0B.1 and V0B.2 reports,
canonical model, SoccerMon importer, validation scripts and relevant tests.
The baseline suite passed 72 tests with no skips.

No source under `src/`, existing tests, importer, canonical timestamps, Walking
behavior or GNSS filtering algorithm was changed. No extra dataset was
downloaded. Sessions S1–S9 follow the existing extraction manifest and prior
reports. The abbreviated identifiers below identify files, not real players.

| Session | Recording date | Anonymized filename identifier prefix |
|---|---|---|
| S1 | 2020-06-17 | afc13e53 |
| S2 | 2020-06-17 | 48bfd4ea |
| S3 | 2020-08-27 | afc13e53 |
| S4 | 2020-08-27 | 48bfd4ea |
| S5 | 2020-11-19 | afc13e53 |
| S6 | 2020-11-19 | 48bfd4ea |
| S7 | 2020-11-19 | 70b74270 |
| S8 | 2020-06-17 | 789547e7 |
| S9 | 2020-06-17 | 247a8333 |

Files remain under `data/raw/soccermon/subset/2020/`, selected by
`outputs/v0b1_soccermon_inventory/extracted_manifest.json`. Each source SHA-256
matches that manifest before and after inspection.

## Official documentation and code findings

Primary sources were accessed on 2026-09-30. Nominal rates are documentation,
not independent measurements of exact timing.

| Primary source and exact URL | Explicit information | Timing implications and limits |
|---|---|---|
| [SoccerMon data descriptor, objective acquisition](https://www.nature.com/articles/s41597-024-03386-x?error=cookies_not_supported) | **DOCUMENTED:** STATSports APEX; 10 Hz multi-GNSS; accelerometer and gyroscope specified at 952 Hz; downloads through Sonra 2.1.4. Original CSV exports were anonymized, column names cleaned and converted to Parquet for compression; authors state no other alterations. | **UNKNOWN:** actual per-recording hardware clock, firmware version, timestamp assignment, buffering, IMU resampling and GNSS/IMU clock alignment. No mechanism for repeated IMU timestamps is described in the acquisition section. |
| [Official Table 3](https://www.nature.com/articles/s41597-024-03386-x/tables/3?error=cookies_not_supported) | **DOCUMENTED:** exported IMU axes nominally 100 Hz, GNSS/auxiliary fields 10 Hz; timestamp format `HH:mm:ss.SSS`, described with millisecond granularity; acceleration g and angular rate deg/s. | **OBSERVED:** local strings instead have one fractional digit. **UNKNOWN:** why; listed precision does not guarantee each exported row has its own clock reading. Export rate is distinct from the hardware specification. |
| [Manufacturer Sonra Desktop Updates](https://statsports.com/article/sonra-desktop-updates) | **DOCUMENTED:** raw API export supports 10 Hz GNSS and 100 Hz accelerometer/gyroscope data. | Corroborates nominal exported rates. Does not specify per-sample versus per-packet clocks, phase, buffers or conversion behavior. This page is not a specification for the particular 2020 files. |
| [Manufacturer Share Data documentation](https://elitesupport.statsports.com/hc/en-us/articles/13494019543965-Share-Data) | **DOCUMENTED:** raw data can be shared for sessions and through the API. | Does not recover clock semantics. Current support documentation is not evidence of the exact historical exporter implementation. |
| [Official Zenodo deposition](https://zenodo.org/records/10033832) | **OBSERVED:** advertised file list comprises four objective team/year ZIPs and `subjective.zip`. | No separate original-CSV comparison set, acquisition code, firmware or timing supplement is advertised in that file list. Archive contents beyond the existing subset were not fetched. |
| [Authors' repository](https://github.com/simula/soccermon) | **OBSERVED:** README describes subjective PMSys loading. Inspected modules below operate on subjective reports. | No objective acquisition or timestamp conversion implementation was found in those inspected modules. This is not proof that no such implementation exists elsewhere. |

Inspected public code URLs:

- [preprocessing/read_in_data.py](https://raw.githubusercontent.com/simula/soccermon/main/preprocessing/read_in_data.py): subjective report/date processing.
- [preprocessing/data_loader.py](https://raw.githubusercontent.com/simula/soccermon/main/preprocessing/data_loader.py): player/team and subjective report structures.
- [preprocessing/run_team_pickle_generation.py](https://raw.githubusercontent.com/simula/soccermon/main/preprocessing/run_team_pickle_generation.py): subjective pickle generation.

Repository tree/API retrieval was incomplete. The official
[dataset landing page](https://datasets.simula.no/soccermon/) and
[SoccerSum site](https://code.simula.no/soccersum/) failed to open in the research
tool. No dedicated timing supplement was found among the inspected publication
links. These access/search limits preclude an exhaustive absence claim.
No inspected source establishes whether timestamps refer to first/last samples,
packet creation/arrival, or export processing. Nor does it establish a usable
sample counter, alternative clock or IMU–GNSS synchronization protocol.

**INFERRED:** hardware-to-export rate reduction is plausible, but the 952 Hz
specification and 100 Hz export documentation do not identify a decimation,
resampling or filtering algorithm. Vendor terminology such as raw export does
not establish untouched hardware samples.

## Reproducible methodology

Run from the repository root using the existing analysis dependencies:

```bash
PYTHONPATH=src .venv/bin/python scripts/investigate_soccermon_imu_timestamps.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

The script accepts `--manifest`, `--output` and `--no-plots`. It reads only
`time`, `accl_x/y/z` and `gyro_x/y/z`. It parses the original strings exactly
using the existing parser, keeps file order, and never sorts, interpolates,
repairs gaps or generates per-sample times. The 100 ms/ten-row references are
inspection constants, not asserted physical cadence.

Separate global timestamp multiplicity from contiguous groups so a reversed
or recurring timestamp cannot silently merge different source runs. Count
source-row and group-clock differences, edge sizes, non-ten interiors,
reversals and missing grid bins. A grid-bin absence is a clock-label absence,
not proof of missing physical samples. Time-of-day reversals, including possible
midnight crossings in other files, are reported without rollover repair.

Analyze accelerometer and gyroscope independently. An identical vector means
exact numeric equality of all three finite components; an identical group
means every vector equals its first. It does not mean duplicated acquisition.
Singleton groups and non-finite groups have explicit separate counts. Six-axis
identity is also counted, but no norm combines incompatible sensor units.

For consecutive rows compute signed axis differences and Euclidean vector
difference norms, without dividing by an assumed interval. Report finite counts,
quantiles and fixed-bin histograms for within-group, all-boundary, normal
100 ms boundary, gap boundary and reversal pairs. Examine nine adjacent pair
positions separately in full ten-row groups and boundaries between two full
groups. The middle-pair ratio is the position-five median divided by the median
of the eight other position medians; it is not a timing estimate or pooled
median. Quantiles use NumPy's default linear method; rows/pairs are correlated,
so no independent-sample significance claim is made.

Outputs are aggregate-only: no coordinates, source time-of-day traces, player
vectors or reconstructed times. SHA-256, schema names/types and metadata-key
names support provenance without copying arbitrary metadata values. All outputs
and plotting caches remain ignored by Git.

## Per-session clock results

**OBSERVED:** every time string has one fractional digit. All six IMU columns
are double precision, without nulls or non-finite values in this subset. All
stored times are on the 100 ms grid. There are no reversals or noncontiguous
timestamp recurrences. Parquet stores `time` as a string, not a timestamp type:
no finer Arrow/Parquet timestamp precision is hidden in that column.
Metadata keys contain only pandas metadata; producer is fastparquet 0.8.1
(pandas metadata identifies 1.4.2). The 17-field schema has no sample counter,
packet identifier, alternative clock or synchronization marker.

| Session | Rows | Distinct groups | Group-size distribution (size: count) | Exactly ten (%) | First / last size | Repeated adjacent timestamps | Stored span (s) |
|---|---:|---:|---|---:|---|---:|---:|
| S1 | 644,460 | 64,447 | 5: 2; 10: 64,445 | 99.996897 | 5 / 5 | 580,013 | 6,445.3 |
| S2 | 580,445 | 58,045 | 5: 1; 10: 58,044 | 99.998277 | 5 / 10 | 522,400 | 5,805.0 |
| S3 | 51,130 | 5,114 | 5: 2; 10: 5,112 | 99.960892 | 5 / 5 | 46,016 | 512.3 |
| S4 | 437,530 | 43,754 | 5: 2; 10: 43,752 | 99.995429 | 5 / 5 | 393,776 | 4,376.3 |
| S5 | 714,225 | 71,423 | 5: 1; 10: 71,422 | 99.998600 | 5 / 10 | 642,802 | 7,143.2 |
| S6 | 696,320 | 69,633 | 5: 2; 10: 69,631 | 99.997128 | 5 / 5 | 626,687 | 6,964.4 |
| S7 | 673,009 | 67,302 | 4: 1; 5: 1; 10: 67,300 | 99.997028 | 4 / 5 | 605,707 | 6,731.0 |
| S8 | 582,780 | 58,279 | 5: 2; 10: 58,277 | 99.996568 | 5 / 5 | 524,501 | 5,828.4 |
| S9 | 607,275 | 60,728 | 5: 1; 10: 60,727 | 99.998353 | 5 / 10 | 546,547 | 6,073.5 |

All fifteen non-ten groups are at recording edges; no irregular interior group
size occurs. All first groups are shorter than ten; six last groups are shorter
than ten. **UNKNOWN:** whether edge groups represent clipping of longer groups,
start/stop acquisition or another export boundary rule.

| Session | Distinct-group intervals (ms: count) | Gaps >100 ms | Absent 100 ms grid bins | Observed export density (rows/s) | Stored span minus hypothetical uniform 100 rows/s span (ms) |
|---|---|---:|---:|---:|---:|
| S1 | 100: 64,444; 200: 1; 700: 1 | 2 | 7 | 99.988984 | 710 |
| S2 | 100: 58,041; 200: 2; 500: 1 | 3 | 6 | 99.990353 | 560 |
| S3 | 100: 5,109; 200: 2; 300: 1; 700: 1 | 4 | 10 | 99.802850 | 1,010 |
| S4 | 100: 43,751; 200: 1; 1,000: 1 | 2 | 10 | 99.976921 | 1,010 |
| S5 | 100: 71,419; 200: 1; 300: 1; 800: 1 | 3 | 10 | 99.986561 | 960 |
| S6 | 100: 69,630; 200: 1; 1,200: 1 | 2 | 12 | 99.982626 | 1,210 |
| S7 | 100: 67,298; 200: 2; 800: 1 | 3 | 9 | 99.986332 | 920 |
| S8 | 100: 58,276; 200: 1; 600: 1 | 2 | 6 | 99.989534 | 610 |
| S9 | 100: 60,725; 200: 1; 800: 1 | 2 | 8 | 99.987487 | 760 |

There are 23 gaps and 78 absent grid bins in total. Distinct-clock interval
minimum, median and p95 are 100 ms in every session. Source-row intervals consist
of zeros (repeat counts above) plus the positive intervals in this table. Density
is `(N−1)/stored_span`, not physical sampling frequency. The last column is only
a scalar counterfactual `stored_span_ms − (N−1)×10`; it creates no timeline.
Gaps and partial edges explain why a global uniform row-index clock would
compress the stored span by 0.56–1.21 s. This is not measured oscillator drift.

## Per-session sensor results

**OBSERVED:** in every session, identical multirow groups are **0%**, varying
groups **100%**, independently for accelerometer and gyroscope (also jointly).
All groups are finite, multirow and classifiable. Consecutive identical vectors
are rare but not absent; they can arise through quantization or inactivity.

| Session | Identical adjacent accel vectors, count (%) | Identical adjacent gyro vectors, count (%) | Identical adjacent six-axis vectors | Longest identical run, accel / gyro (rows) |
|---|---|---|---:|---|
| S1 | 241 (0.037396) | 155 (0.024051) | 1 | 3 / 3 |
| S2 | 576 (0.099234) | 225 (0.038763) | 9 | 3 / 3 |
| S3 | 33 (0.064543) | 20 (0.039117) | 0 | 2 / 2 |
| S4 | 168 (0.038397) | 104 (0.023770) | 2 | 3 / 3 |
| S5 | 174 (0.024362) | 201 (0.028142) | 1 | 2 / 3 |
| S6 | 84 (0.012063) | 97 (0.013930) | 2 | 2 / 3 |
| S7 | 347 (0.051560) | 597 (0.088706) | 11 | 3 / 5 |
| S8 | 1,813 (0.311096) | 1,399 (0.240057) | 36 | 4 / 5 |
| S9 | 673 (0.110823) | 569 (0.093697) | 16 | 4 / 3 |

Denominators are `N−1` pairs per session. Across recordings, 4,109 accel pairs,
3,367 gyro pairs and 78 six-axis pairs are identical among 4,987,165 eligible
pairs. No pairs cross recording boundaries. These are equality observations,
not counts of erroneous duplicate measurements.

The following cells give **median / p95** norms of consecutive vector
differences, in native documented units. Boundary means the last source row of
one group and first of the next, restricted here to a 100 ms clock-label change.
Numbers are rounded to six decimals; they are not accelerations derived from
velocity or angular accelerations derived from a known interval.

| Session | Accel within (g) | Accel boundary (g) | Gyro within (documented deg/s) | Gyro boundary (documented deg/s) |
|---|---|---|---|---|
| S1 | 0.034923 / 0.477965 | 0.033930 / 0.455591 | 0.013562 / 0.136072 | 0.013168 / 0.130685 |
| S2 | 0.022476 / 0.333834 | 0.021994 / 0.320908 | 0.010703 / 0.137053 | 0.010501 / 0.134015 |
| S3 | 0.017253 / 0.140515 | 0.016466 / 0.129191 | 0.007790 / 0.043598 | 0.007441 / 0.040939 |
| S4 | 0.027859 / 0.262961 | 0.027161 / 0.254677 | 0.011070 / 0.075456 | 0.010844 / 0.072614 |
| S5 | 0.067505 / 0.617833 | 0.065614 / 0.591482 | 0.022437 / 0.168921 | 0.021872 / 0.160709 |
| S6 | 0.043653 / 0.345019 | 0.042405 / 0.334435 | 0.014812 / 0.101000 | 0.014542 / 0.097272 |
| S7 | 0.075442 / 0.824639 | 0.074335 / 0.813402 | 0.025582 / 0.268323 | 0.024984 / 0.257921 |
| S8 | 0.016811 / 0.337761 | 0.016449 / 0.325857 | 0.007017 / 0.106187 | 0.006910 / 0.102887 |
| S9 | 0.024076 / 0.510391 | 0.023621 / 0.491276 | 0.009707 / 0.158432 | 0.009531 / 0.154497 |

Normal-boundary/within median ratios range 0.954–0.985 across both sensors.
**INFERRED:** file ordering is compatible with a largely continuous signal;
there is no large median jump at normal group boundaries. This does not certify
chronological ordering or compare physical intervals: both are unknown.
All-boundary and separate gap-boundary statistics, signed axis differences,
per-axis equality and full quantiles are retained in the JSON.

| Session | Position-five median / reference for other within positions: accel | Gyro |
|---|---:|---:|
| S1 | 1.3072 | 1.3087 |
| S2 | 1.2336 | 1.2346 |
| S3 | 1.2901 | 1.3135 |
| S4 | 1.2333 | 1.2378 |
| S5 | 1.3316 | 1.3231 |
| S6 | 1.2310 | 1.2353 |
| S7 | 1.1811 | 1.1800 |
| S8 | 1.2447 | 1.2534 |
| S9 | 1.1753 | 1.1826 |

**INFERRED:** the consistent phase pattern suggests some acquisition/export
structure beyond a featureless uniform sequence. **UNKNOWN:** whether it is
unequal timing, a sensor/processing artifact, within-block ordering, or another
mechanism. Dividing these ratios into assumed time steps would be unjustified.

## Hypothesis comparison

H1 and H3 overlap: rounding could happen during acquisition or export. None of
the positive findings identifies the stage at which the coarse clock arose.

| Hypothesis | Supporting evidence | Contradicting evidence / limits | Remaining unknowns and discriminating evidence |
|---|---|---|---|
| H1: per-sample times rounded/truncated | **OBSERVED:** tenths-only strings; ten differing vectors per 100 ms group. **INFERRED:** compatible with clock quantization of a faster stream. | Not contradicted, but no fine times exist for direct comparison. Middle-pair pattern is not explained by simple clock formatting alone. | **UNKNOWN:** floor versus nearest rounding, original resolution and lost fraction. Obtain pre-formatting sample times or exact formatter specification. |
| H2: common packet timestamp | **OBSERVED:** near-exact ten-row groups and short edges. **INFERRED:** compatible with batching; middle-pair effect could suggest internal structure. | Not contradicted, but neither packet IDs nor packet boundaries are recorded. Ten-row groups could equally be clock bins. | **UNKNOWN:** buffering, packet size/order, first/last/arrival stamp. Obtain packet layout, device logs, counters and firmware specification. |
| H3: export/conversion reduced precision | **DOCUMENTED:** Sonra-to-CSV-to-Parquet workflow. **OBSERVED:** strings are coarser than Table 3's format. | Authors state no other data alteration; this weighs against an intentional dataset-curation timing change, but does not validate formatting behavior. Parquet string storage itself cannot supply missing decimal digits. | **UNKNOWN:** original CSV contents and conversion code. Compare the same recording's CSV and Parquet, including source text bytes and column types; inspect Sonra 2.1.4 formatting and converter. |
| H4: measurements duplicated in processing | **OBSERVED:** some identical adjacent vectors. | **OBSERVED:** zero constant groups in either sensor; only 78 identical adjacent six-axis pairs among nearly five million pairs. Strongly contradicts tenfold copying of one vector as the cause of repeated clocks. | **UNKNOWN:** selective duplication or generated/interpolated samples cannot be excluded by inequality. Counters and paired pre-export data would distinguish copies from naturally equal quantized values. |
| H5: rate reduction, mixed-cadence join or hidden subblocks | **DOCUMENTED:** different hardware/export rates. **OBSERVED:** middle-pair effect; prior V0B.2 audit found held GNSS/auxiliary fields within groups. **INFERRED:** downsampling, block assembly or a low-rate clock attached to faster IMU rows is plausible. | No public algorithm was recovered. A five-sample mechanism is speculative; the ordinary ten-row boundary does not show a matching elevated median. | **UNKNOWN:** sample generation, resampling/filtering, clock joins and block order. Obtain export implementation and an instrumented acquisition with independent timestamps. |

The evidence resolves H4's simple ten-copy explanation and establishes a coarse
export clock. It does not select H1, H2, H3 or a particular H5 implementation.

## What temporal information is recoverable?

**Recoverable:** original timestamp text and exact parsed local milliseconds,
source ordering, group membership, clock gaps, and actual recorded vectors.
The importer already preserves these independently of any estimated timeline.

**Supported but conditional:** approximately 100 exported rows per stored
second agrees with nominal 100 Hz documentation. Within-group order is retained
and signal continuity is plausible. An actual 100 Hz oscillator, reliable
chronological order within every group, and exact 10 ms spacing remain
**UNKNOWN**, particularly given the middle-pair pattern. Absolute timezone and
alignment to GNSS acquisition times also remain unknown.

Clock phase cannot be guessed. Conditional examples for ten perfectly uniform
10 ms-spaced samples: a first-sample stamp implies offsets 0…90 ms; a last-sample
stamp implies −90…0 ms. Nearest rounding would instead suggest a ±50 ms bin;
truncation would suggest a following 100 ms bin. Those bounds require the
corresponding mechanism and do not hold for an unbounded packet-arrival delay.
They are examples, not confidence intervals for SoccerMon.

Gaps cannot distinguish omitted records from acquisition pauses or clock jumps.
Do not bridge them with a row-index clock or manufacture missing samples. Do
not spread five-row edge groups across 100 ms, infer their missing slot positions,
or silently stretch intervals to match a group boundary. Unknown clock drift,
resampling and latency prevent recovering accumulated timing error; the scalar
span mismatch above cannot separate them.

Relative spacing might be estimated under a nominal-cadence assumption without
knowing absolute phase, but these files do not independently measure it. The
middle-pair effect is a specific reason to investigate nonuniform spacing before
using such estimates for integration, spectral interpretation or event timing.

If a separate exploratory timeline is later justified, it should be optional
and versioned, with original timestamp/row references, method, assumed spacing,
anchor hypothesis, gap/edge flags and explicit unknown timing bounds. Compare
anchor and spacing alternatives as sensitivity analysis. Never overwrite raw
time, set measured canonical frequency from this assumption, or treat the result
as synchronized truth. No such timeline is implemented by this investigation.

## Artifacts, tests and next action

Reusable code: `scripts/investigate_soccermon_imu_timestamps.py`.
Tests: `tests/test_imu_timestamp_investigation.py` (nine tests): sensor-specific
identity, global versus contiguous multiplicity, unsigned-clock reversals,
within/boundary/gap differences, partial edges and irregular interiors,
non-finite/null eligibility, singletons, scalar span comparison, middle-pair
patterns, and synthetic Parquet read-only/checksum behavior.

Validation: final full suite **81 tests passed, zero skips**. All nine real
recordings were inspected in full with unchanged hashes. No reconstructed
timestamps, derivatives, movement thresholds or GNSS filters were introduced.

Local ignored outputs:

- [Aggregate statistics](../outputs/v0b2_imu_timestamp_investigation/aggregate_statistics.json).
- [Clock structure](../outputs/v0b2_imu_timestamp_investigation/clock_structure.png).
- [Within/boundary difference distributions](../outputs/v0b2_imu_timestamp_investigation/imu_vector_differences.png).
- [Pair-position diagnostic](../outputs/v0b2_imu_timestamp_investigation/pair_position_differences.png).

Plots were visually inspected. These files are reproducible local artifacts
and are intentionally excluded from commits. The report preserves aggregate
results for readers without the local data/manifest. Re-running requires the
previously acquired subset and manifest; the script does not download them.

Limitations: nine recordings from one team/year do not establish dataset-wide
behavior. Encoded equality does not identify acquisition duplication; smoothness
does not prove sample order; amplitude differences do not measure elapsed time.
No independent hardware clock, original CSV, conversion implementation or
controlled synchronization experiment was available. Native units, calibration,
gravity treatment and sensor-axis conventions remain as qualified in V0B.2.

Recommended next engineering action: obtain, with author/manufacturer help,
a paired original CSV/Parquet recording and Sonra 2.1.4/device firmware export
specification covering timestamp phase, precision, buffers, sample counters,
sample ordering, rate reduction and GNSS synchronization. Specifically ask about
the rows-five-to-six pattern. Then validate any separate estimated timeline
against that evidence before football-specific motion analysis. Until then,
V0B.3 can safely use native vectors, source order and coarse clock/group quality
diagnostics, while keeping fine-time-dependent conclusions conditional.
