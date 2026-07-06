# Demo data

Fake Apple Health and Hevy exports for trying FitLens without using real data.

Files:

- `export.xml` - mock Apple Health export
- `workouts.csv` - mock Hevy export

Run FitLens from the repo root:

```bash
.venv/bin/python fitlens.py
```

When prompted:

- Apple Health export: `demo_data/export.xml`
- Hevy workout history: `demo_data/workouts.csv`
- Timezone: `America/New_York`

The data is synthetic. It covers 120 days ending on `2026-05-31`, with fake
workouts, sleep, daily health metrics, and Apple Watch-style workout records.
