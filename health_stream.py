"""Stream the giant Apple Health export without loading it all."""

import calendar
from bisect import bisect_right
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from common import sha1_id, short_metric

INTRA_SUM = {"ActiveEnergyBurned", "BasalEnergyBurned",
             "DistanceWalkingRunning", "StepCount"}
INTRA_POINT = {"HeartRate", "RespiratoryRate", "PhysicalEffort",
               "HeartRateVariabilitySDNN", "OxygenSaturation"}
INTRA = INTRA_SUM | INTRA_POINT

DAILY_SUM = {"ActiveEnergyBurned", "BasalEnergyBurned", "StepCount",
             "DistanceWalkingRunning", "AppleExerciseTime", "AppleStandTime",
             "FlightsClimbed"}
DAILY_POINT = {"RestingHeartRate", "HeartRateVariabilitySDNN",
               "WalkingHeartRateAverage", "VO2Max", "OxygenSaturation",
               "RespiratoryRate", "BodyMass", "BodyFatPercentage",
               "LeanBodyMass", "BloodPressureSystolic", "BloodPressureDiastolic"}
DAILY = DAILY_SUM | DAILY_POINT

SLEEP_TYPE = "SleepAnalysis"
HEART_RATE = "HeartRate"

# bigger gap means a new sleep night
NIGHT_GAP_SEC = 3 * 3600


def parse_health_dt(s: str):
    """Fast parse for Health timestamps."""
    y = int(s[0:4]); mo = int(s[5:7]); d = int(s[8:10])
    h = int(s[11:13]); mi = int(s[14:16]); se = int(s[17:19])
    off_min = int(s[21:23]) * 60 + int(s[23:25])
    if s[20] == "-":
        off_min = -off_min
    epoch = calendar.timegm((y, mo, d, h, mi, se, 0, 0, 0)) - off_min * 60
    return epoch, s[0:10]


@dataclass
class Stat:
    unit: str | None = None
    count: int = 0
    total: float = 0.0
    vmin: float = float("inf")
    vmax: float = float("-inf")
    first_epoch: float = float("inf")
    first_val: float | None = None
    last_epoch: float = float("-inf")
    last_val: float | None = None

    def add(self, value: float, epoch: float, unit: str | None):
        self.count += 1
        self.total += value
        if value < self.vmin:
            self.vmin = value
        if value > self.vmax:
            self.vmax = value
        if epoch < self.first_epoch:
            self.first_epoch, self.first_val = epoch, value
        if epoch > self.last_epoch:
            self.last_epoch, self.last_val = epoch, value
        if unit and not self.unit:
            self.unit = unit

    def as_row(self):
        return {
            "unit": self.unit,
            "sample_count": self.count,
            "avg": (self.total / self.count) if self.count else None,
            "min": self.vmin if self.count else None,
            "max": self.vmax if self.count else None,
            "sum": self.total,
            "first_value": self.first_val,
            "last_value": self.last_val,
        }


@dataclass
class HealthResult:
    workout_summaries: list[dict] = field(default_factory=list)
    daily_rows: list[dict] = field(default_factory=list)
    sleep_rows: list[dict] = field(default_factory=list)
    apple_workouts: list[dict] = field(default_factory=list)
    max_ts: float = 0.0
    records_scanned: int = 0
    records_used: int = 0


def _summarize_night(segments: list[tuple]) -> dict:
    """Roll sleep segments into one night."""
    mins = {"InBed": 0.0, "Awake": 0.0, "AsleepCore": 0.0, "AsleepDeep": 0.0,
            "AsleepREM": 0.0, "AsleepUnspecified": 0.0}
    segments.sort(key=lambda x: x[0])
    start_local = segments[0][2]
    end_local = segments[-1][3]
    for s_ep, e_ep, _, _, stage in segments:
        dur = (e_ep - s_ep) / 60.0
        mins[stage] = mins.get(stage, 0.0) + dur
    asleep = (mins["AsleepCore"] + mins["AsleepDeep"]
              + mins["AsleepREM"] + mins["AsleepUnspecified"])
    in_bed = mins["InBed"] if mins["InBed"] > 0 else (asleep + mins["Awake"])
    eff = (asleep / in_bed * 100.0) if in_bed > 0 else None
    return {
        "date": end_local[0:10],
        "in_bed_min": round(in_bed, 1),
        "asleep_total_min": round(asleep, 1),
        "core_min": round(mins["AsleepCore"], 1),
        "deep_min": round(mins["AsleepDeep"], 1),
        "rem_min": round(mins["AsleepREM"], 1),
        "unspecified_min": round(mins["AsleepUnspecified"], 1),
        "awake_min": round(mins["Awake"], 1),
        "sleep_start_local": start_local,
        "sleep_end_local": end_local,
        "efficiency_pct": round(eff, 1) if eff is not None else None,
    }


def stream_health(xml_path: str, floor_epoch: float, summary_windows: list[dict],
                  progress=None) -> HealthResult:
    """Parse the XML once and keep the summaries we need."""
    # lookup for workout-window matches
    windows = sorted(summary_windows, key=lambda w: w["start_utc"])
    starts = [w["start_utc"] for w in windows]
    max_dur = max((w["end_utc"] - w["start_utc"] for w in windows), default=0.0)

    workout_acc: dict[tuple[str, str], Stat] = {}
    daily_acc: dict[tuple[str, str], Stat] = {}
    sleep_segments: list[tuple] = []

    res = HealthResult()

    context = ET.iterparse(xml_path, events=("start", "end"))
    _, root = next(context)
    depth = 1
    in_correlation = 0

    for event, elem in context:
        if event == "start":
            depth += 1
            if elem.tag == "Correlation":
                in_correlation += 1
            continue

        tag = elem.tag
        if tag == "Record" and not in_correlation:
            res.records_scanned += 1
            if progress is not None and res.records_scanned % 200000 == 0:
                progress(res.records_scanned)
            _handle_record(elem, floor_epoch, windows, starts, max_dur,
                            workout_acc, daily_acc, sleep_segments, res)
        elif tag == "Workout":
            _handle_workout(elem, floor_epoch, res)
        elif tag == "Correlation":
            in_correlation -= 1

        depth -= 1
        if depth == 1:
            root.clear()

    for (wid, metric), stat in workout_acc.items():
        row = stat.as_row()
        row["workout_id"] = wid
        row["metric_type"] = metric
        res.workout_summaries.append(row)

    for (date, metric), stat in daily_acc.items():
        row = stat.as_row()
        row["date"] = date
        row["metric_type"] = metric
        res.daily_rows.append(row)

    if sleep_segments:
        sleep_segments.sort(key=lambda x: x[0])
        night: list[tuple] = []
        prev_end = None
        for seg in sleep_segments:
            if prev_end is not None and seg[0] - prev_end > NIGHT_GAP_SEC:
                res.sleep_rows.append(_summarize_night(night))
                night = []
            night.append(seg)
            prev_end = max(prev_end or seg[1], seg[1])
        if night:
            res.sleep_rows.append(_summarize_night(night))

    if progress is not None:
        progress(res.records_scanned)
    return res


def _handle_record(elem, floor_epoch, windows, starts, max_dur,
                   workout_acc, daily_acc, sleep_segments, res):
    rtype = elem.get("type")
    start = elem.get("startDate")
    if not rtype or not start:
        return
    metric = short_metric(rtype)

    is_sleep = metric == SLEEP_TYPE
    is_daily = metric in DAILY
    is_intra = metric in INTRA and windows
    if not (is_sleep or is_daily or is_intra):
        return

    epoch, local_date = parse_health_dt(start)
    if epoch < floor_epoch:
        return
    if epoch > res.max_ts:
        res.max_ts = epoch

    if is_sleep:
        end = elem.get("endDate")
        if end:
            e_epoch, _ = parse_health_dt(end)
            stage = short_metric_sleep(elem.get("value"))
            sleep_segments.append((epoch, e_epoch, start, end, stage))
        res.records_used += 1
        return

    raw = elem.get("value")
    if raw is None:
        return
    try:
        value = float(raw)
    except ValueError:
        return
    unit = elem.get("unit")
    res.records_used += 1

    if is_daily:
        key = (local_date, metric)
        st = daily_acc.get(key)
        if st is None:
            st = daily_acc[key] = Stat()
        st.add(value, epoch, unit)

    if is_intra:
        for wid in _windows_containing(epoch, windows, starts, max_dur):
            key = (wid, metric)
            st = workout_acc.get(key)
            if st is None:
                st = workout_acc[key] = Stat()
            st.add(value, epoch, unit)


def short_metric_sleep(value: str | None) -> str:
    """Shorten Apple sleep stage names."""
    if not value:
        return "Unknown"
    prefix = "HKCategoryValueSleepAnalysis"
    return value[len(prefix):] if value.startswith(prefix) else value


def _windows_containing(epoch, windows, starts, max_dur):
    """Workout windows that contain this sample."""
    idx = bisect_right(starts, epoch) - 1
    floor = epoch - max_dur
    while idx >= 0:
        w = windows[idx]
        if w["start_utc"] < floor:
            break
        if w["start_utc"] <= epoch <= w["end_utc"]:
            yield w["workout_id"]
        idx -= 1


def _handle_workout(elem, floor_epoch, res):
    start = elem.get("startDate")
    end = elem.get("endDate")
    if not start or not end:
        return
    s_epoch, s_local = parse_health_dt(start)
    if s_epoch < floor_epoch:
        return
    e_epoch, e_local = parse_health_dt(end)
    activity = short_metric(elem.get("workoutActivityType", ""))

    energy = _to_float(elem.get("totalEnergyBurned"))
    distance = _to_float(elem.get("totalDistance"))
    avg_hr = max_hr = None
    for child in elem:
        if child.tag != "WorkoutStatistics":
            continue
        stype = short_metric(child.get("type", ""))
        if stype == HEART_RATE:
            avg_hr = _to_float(child.get("average"))
            max_hr = _to_float(child.get("maximum"))
        elif stype in ("ActiveEnergyBurned",) and energy is None:
            energy = _to_float(child.get("sum"))
        elif stype == "DistanceWalkingRunning" and distance is None:
            distance = _to_float(child.get("sum"))

    res.apple_workouts.append({
        "id": sha1_id(s_epoch, e_epoch, activity),
        "activity_type": activity,
        "start_local": start,
        "end_local": end,
        "start_utc": s_epoch,
        "end_utc": e_epoch,
        "duration_min": _to_float(elem.get("duration")),
        "total_energy_cal": energy,
        "total_distance": distance,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
    })


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
