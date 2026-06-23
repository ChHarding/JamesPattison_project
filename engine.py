"""Import path for FitLens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import db
from parse_workouts import parse_workouts
from health_stream import stream_health

# Re-read a little overlap so the last day/night can settle.
REAGG_OVERLAP_SEC = 36 * 3600


@dataclass
class ImportReport:
    is_first_run: bool
    coverage_start_local: str | None
    new_workouts: int = 0
    workouts_in_window: int = 0
    new_sets: int = 0
    workout_summaries_written: int = 0
    days_written: int = 0
    sleep_nights_written: int = 0
    new_apple_workouts: int = 0
    records_scanned: int = 0
    workout_date_min: str | None = None
    workout_date_max: str | None = None


def _requested_floor(tz_name, lookback_days, since, all_history):
    """Start date for the import."""
    tz = ZoneInfo(tz_name)
    if all_history:
        dt = datetime(1970, 1, 1, tzinfo=tz)
    elif since:
        dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        dt = datetime.now(tz) - timedelta(days=lookback_days)
    return dt.timestamp(), dt.isoformat()


def ingest(xml_path, csv_path, db_path, tz_name="America/New_York",
           lookback_days=365, since=None, all_history=False, expand_history=False,
           progress=None):
    """Import data into the DB."""
    conn = db.connect(db_path)
    try:
        stored = db.meta_get(conn, "coverage_start")
        is_first_run = stored is None

        if is_first_run:
            coverage_start, coverage_local = _requested_floor(
                tz_name, lookback_days, since, all_history)
        else:
            coverage_start = float(stored)
            coverage_local = db.meta_get(conn, "coverage_start_local")
            if expand_history:
                req_epoch, req_local = _requested_floor(
                    tz_name, lookback_days, since, all_history)
                if req_epoch < coverage_start:
                    coverage_start, coverage_local = req_epoch, req_local

        last_ingested = float(db.meta_get(conn, "last_ingested_ts", 0) or 0)
        if is_first_run or coverage_start < float(stored or coverage_start):
            stream_floor = coverage_start
        elif last_ingested:
            stream_floor = max(coverage_start, last_ingested - REAGG_OVERLAP_SEC)
        else:
            stream_floor = coverage_start

        db.meta_set(conn, "coverage_start", coverage_start)
        db.meta_set(conn, "coverage_start_local", coverage_local)

        report = ImportReport(is_first_run=is_first_run,
                              coverage_start_local=coverage_local)

        workouts, sets = parse_workouts(csv_path, tz_name)
        in_window = [w for w in workouts if w["end_utc"] >= coverage_start]
        in_window_ids = {w["workout_id"] for w in in_window}
        report.workouts_in_window = len(in_window)

        for w in in_window:
            report.new_workouts += db.insert_workout(conn, w)
        for s in sets:
            if s["workout_id"] in in_window_ids:
                report.new_sets += db.insert_set(conn, s)

        # only summarize workouts touched by this XML pass
        summary_windows = [w for w in in_window if w["end_utc"] >= stream_floor]

        res = stream_health(xml_path, stream_floor, summary_windows, progress=progress)
        report.records_scanned = res.records_scanned

        for row in res.workout_summaries:
            db.upsert_workout_health_summary(conn, row)
        report.workout_summaries_written = len(res.workout_summaries)

        for row in res.daily_rows:
            db.upsert_daily_health(conn, row)
        report.days_written = len({r["date"] for r in res.daily_rows})

        for row in res.sleep_rows:
            db.upsert_daily_sleep(conn, row)
        report.sleep_nights_written = len(res.sleep_rows)

        for row in res.apple_workouts:
            report.new_apple_workouts += db.insert_apple_workout(conn, row)

        new_watermark = max(last_ingested, res.max_ts)
        db.meta_set(conn, "last_ingested_ts", new_watermark)
        db.meta_set(conn, "tz_name", tz_name)
        db.meta_set(conn, "last_run", datetime.now().isoformat(timespec="seconds"))
        db.meta_set(conn, "xml_path", xml_path)
        db.meta_set(conn, "csv_path", csv_path)

        rng = conn.execute(
            "SELECT MIN(start_local) lo, MAX(start_local) hi FROM workouts"
        ).fetchone()
        report.workout_date_min = rng["lo"]
        report.workout_date_max = rng["hi"]

        conn.commit()
        return report
    finally:
        conn.close()


def db_snapshot(db_path):
    """Small DB summary for the welcome screen."""
    import os
    if not os.path.exists(db_path):
        return None
    conn = db.connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) c FROM workouts").fetchone()["c"]
        if not n:
            return None
        rng = conn.execute(
            "SELECT MIN(start_local) lo, MAX(start_local) hi FROM workouts"
        ).fetchone()
        days = conn.execute(
            "SELECT COUNT(DISTINCT date) c FROM daily_health"
        ).fetchone()["c"]
        nights = conn.execute("SELECT COUNT(*) c FROM daily_sleep").fetchone()["c"]
        return {
            "workouts": n,
            "date_min": rng["lo"],
            "date_max": rng["hi"],
            "days": days,
            "nights": nights,
            "last_run": db.meta_get(conn, "last_run"),
            "tz_name": db.meta_get(conn, "tz_name"),
        }
    finally:
        conn.close()
