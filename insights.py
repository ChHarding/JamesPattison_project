"""Queries for the coach screens."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

import db

SUM_DAILY_METRICS = {
    "ActiveEnergyBurned",
    "AppleExerciseTime",
    "AppleStandTime",
    "BasalEnergyBurned",
    "DistanceWalkingRunning",
    "FlightsClimbed",
    "StepCount",
}


def _local_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _date_range(end: date | None, days: int) -> tuple[str | None, str | None]:
    if end is None:
        return None, None
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _previous_range(window: tuple[str | None, str | None]) -> tuple[str | None, str | None]:
    if not window or not window[0] or not window[1]:
        return None, None
    start = date.fromisoformat(window[0])
    end = date.fromisoformat(window[1])
    days = (end - start).days + 1
    return _date_range(start - timedelta(days=1), days)


def _pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return (current - baseline) / baseline * 100.0


def _daily_value_expr(metric: str) -> str:
    if metric in SUM_DAILY_METRICS:
        return "COALESCE(sum, avg, last_value)"
    return "COALESCE(avg, last_value, sum)"


def _daily_metric_avg(conn, metric: str, start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    row = conn.execute(
        f"""
        SELECT AVG({_daily_value_expr(metric)}) value
        FROM daily_health
        WHERE metric_type = ? AND date BETWEEN ? AND ?
        """,
        (metric, start, end),
    ).fetchone()
    return row["value"] if row else None


def _sleep_avg(conn, field: str, start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    row = conn.execute(
        f"SELECT AVG({field}) value FROM daily_sleep WHERE date BETWEEN ? AND ?",
        (start, end),
    ).fetchone()
    return row["value"] if row else None


def _latest_data_date(conn) -> date | None:
    candidates = []
    for table, col in (
        ("daily_health", "date"),
        ("daily_sleep", "date"),
        ("workouts", "start_local"),
    ):
        row = conn.execute(f"SELECT MAX({col}) value FROM {table}").fetchone()
        d = _local_date(row["value"] if row else None)
        if d:
            candidates.append(d)
    return max(candidates) if candidates else None


def _workout_totals(conn, start: str | None, end: str | None) -> dict:
    if not start or not end:
        return {"count": 0, "duration_min": 0.0, "avg_effort": None}
    row = conn.execute(
        """
        SELECT
            COUNT(*) workouts,
            COALESCE(SUM(w.duration_sec), 0) / 60.0 duration_min,
            AVG(eff.avg) avg_effort
        FROM workouts w
        LEFT JOIN workout_health_summary eff
            ON eff.workout_id = w.workout_id
           AND eff.metric_type = 'PhysicalEffort'
        WHERE substr(w.start_local, 1, 10) BETWEEN ? AND ?
        """,
        (start, end),
    ).fetchone()
    return {
        "count": row["workouts"] or 0,
        "duration_min": row["duration_min"] or 0.0,
        "avg_effort": row["avg_effort"],
    }


def status(db_path: str) -> dict:
    """Counts and date coverage."""
    conn = db.connect(db_path)
    try:
        tables = {}
        for table in (
            "workouts",
            "workout_sets",
            "workout_health_summary",
            "daily_health",
            "daily_sleep",
            "apple_workouts",
        ):
            tables[table] = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]

        rng = conn.execute(
            "SELECT MIN(start_local) lo, MAX(start_local) hi FROM workouts"
        ).fetchone()
        daily_rng = conn.execute("SELECT MIN(date) lo, MAX(date) hi FROM daily_health").fetchone()
        sleep_rng = conn.execute("SELECT MIN(date) lo, MAX(date) hi FROM daily_sleep").fetchone()
        metrics = conn.execute(
            """
            SELECT metric_type, COUNT(*) c
            FROM daily_health
            GROUP BY metric_type
            ORDER BY c DESC, metric_type
            LIMIT 12
            """
        ).fetchall()
        meta_rows = conn.execute("SELECT key, value FROM import_meta").fetchall()
        return {
            "tables": tables,
            "training_range": (rng["lo"], rng["hi"]),
            "daily_range": (daily_rng["lo"], daily_rng["hi"]),
            "sleep_range": (sleep_rng["lo"], sleep_rng["hi"]),
            "metrics": [dict(r) for r in metrics],
            "meta": {r["key"]: r["value"] for r in meta_rows},
        }
    finally:
        conn.close()


def recent_workouts(db_path: str, limit: int = 10) -> list[dict]:
    """Recent workouts, plus the useful rollups."""
    conn = db.connect(db_path)
    try:
        rows = conn.execute(
            """
            WITH set_rollup AS (
                SELECT
                    workout_id,
                    COUNT(*) sets,
                    SUM(CASE
                        WHEN weight_lbs IS NOT NULL AND reps IS NOT NULL
                        THEN weight_lbs * reps
                        ELSE 0
                    END) volume_lbs
                FROM workout_sets
                GROUP BY workout_id
            ),
            metric_rollup AS (
                SELECT
                    workout_id,
                    MAX(CASE WHEN metric_type = 'HeartRate' THEN avg END) avg_hr,
                    MAX(CASE WHEN metric_type = 'HeartRate' THEN max END) max_hr,
                    MAX(CASE WHEN metric_type = 'PhysicalEffort' THEN avg END) effort,
                    MAX(CASE WHEN metric_type = 'ActiveEnergyBurned' THEN sum END) active_cal
                FROM workout_health_summary
                GROUP BY workout_id
            )
            SELECT
                w.workout_id,
                substr(w.start_local, 1, 10) day,
                substr(w.start_local, 12, 5) time,
                w.title,
                w.duration_sec / 60.0 duration_min,
                COALESCE(sr.sets, 0) sets,
                COALESCE(sr.volume_lbs, 0) volume_lbs,
                mr.avg_hr,
                mr.max_hr,
                mr.effort,
                mr.active_cal
            FROM workouts w
            LEFT JOIN set_rollup sr ON sr.workout_id = w.workout_id
            LEFT JOIN metric_rollup mr ON mr.workout_id = w.workout_id
            ORDER BY w.start_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def weekly_summary(db_path: str, weeks: int = 8) -> list[dict]:
    """Week buckets for training load."""
    conn = db.connect(db_path)
    try:
        rows = conn.execute(
            """
            WITH set_rollup AS (
                SELECT
                    workout_id,
                    COUNT(*) sets,
                    SUM(CASE
                        WHEN weight_lbs IS NOT NULL AND reps IS NOT NULL
                        THEN weight_lbs * reps
                        ELSE 0
                    END) volume_lbs
                FROM workout_sets
                GROUP BY workout_id
            ),
            metric_rollup AS (
                SELECT
                    workout_id,
                    MAX(CASE WHEN metric_type = 'HeartRate' THEN avg END) avg_hr,
                    MAX(CASE WHEN metric_type = 'PhysicalEffort' THEN avg END) effort
                FROM workout_health_summary
                GROUP BY workout_id
            )
            SELECT
                w.workout_id,
                substr(w.start_local, 1, 10) day,
                w.duration_sec / 60.0 duration_min,
                COALESCE(sr.sets, 0) sets,
                COALESCE(sr.volume_lbs, 0) volume_lbs,
                mr.avg_hr,
                mr.effort
            FROM workouts w
            LEFT JOIN set_rollup sr ON sr.workout_id = w.workout_id
            LEFT JOIN metric_rollup mr ON mr.workout_id = w.workout_id
            ORDER BY w.start_utc DESC
            """
        ).fetchall()

        buckets = defaultdict(lambda: {
            "week_start": None,
            "workouts": 0,
            "duration_min": 0.0,
            "sets": 0,
            "volume_lbs": 0.0,
            "hr_values": [],
            "effort_values": [],
        })
        for row in rows:
            d = date.fromisoformat(row["day"])
            week_start = d - timedelta(days=d.weekday())
            bucket = buckets[week_start]
            bucket["week_start"] = week_start.isoformat()
            bucket["workouts"] += 1
            bucket["duration_min"] += row["duration_min"] or 0.0
            bucket["sets"] += row["sets"] or 0
            bucket["volume_lbs"] += row["volume_lbs"] or 0.0
            if row["avg_hr"] is not None:
                bucket["hr_values"].append(row["avg_hr"])
            if row["effort"] is not None:
                bucket["effort_values"].append(row["effort"])

        summaries = []
        for week_start, bucket in sorted(buckets.items(), reverse=True)[:weeks]:
            hrs = bucket.pop("hr_values")
            efforts = bucket.pop("effort_values")
            bucket["avg_hr"] = sum(hrs) / len(hrs) if hrs else None
            bucket["avg_effort"] = sum(efforts) / len(efforts) if efforts else None
            summaries.append(bucket)
        return summaries
    finally:
        conn.close()


def recovery_summary(db_path: str) -> dict:
    """7/30/60/90 day recovery windows."""
    conn = db.connect(db_path)
    try:
        end = _latest_data_date(conn)
        windows = {
            days: _date_range(end, days)
            for days in (7, 30, 60, 90)
        }
        previous_windows = {
            days: _previous_range(window)
            for days, window in windows.items()
        }
        metrics = {}
        for metric in (
            "RestingHeartRate",
            "HeartRateVariabilitySDNN",
            "StepCount",
            "ActiveEnergyBurned",
            "AppleExerciseTime",
            "VO2Max",
        ):
            metrics[metric] = {}
            for days, (start, end_s) in windows.items():
                metrics[metric][f"avg_{days}"] = _daily_metric_avg(conn, metric, start, end_s)
                prev_start, prev_end = previous_windows[days]
                metrics[metric][f"prev_avg_{days}"] = _daily_metric_avg(
                    conn, metric, prev_start, prev_end)
                metrics[metric][f"change_{days}_pct"] = _pct_change(
                    metrics[metric][f"avg_{days}"],
                    metrics[metric][f"prev_avg_{days}"])
            metrics[metric]["change_pct"] = _pct_change(
                metrics[metric]["avg_7"], metrics[metric]["avg_30"])

        sleep = {}
        for days, (start, end_s) in windows.items():
            sleep[f"asleep_min_{days}"] = _sleep_avg(conn, "asleep_total_min", start, end_s)
            sleep[f"efficiency_{days}"] = _sleep_avg(conn, "efficiency_pct", start, end_s)
            prev_start, prev_end = previous_windows[days]
            sleep[f"prev_asleep_min_{days}"] = _sleep_avg(
                conn, "asleep_total_min", prev_start, prev_end)
            sleep[f"prev_efficiency_{days}"] = _sleep_avg(
                conn, "efficiency_pct", prev_start, prev_end)
            sleep[f"asleep_change_{days}_pct"] = _pct_change(
                sleep[f"asleep_min_{days}"], sleep[f"prev_asleep_min_{days}"])
            sleep[f"efficiency_change_{days}_pct"] = _pct_change(
                sleep[f"efficiency_{days}"], sleep[f"prev_efficiency_{days}"])
        sleep["asleep_change_pct"] = _pct_change(sleep["asleep_min_7"], sleep["asleep_min_30"])

        return {
            "latest_date": end.isoformat() if end else None,
            "windows": windows,
            "previous_windows": previous_windows,
            "window_7": windows[7],
            "window_30": windows[30],
            "window_60": windows[60],
            "window_90": windows[90],
            "sleep": sleep,
            "metrics": metrics,
        }
    finally:
        conn.close()


def coach_insights(db_path: str) -> dict:
    """Main coach snapshot."""
    conn = db.connect(db_path)
    try:
        end = _latest_data_date(conn)
        start_7, end_s = _date_range(end, 7)
        prev_end = (date.fromisoformat(start_7) - timedelta(days=1)).isoformat() if start_7 else None
        prev_start = (date.fromisoformat(prev_end) - timedelta(days=6)).isoformat() if prev_end else None
        current = _workout_totals(conn, start_7, end_s)
        previous = _workout_totals(conn, prev_start, prev_end)
    finally:
        conn.close()

    recovery = recovery_summary(db_path)
    recent = recent_workouts(db_path, limit=1)
    weeks = weekly_summary(db_path, weeks=4)

    sleep = recovery["sleep"]
    hrv = recovery["metrics"]["HeartRateVariabilitySDNN"]
    rhr = recovery["metrics"]["RestingHeartRate"]
    notes = []

    if current["count"] == 0:
        notes.append("No workouts are logged in the latest 7-day window.")
    elif previous["count"] == 0:
        notes.append(f"Latest 7 days include {current['count']} workouts and {current['duration_min']:.0f} training minutes.")
    else:
        delta = current["duration_min"] - previous["duration_min"]
        direction = "up" if delta >= 0 else "down"
        notes.append(
            f"Training time is {direction} {abs(delta):.0f} minutes versus the prior 7 days."
        )

    if sleep["asleep_min_7"] is not None:
        sleep_hours = sleep["asleep_min_7"] / 60.0
        if sleep_hours < 6.5:
            notes.append(f"Average sleep is {sleep_hours:.1f} hours over the latest 7 days; recovery may be constrained.")
        elif sleep_hours >= 7.5:
            notes.append(f"Average sleep is {sleep_hours:.1f} hours over the latest 7 days, which supports harder training.")

    if hrv["avg_7"] is not None and hrv["avg_30"] is not None and hrv["avg_7"] < hrv["avg_30"] * 0.9:
        notes.append("HRV is more than 10% below the 30-day average, so keep an eye on fatigue.")

    if rhr["avg_7"] is not None and rhr["avg_30"] is not None and rhr["avg_7"] > rhr["avg_30"] * 1.05:
        notes.append("Resting heart rate is elevated versus the 30-day average; consider keeping the next session moderate.")

    if not notes:
        notes.append("Training and recovery look steady from the data currently available.")

    return {
        "latest_date": recovery["latest_date"],
        "current_7": current,
        "previous_7": previous,
        "recovery": recovery,
        "recent_workout": recent[0] if recent else None,
        "weekly": weeks,
        "notes": notes,
    }
