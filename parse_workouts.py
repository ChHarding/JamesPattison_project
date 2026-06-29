"""Hevy CSV -> workouts and sets."""

import csv
from datetime import datetime
from zoneinfo import ZoneInfo

from common import sha1_id, to_float, to_int

CSV_TIME_FMT = "%b %d, %Y, %I:%M %p"


def _localize(text: str, tz: ZoneInfo) -> datetime:
    """Hevy times need the timezone added."""
    naive = datetime.strptime(text.strip(), CSV_TIME_FMT)
    return naive.replace(tzinfo=tz)


def parse_workouts(csv_path: str, tz_name: str):
    """Return workouts and sets ready for the DB."""
    tz = ZoneInfo(tz_name)
    workouts: dict[str, dict] = {}
    sets: list[dict] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            start_dt = _localize(row["start_time"], tz)
            end_dt = _localize(row["end_time"], tz)
            wid = sha1_id(row["title"], start_dt.isoformat(), end_dt.isoformat())

            if wid not in workouts:
                offset = start_dt.utcoffset()
                workouts[wid] = {
                    "workout_id": wid,
                    "title": row["title"],
                    "description": row.get("description") or None,
                    "start_local": start_dt.isoformat(),
                    "end_local": end_dt.isoformat(),
                    "start_utc": start_dt.timestamp(),
                    "end_utc": end_dt.timestamp(),
                    "tz_name": tz_name,
                    "utc_offset_min": int(offset.total_seconds() // 60) if offset else None,
                    "duration_sec": (end_dt - start_dt).total_seconds(),
                    "source": "hevy",
                }

            sets.append({
                "workout_id": wid,
                "exercise_title": row.get("exercise_title") or None,
                "superset_id": row.get("superset_id") or None,
                "exercise_notes": row.get("exercise_notes") or None,
                "set_index": to_int(row.get("set_index")),
                "set_type": row.get("set_type") or None,
                "weight_lbs": to_float(row.get("weight_lbs")),
                "reps": to_float(row.get("reps")),
                "distance_miles": to_float(row.get("distance_miles")),
                "duration_seconds": to_float(row.get("duration_seconds")),
                "rpe": to_float(row.get("rpe")),
            })

    return list(workouts.values()), sets
