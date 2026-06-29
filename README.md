# FitLens

Local CLI for combining my Hevy export with Apple Health data.

It builds `fitlens.db`, then lets me look at:

- coach notes
- coach recommendations for the next month
- recent workouts
- weekly training load
- recovery trends
- import/database status

## Setup

```bash
cd FitLens
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python fitlens.py
```

I use Python 3.12 for the virtual environment. Python 3.14 made the prompt UI
imports hang on my machine.

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

## Coach recommendations

Recommendations compare the latest 30 days to the prior 30 days. That matches
how I use the app when I upload a fresh export every month.

The advice is local and rule-based. It looks at training load, strength sets,
movement balance, Zone 2 cardio, harder interval-style cardio, sleep, HRV, and
resting heart rate. Then it gives ranked actions plus a simple four-week plan.

## Movement balance

The "Movement balance" menu item breaks the latest 30 days of lifting into
fractional muscle volume. Each set gives 1.0 to the main muscle and 0.5 to each
assisting muscle, so an incline press shows up as upper chest plus some front
delt and triceps. Leaves roll up into groups (upper/mid/lower chest -> chest)
and patterns (push/pull). Balance ratios compare same-role muscles - chest vs
back, quads vs hams, biceps vs triceps - not push vs pull, since push always
carries more total volume (chest, all delt heads, triceps) than pull.

Classification lives in `taxonomy.py`: an exact-name map for the tricky ones and
an ordered regex fallback for everything else. The same screen lists any
exercises it couldn't place - drop those names into `taxonomy.EXERCISE_MAP` after
a new export adds machines I haven't done before.

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
- `taxonomy.py` - exercise -> muscle classification
- `engine.py` - import flow
- `parse_workouts.py` - Hevy CSV parser
- `health_stream.py` - Apple Health XML parser
- `db.py` - SQLite schema/writes
- `common.py` - small helpers

The parser/import code is stdlib. The CLI uses `rich` and `questionary`.
