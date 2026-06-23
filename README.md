# FitLens

Local CLI for combining my Hevy export with Apple Health data.

It builds `fitlens.db`, then lets me look at:

- coach notes
- recent workouts
- weekly training load
- recovery trends
- import/database status

## Setup

```bash
cd FitLens
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python fitlens.py
```

## Exports

Apple Health:

- Health app
- profile photo
- Export All Health Data
- unzip it and use `export.xml`

Hevy:

- Settings
- Export Data
- use `workouts.csv`

If both files are in `~/Downloads`, FitLens will usually find them.

## How I use it

Run:

```bash
.venv/bin/python fitlens.py
```

First run imports the data. After that it opens the menu.

The app is guided only. I removed command-line flags/subcommands because I kept
forgetting what to type and the menu is easier.

## Recovery view

Recovery trends show:

- 7-day average
- 30-day average
- 60-day average
- 90-day average

It also compares each window to the previous same-length window. So 7-day is
compared to the prior 7 days, 30-day to the prior 30 days, etc.

The dates are based on the newest data in `fitlens.db`, not today's date. If the
latest Health export in the database ends on May 17, the recovery windows end on
May 17.

## Data

Main tables:

| table | notes |
|---|---|
| `workouts` | Hevy workouts |
| `workout_sets` | sets from Hevy |
| `workout_health_summary` | heart rate, effort, energy, etc. during workouts |
| `daily_health` | steps, resting HR, HRV, VO2 max, body mass, etc. |
| `daily_sleep` | sleep totals/stages |
| `apple_workouts` | Apple Watch workout records |
| `import_meta` | import paths, timezone, watermark |

Useful query:

```sql
SELECT w.title, w.start_local, s.avg, s.max
FROM workouts w
JOIN workout_health_summary s ON s.workout_id = w.workout_id
WHERE s.metric_type = 'HeartRate'
ORDER BY w.start_utc DESC
LIMIT 10;
```

## Files

- `fitlens.py` - CLI/menu
- `insights.py` - coach queries
- `engine.py` - import flow
- `parse_workouts.py` - Hevy CSV parser
- `health_stream.py` - Apple Health XML parser
- `db.py` - SQLite schema/writes
- `common.py` - small helpers

The parser/import code is stdlib. The CLI uses `rich` and `questionary`.
