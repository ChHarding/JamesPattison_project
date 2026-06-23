"""SQLite stuff for FitLens."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS workouts (
    workout_id      TEXT PRIMARY KEY,   -- sha1(title|start|end)
    title           TEXT,
    description     TEXT,
    start_local     TEXT,               -- ISO 8601 with offset
    end_local       TEXT,
    start_utc       REAL,               -- epoch seconds
    end_utc         REAL,
    tz_name         TEXT,
    utc_offset_min  INTEGER,
    duration_sec    REAL,
    source          TEXT
);

CREATE TABLE IF NOT EXISTS workout_sets (
    set_pk          INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id      TEXT NOT NULL,
    exercise_title  TEXT,
    superset_id     TEXT,
    exercise_notes  TEXT,
    set_index       INTEGER,
    set_type        TEXT,
    weight_lbs      REAL,
    reps            REAL,
    distance_miles  REAL,
    duration_seconds REAL,
    rpe             REAL,
    UNIQUE (workout_id, exercise_title, set_index, set_type),
    FOREIGN KEY (workout_id) REFERENCES workouts(workout_id)
);

CREATE TABLE IF NOT EXISTS workout_health_summary (
    workout_id      TEXT NOT NULL,
    metric_type     TEXT NOT NULL,
    unit            TEXT,
    sample_count    INTEGER,
    avg             REAL,
    min             REAL,
    max             REAL,
    sum             REAL,
    first_value     REAL,
    last_value      REAL,
    PRIMARY KEY (workout_id, metric_type),
    FOREIGN KEY (workout_id) REFERENCES workouts(workout_id)
);

CREATE TABLE IF NOT EXISTS daily_health (
    date            TEXT NOT NULL,
    metric_type     TEXT NOT NULL,
    unit            TEXT,
    sample_count    INTEGER,
    avg             REAL,
    min             REAL,
    max             REAL,
    sum             REAL,
    last_value      REAL,
    PRIMARY KEY (date, metric_type)
);

CREATE TABLE IF NOT EXISTS daily_sleep (
    date                TEXT PRIMARY KEY,
    in_bed_min          REAL,
    asleep_total_min    REAL,
    core_min            REAL,
    deep_min            REAL,
    rem_min             REAL,
    unspecified_min     REAL,
    awake_min           REAL,
    sleep_start_local   TEXT,
    sleep_end_local     TEXT,
    efficiency_pct      REAL
);

CREATE TABLE IF NOT EXISTS apple_workouts (
    id                  TEXT PRIMARY KEY,
    activity_type       TEXT,
    start_local         TEXT,
    end_local           TEXT,
    start_utc           REAL,
    end_utc             REAL,
    duration_min        REAL,
    total_energy_cal    REAL,
    total_distance      REAL,
    avg_hr              REAL,
    max_hr              REAL
);

CREATE TABLE IF NOT EXISTS import_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sets_workout ON workout_sets(workout_id);
CREATE INDEX IF NOT EXISTS idx_whs_metric ON workout_health_summary(metric_type);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_health(date);
CREATE INDEX IF NOT EXISTS idx_workouts_start ON workouts(start_utc);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open the DB and make sure the tables exist."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def meta_get(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute(
        "SELECT value FROM import_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def meta_set(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO import_meta(key, value) VALUES (?, ?)",
        (key, None if value is None else str(value)),
    )


def insert_workout(conn: sqlite3.Connection, w: dict) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO workouts
            (workout_id, title, description, start_local, end_local,
             start_utc, end_utc, tz_name, utc_offset_min, duration_sec, source)
        VALUES
            (:workout_id, :title, :description, :start_local, :end_local,
             :start_utc, :end_utc, :tz_name, :utc_offset_min, :duration_sec, :source)
        """,
        w,
    )
    return cur.rowcount


def insert_set(conn: sqlite3.Connection, s: dict) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO workout_sets
            (workout_id, exercise_title, superset_id, exercise_notes,
             set_index, set_type, weight_lbs, reps, distance_miles,
             duration_seconds, rpe)
        VALUES
            (:workout_id, :exercise_title, :superset_id, :exercise_notes,
             :set_index, :set_type, :weight_lbs, :reps, :distance_miles,
             :duration_seconds, :rpe)
        """,
        s,
    )
    return cur.rowcount


def upsert_workout_health_summary(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO workout_health_summary
            (workout_id, metric_type, unit, sample_count, avg, min, max, sum,
             first_value, last_value)
        VALUES
            (:workout_id, :metric_type, :unit, :sample_count, :avg, :min, :max,
             :sum, :first_value, :last_value)
        """,
        row,
    )


def upsert_daily_health(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_health
            (date, metric_type, unit, sample_count, avg, min, max, sum, last_value)
        VALUES
            (:date, :metric_type, :unit, :sample_count, :avg, :min, :max, :sum,
             :last_value)
        """,
        row,
    )


def upsert_daily_sleep(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_sleep
            (date, in_bed_min, asleep_total_min, core_min, deep_min, rem_min,
             unspecified_min, awake_min, sleep_start_local, sleep_end_local,
             efficiency_pct)
        VALUES
            (:date, :in_bed_min, :asleep_total_min, :core_min, :deep_min,
             :rem_min, :unspecified_min, :awake_min, :sleep_start_local,
             :sleep_end_local, :efficiency_pct)
        """,
        row,
    )


def insert_apple_workout(conn: sqlite3.Connection, row: dict) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO apple_workouts
            (id, activity_type, start_local, end_local, start_utc, end_utc,
             duration_min, total_energy_cal, total_distance, avg_hr, max_hr)
        VALUES
            (:id, :activity_type, :start_local, :end_local, :start_utc, :end_utc,
             :duration_min, :total_energy_cal, :total_distance, :avg_hr, :max_hr)
        """,
        row,
    )
    return cur.rowcount
