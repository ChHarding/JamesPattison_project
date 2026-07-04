#!/usr/bin/env python3
"""FitLens CLI.

Run this file and follow the prompts.
"""

import os
import sys
import traceback
from datetime import date

import engine
import insights
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

HOME = os.path.expanduser("~")
DOWNLOADS = os.path.join(HOME, "Downloads")
DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fitlens.db")
ERROR_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fitlens_error.log")
console = Console()


def say(msg=""):
    console.print(msg)


def panel(body, title=None, style="cyan"):
    console.print(Panel(body, title=title, border_style=style, padding=(1, 2)))


def ask_path(message, default=None):
    while True:
        ans = questionary.path(message, default=default or "").ask()
        if ans is None:
            sys.exit(0)
        ans = os.path.expanduser(ans.strip().strip('"').strip("'"))
        if os.path.isfile(ans):
            return ans
        say(f"[red]I couldn't find a file at:[/red] {ans}\n"
            "Tip: you can drag the file into this window to paste its path.")


def ask_select(message, choices, default=None):
    ans = questionary.select(message, choices=choices, default=default).ask()
    if ans is None:
        sys.exit(0)
    return ans


def ask_text(message, default=None):
    ans = questionary.text(message, default=default or "").ask()
    return ans if ans is not None else sys.exit(0)


def ask_confirm(message, default=True):
    ans = questionary.confirm(message, default=default).ask()
    return bool(ans) if ans is not None else sys.exit(0)


def detect_local_tz():
    try:
        p = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in p:
            return p.split("zoneinfo/")[-1]
    except Exception:
        pass
    return "America/New_York"


def autodetect(name):
    p = os.path.join(DOWNLOADS, name)
    return p if os.path.isfile(p) else None


def pick_file(label, filename, current=None):
    """Use the guessed file if it looks right."""
    guess = current or autodetect(filename)
    if guess and ask_confirm(f"Use this {label}?\n   {guess}", default=True):
        return guess
    return ask_path(f"Path to your {label} ({filename})")


LOOKBACK_CHOICES = {
    "Past year (recommended)": ("days", 365),
    "Past 6 months": ("days", 182),
    "Past 2 years": ("days", 730),
    "All of my history": ("all", None),
}


def ask_lookback():
    label = ask_select("How much history should I bring in?",
                       list(LOOKBACK_CHOICES.keys()),
                       default="Past year (recommended)")
    kind, val = LOOKBACK_CHOICES[label]
    return kind, val, label


def run_import(xml, csv, db_path, tz, lookback_kind, lookback_val):
    kwargs = dict(tz_name=tz)
    if lookback_kind == "all":
        kwargs["all_history"] = True
    else:
        kwargs["lookback_days"] = lookback_val

    with Progress(SpinnerColumn(), TextColumn("[cyan]Reading Apple Health export[/cyan]"),
                  BarColumn(), TextColumn("{task.fields[count]}"),
                  TimeElapsedColumn(), console=console, transient=True) as prog:
        task = prog.add_task("scan", total=None, count="0 records")

        def cb(n):
            prog.update(task, count=f"{n:,} records")

        report = engine.ingest(xml, csv, db_path, progress=cb, **kwargs)
    return report


def show_report(report, returning):
    body = []
    if returning:
        body.append("[bold green]All caught up![/bold green] Here's what was added this time:\n")
    else:
        body.append("[bold green]Setup complete![/bold green] Here's what I imported:\n")
    body.append(f"  • Workouts saved: [bold]{report.new_workouts}[/bold]"
                + (f"  ([dim]{report.workouts_in_window} in range[/dim])" if not returning else ""))
    body.append(f"  • Exercise sets: [bold]{report.new_sets}[/bold]")
    body.append(f"  • Workouts matched to live health metrics: [bold]{report.workout_summaries_written}[/bold]")
    body.append(f"  • Days of daily health stats: [bold]{report.days_written}[/bold]")
    body.append(f"  • Nights of sleep: [bold]{report.sleep_nights_written}[/bold]")
    if report.workout_date_min:
        body.append(f"\n[dim]Training data now spans "
                    f"{report.workout_date_min[:10]} → {report.workout_date_max[:10]}[/dim]")
    if returning and report.new_workouts == 0 and report.new_sets == 0:
        body = ["[bold]Nothing new to add[/bold] — your data was already up to date. 👍"]
    panel("\n".join(body), title="✅ Done", style="green")


def fmt_num(value, digits=0, suffix=""):
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}{suffix}"


def fmt_minutes(value):
    if value is None:
        return "n/a"
    value = float(value)
    if value >= 90:
        return f"{value / 60.0:.1f}h"
    return f"{value:.0f}m"


def fmt_change(value):
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def fmt_delta(current, previous):
    if current is None or previous in (None, 0):
        return "n/a"
    return fmt_change((current - previous) / previous * 100.0)


def fmt_date_range(window):
    if not window or not window[0] or not window[1]:
        return "n/a"
    start = date.fromisoformat(window[0])
    end = date.fromisoformat(window[1])
    if start.year == end.year:
        return f"{start:%b %-d} - {end:%b %-d, %Y}"
    return f"{start:%b %-d, %Y} - {end:%b %-d, %Y}"


def render_status(db_path):
    data = insights.status(db_path)
    counts = data["tables"]
    train_lo, train_hi = data["training_range"]
    daily_lo, daily_hi = data["daily_range"]
    sleep_lo, sleep_hi = data["sleep_range"]
    meta = data["meta"]

    tbl = Table(title="Imported Data Counts", show_header=True, header_style="bold cyan")
    tbl.add_column("Area")
    tbl.add_column("Count", justify="right")
    for key, label in (
        ("workouts", "Workouts"),
        ("workout_sets", "Exercise sets"),
        ("workout_health_summary", "Workout health summaries"),
        ("daily_health", "Daily health rows"),
        ("daily_sleep", "Sleep nights"),
        ("apple_workouts", "Apple workouts"),
    ):
        tbl.add_row(label, f"{counts[key]:,}")
    console.print(tbl)

    ranges = (
        f"Training: {train_lo[:10] if train_lo else 'n/a'} -> {train_hi[:10] if train_hi else 'n/a'}\n"
        f"Daily health: {daily_lo or 'n/a'} -> {daily_hi or 'n/a'}\n"
        f"Sleep: {sleep_lo or 'n/a'} -> {sleep_hi or 'n/a'}\n"
        f"Last import: {meta.get('last_run', 'n/a')}"
    )
    panel(ranges, title="Data Coverage", style="cyan")


def render_recent(db_path, limit=10):
    rows = insights.recent_workouts(db_path, limit=limit)
    if not rows:
        panel("No workouts found yet. Import your data first.", title="Recent Workouts", style="yellow")
        return

    tbl = Table(title=f"Recent Workouts ({len(rows)})", show_header=True, header_style="bold cyan")
    for col in ("Date", "Time", "Workout", "Min", "Sets", "Volume", "Avg HR", "Effort"):
        justify = "right" if col in {"Min", "Sets", "Volume", "Avg HR", "Effort"} else "left"
        tbl.add_column(col, justify=justify)
    for r in rows:
        tbl.add_row(
            r["day"],
            r["time"] or "",
            r["title"] or "Workout",
            fmt_num(r["duration_min"], 0),
            fmt_num(r["sets"], 0),
            fmt_num(r["volume_lbs"], 0),
            fmt_num(r["avg_hr"], 0),
            fmt_num(r["effort"], 1),
        )
    console.print(tbl)


def render_weekly(db_path, weeks=8):
    rows = insights.weekly_summary(db_path, weeks=weeks)
    if not rows:
        panel("No workouts found yet. Import your data first.", title="Weekly Training", style="yellow")
        return

    tbl = Table(title=f"Weekly Training Load ({len(rows)} weeks)", show_header=True, header_style="bold cyan")
    for col in ("Week Of", "Workouts", "Time", "Sets", "Volume", "Avg HR", "Effort"):
        justify = "right" if col != "Week Of" else "left"
        tbl.add_column(col, justify=justify)
    for r in rows:
        tbl.add_row(
            r["week_start"],
            fmt_num(r["workouts"], 0),
            fmt_minutes(r["duration_min"]),
            fmt_num(r["sets"], 0),
            fmt_num(r["volume_lbs"], 0),
            fmt_num(r["avg_hr"], 0),
            fmt_num(r["avg_effort"], 1),
        )
    console.print(tbl)


def render_recovery(db_path):
    data = insights.recovery_summary(db_path)
    if not data["latest_date"]:
        panel("No recovery data found yet. Import your Apple Health export first.",
              title="Recovery", style="yellow")
        return

    sleep = data["sleep"]
    metrics = data["metrics"]
    windows = data["windows"]
    previous_windows = data["previous_windows"]
    window_labels = {days: fmt_date_range(windows[days]) for days in (7, 30, 60, 90)}
    previous_labels = {
        days: fmt_date_range(previous_windows[days])
        for days in (7, 30, 60, 90)
    }
    range_lines = "\n".join(
        f"  {days}-day: [bold]{window_labels[days]}[/bold]  vs  {previous_labels[days]}"
        for days in (7, 30, 60, 90)
    )
    panel(range_lines, title="Recovery Windows", style="cyan")
    tbl = Table(title="Recovery Averages", show_header=True, header_style="bold cyan")
    tbl.add_column("Metric")
    tbl.add_column("7-day avg", justify="right")
    tbl.add_column("30-day avg", justify="right")
    tbl.add_column("60-day avg", justify="right")
    tbl.add_column("90-day avg", justify="right")
    tbl.add_row("Sleep", fmt_minutes(sleep["asleep_min_7"]),
                fmt_minutes(sleep["asleep_min_30"]),
                fmt_minutes(sleep["asleep_min_60"]),
                fmt_minutes(sleep["asleep_min_90"]))
    tbl.add_row("Sleep eff.", fmt_num(sleep["efficiency_7"], 1, "%"),
                fmt_num(sleep["efficiency_30"], 1, "%"),
                fmt_num(sleep["efficiency_60"], 1, "%"),
                fmt_num(sleep["efficiency_90"], 1, "%"))
    labels = {
        "RestingHeartRate": "Resting HR",
        "HeartRateVariabilitySDNN": "HRV",
        "StepCount": "Steps",
        "ActiveEnergyBurned": "Active energy",
        "AppleExerciseTime": "Exercise min",
        "VO2Max": "VO2 max",
    }
    for metric, label in labels.items():
        m = metrics[metric]
        tbl.add_row(label,
                    fmt_num(m["avg_7"], 1),
                    fmt_num(m["avg_30"], 1),
                    fmt_num(m["avg_60"], 1),
                    fmt_num(m["avg_90"], 1))
    console.print(tbl)

    change_tbl = Table(title="Change vs Previous Same-Length Window",
                       show_header=True, header_style="bold cyan")
    change_tbl.add_column("Metric")
    for days in (7, 30, 60, 90):
        change_tbl.add_column(f"{days}-day", justify="right")
    change_tbl.add_row("Sleep",
                       fmt_change(sleep["asleep_change_7_pct"]),
                       fmt_change(sleep["asleep_change_30_pct"]),
                       fmt_change(sleep["asleep_change_60_pct"]),
                       fmt_change(sleep["asleep_change_90_pct"]))
    change_tbl.add_row("Sleep eff.",
                       fmt_change(sleep["efficiency_change_7_pct"]),
                       fmt_change(sleep["efficiency_change_30_pct"]),
                       fmt_change(sleep["efficiency_change_60_pct"]),
                       fmt_change(sleep["efficiency_change_90_pct"]))
    for metric, label in labels.items():
        m = metrics[metric]
        change_tbl.add_row(label,
                           fmt_change(m["change_7_pct"]),
                           fmt_change(m["change_30_pct"]),
                           fmt_change(m["change_60_pct"]),
                           fmt_change(m["change_90_pct"]))
    console.print(change_tbl)


def render_insights(db_path):
    data = insights.coach_insights(db_path)
    if not data["latest_date"]:
        panel("No data found yet. Import your exports first.", title="Coach Insights", style="yellow")
        return

    current = data["current_7"]
    previous = data["previous_7"]
    sleep = data["recovery"]["sleep"]
    hrv = data["recovery"]["metrics"]["HeartRateVariabilitySDNN"]
    rhr = data["recovery"]["metrics"]["RestingHeartRate"]
    recent = data["recent_workout"]
    current_window = fmt_date_range(data["recovery"]["window_7"])
    baseline_window = fmt_date_range(data["recovery"]["window_30"])

    lines = [
        f"[bold]Data window:[/bold] {current_window}",
        f"[dim]Baseline comparison: {baseline_window}[/dim]",
        "",
        f"[bold cyan]Training ({current_window})[/bold cyan]",
        f"  Workouts: {current['count']} ({fmt_minutes(current['duration_min'])})",
        f"  Prior 7 days: {previous['count']} ({fmt_minutes(previous['duration_min'])})",
        f"  Avg workout effort: {fmt_num(current['avg_effort'], 1)}",
        "",
        "[bold cyan]Recovery context[/bold cyan]",
        f"  Sleep: {fmt_minutes(sleep['asleep_min_7'])} avg vs {fmt_minutes(sleep['asleep_min_30'])} baseline",
        f"  HRV: {fmt_num(hrv['avg_7'], 1)} avg vs {fmt_num(hrv['avg_30'], 1)} baseline",
        f"  Resting HR: {fmt_num(rhr['avg_7'], 1)} avg vs {fmt_num(rhr['avg_30'], 1)} baseline",
    ]
    if recent:
        lines.extend([
            "",
            "[bold cyan]Most recent workout[/bold cyan]",
            f"  {recent['day']} {recent['title']} - {fmt_minutes(recent['duration_min'])}, "
            f"avg HR {fmt_num(recent['avg_hr'], 0)}, effort {fmt_num(recent['effort'], 1)}",
        ])
    lines.extend(["", "[bold cyan]Coach notes[/bold cyan]"])
    lines.extend(f"  • {note}" for note in data["notes"])
    panel("\n".join(lines), title="Coach Insights", style="green")


def render_recommendations(db_path):
    data = insights.coach_recommendations(db_path)
    if not data["latest_date"]:
        panel("No data found yet. Import your exports first.",
              title="Coach Recommendations", style="yellow")
        return

    current = data["current"]
    previous = data["previous"]
    readiness = data["readiness"]
    style = {"green": "green", "yellow": "yellow", "red": "red"}.get(readiness, "cyan")
    current_range = fmt_date_range(data["current_window"])
    previous_range = fmt_date_range(data["previous_window"])
    reasons = "; ".join(data["readiness_reasons"])

    overview = [
        f"[bold]Readiness:[/bold] [{style}]{readiness.upper()}[/{style}]",
        f"[bold]Current month:[/bold] {current_range}",
        f"[dim]Compared with: {previous_range}[/dim]",
        "",
        f"Training: {current['workouts']} workouts, {fmt_minutes(current['duration_min'])} "
        f"({fmt_delta(current['duration_min'], previous['duration_min'])})",
        f"Strength: {current['strength_sets']} sets "
        f"({fmt_delta(current['strength_sets'], previous['strength_sets'])})",
        f"Cardio: {fmt_minutes(current['cardio_min'])} total, "
        f"{fmt_minutes(current['zone2_min'])} Zone 2, "
        f"{fmt_minutes(current['hard_cardio_min'])} hard",
        f"Sleep: {fmt_minutes(current['sleep_min'])} avg",
        "",
        f"[dim]{reasons}[/dim]",
    ]
    panel("\n".join(overview), title="Coach Recommendations", style=style)

    rec_tbl = Table(title="Priority Actions", show_header=True, header_style="bold cyan")
    rec_tbl.add_column("Priority")
    rec_tbl.add_column("Area")
    rec_tbl.add_column("Recommendation")
    rec_tbl.add_column("Action")
    rec_tbl.add_column("Timeframe")
    for rec in data["recommendations"]:
        rec_tbl.add_row(
            rec["priority"].title(),
            rec["area"].title(),
            f"[bold]{rec['title']}[/bold]\n[dim]{rec['evidence']}[/dim]",
            rec["action"],
            rec["timeframe"],
        )
    console.print(rec_tbl)

    plan_tbl = Table(title="Next 4 Weeks", show_header=True, header_style="bold cyan")
    for col in ("Week", "Lifting", "Cardio", "Intensity", "Progression"):
        plan_tbl.add_column(col)
    for week in data["monthly_plan"]:
        plan_tbl.add_row(
            week["week"],
            week["lifting"],
            week["cardio"],
            week["recovery"],
            week["progression"],
        )
    console.print(plan_tbl)


def onboarding(db_path):
    panel(
        "Welcome to [bold cyan]FitLens[/bold cyan] 👋\n\n"
        "I turn your gym log and your Apple Health export into one tidy database — "
        "matching the heart rate, calories, and effort recorded [italic]during[/italic] each "
        "workout, plus your daily recovery stats like sleep and resting heart rate.\n\n"
        "This powers scoring and smart training suggestions down the road.\n\n"
        "Let's get you set up — takes about a minute.",
        title="FitLens", style="cyan")

    xml = pick_file("Apple Health export", "export.xml")
    csv = pick_file("workout history", "workouts.csv")
    tz = ask_text("What's your timezone?", default=detect_local_tz())
    kind, val, label = ask_lookback()

    panel(f"Here's the plan:\n\n"
          f"  • Health export: [bold]{xml}[/bold]\n"
          f"  • Workout file:  [bold]{csv}[/bold]\n"
          f"  • Timezone:      [bold]{tz}[/bold]\n"
          f"  • History:       [bold]{label}[/bold]\n\n"
          "Your data stays on this computer.", title="Ready to import", style="cyan")
    if not ask_confirm("Start the import?", default=True):
        say("No problem — run me again whenever you're ready.")
        return
    report = run_import(xml, csv, db_path, tz, kind, val)
    show_report(report, returning=False)


def welcome_back(snap):
    info = (f"You currently have [bold]{snap['workouts']}[/bold] workouts, "
            f"[bold]{snap['days']}[/bold] days of health data, and "
            f"[bold]{snap['nights']}[/bold] nights of sleep.\n"
            f"[dim]Training spans {snap['date_min'][:10]} → {snap['date_max'][:10]}"
            + (f" · last import {snap['last_run'][:10]}" if snap.get('last_run') else "")
            + "[/dim]")
    panel("Welcome back to [bold cyan]FitLens[/bold cyan] 👋\n\n" + info,
          title="FitLens", style="cyan")


def import_existing(db_path, snap):
    welcome_back(snap)
    if not ask_confirm("Got a fresh export to add?", default=True):
        say("Okay! Nothing changed.")
        return

    say("[dim]Re-export from the Health app and Hevy, then point me at the files.[/dim]")
    xml = pick_file("new Apple Health export", "export.xml")
    csv = pick_file("new workout history", "workouts.csv")
    # keep the original timezone/window for normal updates
    report = run_import(xml, csv, db_path, snap.get("tz_name") or detect_local_tz(),
                        "days", 365)
    show_report(report, returning=True)


GROUP_ORDER = [
    ("chest", [("upper_chest", "upper"), ("mid_chest", "mid"), ("lower_chest", "lower")]),
    ("shoulders", [("front_delts", "front"), ("side_delts", "side"), ("rear_delts", "rear")]),
    ("back", [("lats", "lats"), ("mid_back", "rows")]),
    ("triceps", []),
    ("biceps", []),
    ("quads", [("quad_compound", "compound"), ("quad_isolation", "isolation")]),
    ("hamstrings", [("ham_hinge", "hinge"), ("ham_curl", "curl")]),
    ("glutes", []),
    ("adductors", []),
    ("abductors", []),
    ("calves", []),
    ("core", [("abs", "abs"), ("obliques", "obliques"), ("lower_back", "low-back")]),
]


def render_movement_balance(db_path):
    data = insights.movement_balance(db_path)
    if not data["latest_date"]:
        panel("No data found yet. Import your exports first.",
              title="Movement Balance", style="yellow")
        return

    groups = data["groups"]
    muscles = data["muscles"]
    quad, ham = data["quad_ham"]

    lines = [
        f"[bold]Window:[/bold] {fmt_date_range(data['window'])}  "
        f"[dim]({data['strength_sets']:.0f} sets, {fmt_num(data['classified_pct'], 0)}% classified)[/dim]",
        "[dim]Fractional sets: 1.0 per primary muscle, 0.5 per assisting muscle.[/dim]",
        "",
        "[bold cyan]Volume by muscle group[/bold cyan]",
    ]
    for group, leaves in GROUP_ORDER:
        total = groups.get(group, 0.0)
        line = f"  {group.capitalize():12} {total:5.1f}"
        subs = [f"{label} {muscles[leaf]:.1f}" for leaf, label in leaves if muscles.get(leaf, 0.0)]
        if subs:
            line += f"   [dim]({', '.join(subs)})[/dim]"
        lines.append(line)

    chest = groups.get("chest", 0.0)
    back = groups.get("back", 0.0)
    biceps = groups.get("biceps", 0.0)
    triceps = groups.get("triceps", 0.0)
    lines.extend([
        "",
        "[bold cyan]Balance[/bold cyan] [dim](same-role muscles, not push vs pull)[/dim]",
        f"  Chest : Back      {chest:.0f} : {back:.0f}   [dim]({_ratio_str(chest, back)})[/dim]",
        f"  Quads : Hams      {quad:.0f} : {ham:.0f}   [dim]({_ratio_str(quad, ham)})[/dim]",
        f"  Biceps : Triceps  {biceps:.0f} : {triceps:.0f}   [dim]({_ratio_str(biceps, triceps)})[/dim]",
    ])

    if data["unmapped"]:
        lines.extend(["", "[bold yellow]Unmapped exercises[/bold yellow] "
                      "[dim](add to taxonomy.EXERCISE_MAP)[/dim]"])
        for title, n in sorted(data["unmapped"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {title} ({n})")

    panel("\n".join(lines), title="Movement Balance", style="cyan")


def _ratio_str(a, b):
    if not b:
        return "second is zero" if a else "n/a"
    return f"{a / b:.2f}x"


MENU_CHOICES = [
    "Coach insights",
    "Coach recommendations",
    "Movement balance",
    "Recent workouts",
    "Weekly training summary",
    "Recovery trends",
    "Data coverage",
    "Import new data",
    "Quit",
]


def coach_menu(db_path, snap):
    welcome_back(snap)
    while True:
        choice = ask_select("What do you want to do?", MENU_CHOICES, default="Coach insights")
        if choice == "Coach insights":
            render_insights(db_path)
        elif choice == "Coach recommendations":
            render_recommendations(db_path)
        elif choice == "Movement balance":
            render_movement_balance(db_path)
        elif choice == "Recent workouts":
            render_recent(db_path, limit=10)
        elif choice == "Weekly training summary":
            render_weekly(db_path, weeks=8)
        elif choice == "Recovery trends":
            render_recovery(db_path)
        elif choice == "Data coverage":
            render_status(db_path)
        elif choice == "Import new data":
            import_existing(db_path, snap)
            snap = engine.db_snapshot(db_path) or snap
        else:
            say("See you next session.")
            return


def main():
    db_path = DEFAULT_DB
    try:
        if len(sys.argv) > 1:
            panel("FitLens is guided now. Run [bold]python fitlens.py[/bold] "
                  "without command-line options to use the coach menu.",
                  title="Guided Mode", style="yellow")
            return

        snap = engine.db_snapshot(db_path)
        if snap:
            coach_menu(db_path, snap)
        else:
            onboarding(db_path)
    except KeyboardInterrupt:
        say("\nGoodbye 👋, see you again soon!")
    except Exception as e:
        with open(ERROR_LOG, "w") as f:
            f.write(traceback.format_exc())
        panel(f"Something went wrong:\n\n  [red]{e}[/red]\n\n"
              f"The technical details are saved in:\n  {ERROR_LOG}\n\n"
              "Double-check the file paths and try again — your data is safe.",
              title="⚠️  Import failed", style="red")
        sys.exit(1)


if __name__ == "__main__":
    main()
