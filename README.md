# football-stat-tracker
Personal football player tracking project using smartphone sensors and GPS

## Current status

V0A and V0B.1 are committed; V0B.2 adds a SoccerMon recording importer.

## Import one SoccerMon recording

From the repository root, using the existing selected subset (raw data is not
included in Git):

```bash
python3 -m venv .venv  # only if no project environment exists
.venv/bin/python -m pip install -r requirements-v0b1.txt
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
from football_stat_tracker.importers import (
    import_soccermon_session, summarize_soccermon_session,
)

path = Path("data/raw/soccermon/subset/2020/2020-08/2020-08-27/") / (
    "2020-08-27-TeamB-afc13e53-2c77-48cb-8a78-743663bbb84f.parquet"
)
session = import_soccermon_session(path)
print(summarize_soccermon_session(session))
assert session.ground_truth is None
# Native device axes: documented g and deg/s; gravity/orientation unresolved.
accel_x_g = session.imu[0].raw_source.get("accl_x")
gyro_x_deg_s = session.imu[0].raw_source.get("gyro_x")
PY
```

IMU rows retain repeated original timestamps and source ordering. GNSS entries
are timestamp-group candidates with unknown fix freshness. Invalid coordinates
remain in `raw_source`, with an explicit `position_status`; their canonical
coordinates are `None`. Quality codes retain their source encoding.
See [the V0B.2 report](docs/v0b2_soccermon_importer_report.md) for mapping and limits.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
# Requires the existing V0B.1 nine-file extracted manifest; reads every source row.
PYTHONPATH=src .venv/bin/python scripts/validate_soccermon_imports.py
```
