"""Queries for the coach screens."""


from collections import defaultdict
from datetime import date, datetime, timedelta

import db
import taxonomy

SUM_DAILY_METRICS = {
    "ActiveEnergyBurned",
    "AppleExerciseTime",
    "AppleStandTime",
    "BasalEnergyBurned",
    "DistanceWalkingRunning",
    "FlightsClimbed",
    "StepCount",
}

ZONE2_TITLE_KEYWORDS = ("zone 2", "zone2", "easy", "base", "aerobic")
HARD_CARDIO_TITLE_KEYWORDS = (
    "hiit", "interval", "intervals", "4x4", "sprint", "threshold",
    "tempo", "vo2", "zone 4", "zone4", "zone 5", "zone5",
)
CARDIO_TITLE_KEYWORDS = (
    "cardio", "run", "treadmill", "bike", "cycle", "cycling", "rower",
    "elliptical", "walk", "stair", "hiit", "interval", "zone",
)

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


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


def _safe_ratio(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return value / baseline


def _avg(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


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
        return {
            "count": 0,
            "duration_min": 0.0,
            "sets": 0,
            "volume_lbs": 0.0,
            "avg_effort": None,
        }
    row = conn.execute(
        """
        WITH set_totals AS (
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
        )
        SELECT
            COUNT(*) workouts,
            COALESCE(SUM(w.duration_sec), 0) / 60.0 duration_min,
            COALESCE(SUM(st.sets), 0) sets,
            COALESCE(SUM(st.volume_lbs), 0) volume_lbs,
            AVG(eff.avg) avg_effort
        FROM workouts w
        LEFT JOIN set_totals st ON st.workout_id = w.workout_id
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
        "sets": row["sets"] or 0,
        "volume_lbs": row["volume_lbs"] or 0.0,
        "avg_effort": row["avg_effort"],
    }


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _cardio_zone(title: str | None, avg_hr: float | None, max_hr: float | None,
                 effort: float | None, duration_min: float | None) -> str | None:
    text = (title or "").lower()
    if _contains_any(text, ZONE2_TITLE_KEYWORDS):
        return "zone2"
    if _contains_any(text, HARD_CARDIO_TITLE_KEYWORDS):
        return "hard"
    if not _contains_any(text, CARDIO_TITLE_KEYWORDS):
        return None

    if effort is not None:
        if effort >= 6.5:
            return "hard"
        if 2.0 <= effort <= 5.5 and (duration_min or 0) >= 20:
            return "zone2"
    if avg_hr is not None and max_hr is not None:
        if max_hr >= 170 or (max_hr - avg_hr >= 28 and avg_hr >= 130):
            return "hard"
        if 110 <= avg_hr <= 150 and (duration_min or 0) >= 20:
            return "zone2"
    elif avg_hr is not None and 110 <= avg_hr <= 145 and (duration_min or 0) >= 20:
        return "zone2"
    return "unknown"


def _month_stats(conn, start: str | None, end: str | None) -> dict:
    stats = {
        "window": (start, end),
        "workouts": 0,
        "duration_min": 0.0,
        "strength_sets": 0,
        "volume_lbs": 0.0,
        "avg_effort": None,
        "avg_rpe": None,
        "muscle_volume": {leaf: 0.0 for leaf in taxonomy.LEAVES},
        "iso_volume": {leaf: 0.0 for leaf in taxonomy.LEAVES},
        "group_volume": {},
        "pattern_volume": {},
        "unmapped": {},
        "unknown_sets": 0,
        "cardio_min": 0.0,
        "zone2_min": 0.0,
        "hard_cardio_min": 0.0,
        "unknown_cardio_min": 0.0,
        "sleep_min": None,
        "hrv": None,
        "resting_hr": None,
        "steps": None,
        "active_energy": None,
        "exercise_min": None,
    }
    if not start or not end:
        return stats

    workout_rows = conn.execute(
        """
        WITH set_rollup AS (
            SELECT
                workout_id,
                COUNT(*) sets,
                SUM(CASE
                    WHEN weight_lbs IS NOT NULL AND reps IS NOT NULL
                    THEN weight_lbs * reps
                    ELSE 0
                END) volume_lbs,
                AVG(rpe) avg_rpe
            FROM workout_sets
            GROUP BY workout_id
        ),
        metric_rollup AS (
            SELECT
                workout_id,
                MAX(CASE WHEN metric_type = 'HeartRate' THEN avg END) avg_hr,
                MAX(CASE WHEN metric_type = 'HeartRate' THEN max END) max_hr,
                MAX(CASE WHEN metric_type = 'PhysicalEffort' THEN avg END) effort
            FROM workout_health_summary
            GROUP BY workout_id
        )
        SELECT
            w.workout_id,
            w.title,
            w.duration_sec / 60.0 duration_min,
            COALESCE(sr.sets, 0) sets,
            COALESCE(sr.volume_lbs, 0) volume_lbs,
            sr.avg_rpe,
            mr.avg_hr,
            mr.max_hr,
            mr.effort
        FROM workouts w
        LEFT JOIN set_rollup sr ON sr.workout_id = w.workout_id
        LEFT JOIN metric_rollup mr ON mr.workout_id = w.workout_id
        WHERE substr(w.start_local, 1, 10) BETWEEN ? AND ?
        """,
        (start, end),
    ).fetchall()

    efforts = []
    rpes = []
    for row in workout_rows:
        duration = row["duration_min"] or 0.0
        stats["workouts"] += 1
        stats["duration_min"] += duration
        stats["volume_lbs"] += row["volume_lbs"] or 0.0
        if row["effort"] is not None:
            efforts.append(row["effort"])
        if row["avg_rpe"] is not None:
            rpes.append(row["avg_rpe"])

        zone = _cardio_zone(row["title"], row["avg_hr"], row["max_hr"], row["effort"], duration)
        if zone:
            stats["cardio_min"] += duration
            if zone == "zone2":
                stats["zone2_min"] += duration
            elif zone == "hard":
                stats["hard_cardio_min"] += duration
            else:
                stats["unknown_cardio_min"] += duration

    set_rows = conn.execute(
        """
        SELECT s.exercise_title
        FROM workout_sets s
        JOIN workouts w ON w.workout_id = s.workout_id
        WHERE substr(w.start_local, 1, 10) BETWEEN ? AND ?
        """,
        (start, end),
    ).fetchall()
    for row in set_rows:
        res = taxonomy.classify(row["exercise_title"])
        if res["mechanic"] == "cardio":
            continue
        stats["strength_sets"] += 1
        if res["source"] == "unknown":
            stats["unknown_sets"] += 1
            title = row["exercise_title"] or "(unnamed)"
            stats["unmapped"][title] = stats["unmapped"].get(title, 0) + 1
            continue
        for leaf, weight in res["targets"]:
            stats["muscle_volume"][leaf] += weight
            if res["mechanic"] == "isolation":
                stats["iso_volume"][leaf] += weight

    for leaf, vol in stats["muscle_volume"].items():
        group, pattern = taxonomy.LEAVES[leaf]
        stats["group_volume"][group] = stats["group_volume"].get(group, 0.0) + vol
        stats["pattern_volume"][pattern] = stats["pattern_volume"].get(pattern, 0.0) + vol

    stats["avg_effort"] = _avg(efforts)
    stats["avg_rpe"] = _avg(rpes)
    stats["sleep_min"] = _sleep_avg(conn, "asleep_total_min", start, end)
    stats["hrv"] = _daily_metric_avg(conn, "HeartRateVariabilitySDNN", start, end)
    stats["resting_hr"] = _daily_metric_avg(conn, "RestingHeartRate", start, end)
    stats["steps"] = _daily_metric_avg(conn, "StepCount", start, end)
    stats["active_energy"] = _daily_metric_avg(conn, "ActiveEnergyBurned", start, end)
    stats["exercise_min"] = _daily_metric_avg(conn, "AppleExerciseTime", start, end)
    return stats


def _readiness(current: dict, previous: dict) -> tuple[str, list[str]]:
    flags = []
    sleep = current["sleep_min"]
    if sleep is not None and sleep < 390:
        flags.append("sleep under 6.5h")
    elif sleep is not None and sleep < 420:
        flags.append("sleep under 7h")

    hrv_ratio = _safe_ratio(current["hrv"], previous["hrv"])
    if hrv_ratio is not None and hrv_ratio < 0.9:
        flags.append("HRV down more than 10%")

    rhr_ratio = _safe_ratio(current["resting_hr"], previous["resting_hr"])
    if rhr_ratio is not None and rhr_ratio > 1.05:
        flags.append("resting HR up more than 5%")

    load_change = _pct_change(current["duration_min"], previous["duration_min"])
    if load_change is not None and load_change > 25:
        flags.append("training load up more than 25%")
    elif load_change is not None and load_change > 15:
        flags.append("training load up more than 15%")

    hard_change = _pct_change(current["hard_cardio_min"], previous["hard_cardio_min"])
    recovery_down = (
        (hrv_ratio is not None and hrv_ratio < 0.95)
        or (rhr_ratio is not None and rhr_ratio > 1.03)
        or (sleep is not None and sleep < 420)
    )
    if current["hard_cardio_min"] >= 60 and recovery_down:
        flags.append("hard cardio is high while recovery is down")
    elif hard_change is not None and hard_change > 30 and current["hard_cardio_min"] >= 45:
        flags.append("hard cardio rose sharply")

    red_flags = {
        "sleep under 6.5h",
        "training load up more than 25%",
        "hard cardio is high while recovery is down",
    }
    if any(f in red_flags for f in flags) or len(flags) >= 3:
        return "red", flags
    if flags:
        return "yellow", flags
    return "green", ["recovery and training load look stable"]


def _recommendation(priority, area, title, evidence, action, timeframe):
    return {
        "priority": priority,
        "area": area,
        "title": title,
        "evidence": evidence,
        "action": action,
        "timeframe": timeframe,
    }


def _build_recommendations(current: dict, previous: dict, readiness: str) -> list[dict]:
    recs = []
    load_change = _pct_change(current["duration_min"], previous["duration_min"])
    zone2_change = _pct_change(current["zone2_min"], previous["zone2_min"])
    hard_change = _pct_change(current["hard_cardio_min"], previous["hard_cardio_min"])
    strength_change = _pct_change(current["strength_sets"], previous["strength_sets"])
    sleep_change = _pct_change(current["sleep_min"], previous["sleep_min"])

    if current["zone2_min"] < 80:
        recs.append(_recommendation(
            "high" if readiness == "green" else "medium",
            "cardio",
            "Build your aerobic base",
            f"Zone 2 work is about {current['zone2_min']:.0f} min in the latest 30 days.",
            "Add 2 Zone 2 sessions per week at 25-35 minutes each.",
            "Next 4 weeks",
        ))
    elif zone2_change is not None and zone2_change < -20 and readiness != "red":
        recs.append(_recommendation(
            "medium",
            "cardio",
            "Bring Zone 2 back up",
            f"Zone 2 minutes are {abs(zone2_change):.0f}% lower than the prior 30 days.",
            "Add one easy aerobic session weekly before adding more hard intervals.",
            "Weeks 1-2",
        ))

    if current["hard_cardio_min"] >= 90 and readiness != "green":
        recs.append(_recommendation(
            "high",
            "cardio",
            "Cap hard cardio for now",
            f"Hard cardio is about {current['hard_cardio_min']:.0f} min while readiness is {readiness}.",
            "Keep intervals to 1 session per week until sleep/HRV/resting HR stabilize.",
            "Week 1",
        ))
    elif hard_change is not None and hard_change > 30 and current["hard_cardio_min"] >= 45:
        recs.append(_recommendation(
            "medium",
            "cardio",
            "Do not stack more intensity yet",
            f"Hard cardio is up {hard_change:.0f}% versus the prior 30 days.",
            "Hold hard cardio steady and add easy Zone 2 if you want more conditioning.",
            "Weeks 1-2",
        ))

    if readiness == "green" and current["strength_sets"] >= 20:
        recs.append(_recommendation(
            "high",
            "strength",
            "Push lifting volume slightly",
            f"Readiness is green with {current['strength_sets']} strength sets in the latest 30 days.",
            "Add 5-10% more work by adding 1 set to a few main lifts, not every lift.",
            "Weeks 2-4",
        ))
    elif load_change is not None and load_change > 25:
        recs.append(_recommendation(
            "high",
            "training load",
            "Hold total training load",
            f"Training time is up {load_change:.0f}% versus the prior 30 days.",
            "Keep next week close to this month's average before adding more volume.",
            "Week 1",
        ))
    elif strength_change is not None and strength_change < -20:
        recs.append(_recommendation(
            "medium",
            "strength",
            "Rebuild lifting consistency",
            f"Strength sets are down {abs(strength_change):.0f}% versus the prior 30 days.",
            "Add one full-body or lower-body session before increasing intensity.",
            "Weeks 1-2",
        ))

    mv = current["muscle_volume"]
    gv = current["group_volume"]
    chest = gv.get("chest", 0.0)
    back = gv.get("back", 0.0)
    biceps = gv.get("biceps", 0.0)
    triceps = gv.get("triceps", 0.0)
    quads = gv.get("quads", 0.0)
    hams = gv.get("hamstrings", 0.0)
    glutes = gv.get("glutes", 0.0)
    upper = chest + back + gv.get("shoulders", 0.0) + biceps + triceps
    delts_fs = mv["front_delts"] + mv["side_delts"]

    # chest/back is cleaner here than push/pull. push includes delts + triceps too.
    if chest >= 12 and back < chest * 0.9:
        recs.append(_recommendation(
            "medium",
            "strength balance",
            "Add back volume",
            f"Back ({back:.0f} sets) trails chest ({chest:.0f}) this month.",
            "Add 4-6 sets of rows or pulldowns each week to even chest and back.",
            "Next 4 weeks",
        ))
    if biceps + triceps >= 12 and min(biceps, triceps) < max(biceps, triceps) * 0.6:
        lagging = "biceps" if biceps < triceps else "triceps"
        recs.append(_recommendation(
            "low",
            "strength balance",
            "Even out arm work",
            f"Biceps {biceps:.0f} vs triceps {triceps:.0f} sets; {lagging} is lagging.",
            f"Add 3-4 sets of direct {lagging} work each week.",
            "Next 4 weeks",
        ))
    if quads >= 16 and hams < quads * 0.6:
        recs.append(_recommendation(
            "medium",
            "strength balance",
            "Balance the posterior chain",
            f"Hamstrings ({hams:.0f} sets) trail quads ({quads:.0f}) this month.",
            "Add 3-4 sets each of a hip hinge and a leg curl per week.",
            "Next 4 weeks",
        ))
    if hams >= 8 and (mv["ham_hinge"] == 0 or mv["ham_curl"] == 0):
        missing = "hip-hinge (RDL/deadlift)" if mv["ham_hinge"] == 0 else "knee-flexion (leg curl)"
        recs.append(_recommendation(
            "low",
            "strength balance",
            "Hit both hamstring functions",
            f"Hamstring work is all one pattern; {missing} is missing.",
            f"Add 3-4 sets of {missing} weekly so both functions get trained.",
            "Next 4 weeks",
        ))
    if delts_fs >= 12 and mv["rear_delts"] < delts_fs * 0.3:
        recs.append(_recommendation(
            "medium",
            "strength balance",
            "Bring up rear delts",
            f"Rear delts ({mv['rear_delts']:.0f} sets) lag front/side ({delts_fs:.0f}).",
            "Add 4-6 sets of face pulls or reverse flys each week.",
            "Next 4 weeks",
        ))
    if upper >= 24 and glutes < 6:
        recs.append(_recommendation(
            "low",
            "strength balance",
            "Add direct glute work",
            f"Glute volume is {glutes:.0f} sets while upper body sits at {upper:.0f}.",
            "Add one hip thrust or glute-focused session each week.",
            "Next 4 weeks",
        ))

    if current["sleep_min"] is not None and current["sleep_min"] < 420:
        recs.append(_recommendation(
            "high" if readiness == "red" else "medium",
            "recovery",
            "Raise the sleep floor",
            f"Average sleep is {current['sleep_min'] / 60.0:.1f}h over the latest 30 days.",
            "Protect a 7h sleep opportunity on the nights before harder sessions.",
            "Next 2 weeks",
        ))
    elif sleep_change is not None and sleep_change < -5:
        recs.append(_recommendation(
            "medium",
            "recovery",
            "Stop the sleep slide",
            f"Sleep is down {abs(sleep_change):.0f}% versus the prior 30 days.",
            "Keep hard workouts away from short-sleep days when possible.",
            "Weeks 1-2",
        ))

    if not recs:
        recs.append(_recommendation(
            "medium",
            "training",
            "Keep progressing gradually",
            "The latest 30 days look stable against the prior month.",
            "Add one small progression at a time: either 5-10% lifting volume or one easy aerobic session.",
            "Next 4 weeks",
        ))

    existing_titles = {r["title"] for r in recs}
    if "Keep hard days separated" not in existing_titles:
        recs.append(_recommendation(
            "low",
            "recovery",
            "Keep hard days separated",
            f"Hard cardio is about {current['hard_cardio_min']:.0f} min in the latest 30 days.",
            "Leave at least one easy or rest day between intervals and your hardest lifting sessions.",
            "Next 4 weeks",
        ))
    if "Review the next monthly export" not in existing_titles:
        recs.append(_recommendation(
            "low",
            "tracking",
            "Review the next monthly export",
            "These recommendations are based on the latest 30 days versus the prior 30 days.",
            "After your next upload, compare whether Zone 2, strength sets, sleep, HRV, and resting HR moved the right way.",
            "Next upload",
        ))

    recs.sort(key=lambda r: (PRIORITY_ORDER[r["priority"]], r["area"], r["title"]))
    return recs[:6]


def _monthly_plan(current: dict, readiness: str) -> list[dict]:
    weekly_lifts = max(2, round(current["workouts"] / 4))
    weekly_zone2 = max(50, round(current["zone2_min"] / 4))
    weekly_hard = round(current["hard_cardio_min"] / 4)
    weekly_sets = max(20, round(current["strength_sets"] / 4))

    if readiness == "green":
        week1 = "Hold this month's rhythm and keep hard days separated."
        week2 = "Add one small lift progression or 10-15 min Zone 2."
        week3 = "Progress another 5% if sleep and HRV stay steady."
        week4 = "Keep volume near week 3, then review the next export."
        set_target = f"{weekly_sets}-{round(weekly_sets * 1.1)} strength sets"
        zone2_target = f"{weekly_zone2}-{weekly_zone2 + 30} Zone 2 min"
    elif readiness == "yellow":
        week1 = "Hold total load steady and clean up the weakest recovery signal."
        week2 = "Add only easy aerobic work if recovery improves."
        week3 = "Resume small strength progressions if readiness turns green."
        week4 = "Keep hard cardio capped and compare against the new export."
        set_target = f"about {weekly_sets} strength sets"
        zone2_target = f"{weekly_zone2}-{weekly_zone2 + 20} Zone 2 min"
    else:
        week1 = "Deload intensity and keep sessions easy/moderate."
        week2 = "Return to baseline volume if sleep and resting HR improve."
        week3 = "Add Zone 2 before adding intervals or extra heavy sets."
        week4 = "Progress only if recovery signals are no longer red."
        set_target = f"{round(weekly_sets * 0.8)}-{weekly_sets} strength sets"
        zone2_target = f"about {weekly_zone2} easy Zone 2 min"

    hard_target = "0-1 hard cardio sessions" if weekly_hard < 30 or readiness != "green" else "1 hard cardio session"
    return [
        {"week": "Week 1", "lifting": set_target, "cardio": zone2_target,
         "recovery": hard_target, "progression": week1},
        {"week": "Week 2", "lifting": set_target, "cardio": zone2_target,
         "recovery": hard_target, "progression": week2},
        {"week": "Week 3", "lifting": set_target, "cardio": zone2_target,
         "recovery": hard_target, "progression": week3},
        {"week": "Week 4", "lifting": set_target, "cardio": zone2_target,
         "recovery": hard_target, "progression": week4},
    ]


def coach_recommendations(db_path: str) -> dict:
    """Next-month recommendations from the latest monthly window."""
    conn = db.connect(db_path)
    try:
        end = _latest_data_date(conn)
        current_window = _date_range(end, 30)
        previous_window = _previous_range(current_window)
        current = _month_stats(conn, *current_window)
        previous = _month_stats(conn, *previous_window)
    finally:
        conn.close()

    if not end:
        return {
            "latest_date": None,
            "current_window": current_window,
            "previous_window": previous_window,
            "readiness": None,
            "readiness_reasons": [],
            "current": current,
            "previous": previous,
            "recommendations": [],
            "monthly_plan": [],
        }

    readiness, reasons = _readiness(current, previous)
    return {
        "latest_date": end.isoformat(),
        "current_window": current_window,
        "previous_window": previous_window,
        "readiness": readiness,
        "readiness_reasons": reasons,
        "current": current,
        "previous": previous,
        "recommendations": _build_recommendations(current, previous, readiness),
        "monthly_plan": _monthly_plan(current, readiness),
    }


def movement_balance(db_path: str) -> dict:
    """Muscle-group volume breakdown for the latest 30 days."""
    conn = db.connect(db_path)
    try:
        end = _latest_data_date(conn)
        window = _date_range(end, 30)
        stats = _month_stats(conn, *window)
    finally:
        conn.close()

    strength = stats["strength_sets"]
    classified = strength - stats["unknown_sets"]
    return {
        "latest_date": end.isoformat() if end else None,
        "window": window,
        "groups": stats["group_volume"],
        "patterns": stats["pattern_volume"],
        "muscles": stats["muscle_volume"],
        "iso_volume": stats["iso_volume"],
        "chest_back": (stats["group_volume"].get("chest", 0.0),
                       stats["group_volume"].get("back", 0.0)),
        "quad_ham": (stats["group_volume"].get("quads", 0.0),
                     stats["group_volume"].get("hamstrings", 0.0)),
        "strength_sets": strength,
        "classified_pct": (100.0 * classified / strength) if strength else None,
        "unmapped": stats["unmapped"],
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
