# FitLens Project Spec - Revised Version 2

Project Name: FitLens

Original Spec Source: `FitLens_ProjectSpec_Final.pdf`

Revision Date: July 4, 2026

## Revision Legend

- **[REVISED]** means I changed the original plan to better match what is actually implemented and what is realistic before the class ends in early August.
- **[UNCHANGED]** means the original idea still fits the project.
- **[DEFERRED]** means the idea is still valid, but I am moving it out of the required final scope.
- **[REMOVED]** means I no longer plan to include that part in this class version.

## 1. General Description of the Project

**[UNCHANGED]** FitLens is a local fitness analysis application that helps me understand my training history by combining data that is normally split across multiple apps. Apple Health contains recovery and cardio-related data like heart rate, HRV, resting heart rate, sleep, VO2 max, steps, and active energy. Hevy contains the strength-training side, like workouts, exercises, sets, reps, weight, RPE, and volume.

**[REVISED]** The original spec described FitLens as a local Python desktop application with an initial command-line version. That is still the right direction, but the order is clearer now: **Version 1 proves the data pipeline through a guided CLI, and Version 2/final will focus on building a desktop GUI on top of that working core**. The GUI is not starting from scratch. It will reuse the import, SQLite, and insights modules that already work.

**[UNCHANGED]** The core purpose is still historical fitness analysis and a monthly coaching check-in. The app is not trying to diagnose medical conditions, replace a doctor, or replace a real coach. It is meant to turn raw personal fitness exports into clearer summaries and practical training suggestions.

**[REVISED]** The current working version already imports Apple Health XML and Hevy CSV data, stores the cleaned data in a local SQLite database, and lets me explore the data through a guided menu. Instead of requiring the user to remember command-line flags, the app now opens a menu with options like Coach insights, Coach recommendations, Movement balance, Recent workouts, Weekly training summary, Recovery trends, Data coverage, and Import new data. For Version 2, these same screens become the main sections of the desktop GUI.

**[REVISED]** The first spec mentioned using pandas DataFrames as the main cleaned-data layer. The actual implementation does not use pandas. I switched to a more direct pipeline using Python's standard library, streaming XML parsing, and SQLite. This ended up being a better fit because Apple Health exports can be very large, and I did not want to load the whole file into memory if I did not need to.

**[REVISED]** FitLens now focuses on these final Version 2 goals:

- Build a desktop GUI that wraps the existing working pipeline.
- Let the user choose Apple Health and Hevy files with file-picker controls.
- Show the current CLI summaries as GUI screens instead of terminal tables only.
- Improve import validation and error messages.
- Keep the SQLite data model stable.
- Make the coaching recommendations more transparent and defensible.
- Improve the movement-balance taxonomy so more exercises are classified correctly.
- Add documentation, screenshots, and a revised project spec in the repo.
- Keep the CLI available as a fallback/demo path, but make the GUI the main final focus.

## 2. Task Vignettes

### Vignette 1: Importing Apple Health and Hevy Data

**Original idea:** The user would run a command like:

```bash
python fitlens.py import --apple export.xml --hevy workouts.csv
```

or eventually use a desktop GUI to select files.

**[REVISED]** The current app uses a guided CLI instead of subcommands. The user runs:

```bash
python fitlens.py
```

If there is no existing `fitlens.db`, FitLens starts onboarding. It asks the user to choose their Apple Health XML export, choose their Hevy workout CSV, confirm the timezone, and pick how much history to import. If a database already exists, the app opens the main menu and lets the user choose **Import new data** when they have fresh exports.

**[REVISED] Version 2 GUI plan:** The desktop app will keep the same import workflow, but the user will click buttons instead of answering terminal prompts. The GUI should have file-picker controls for the Apple Health XML file and Hevy CSV file, a timezone field/default, an import button, a progress/status area, and a clear import summary after processing finishes.

**[UNCHANGED]** The import still has the same basic goal: read both files, check that the needed data exists, extract the useful records, and store them locally.

**[REVISED] Technical Details**

The app currently imports:

- Apple Health XML export
- Hevy CSV workout export

Apple Health parsing is handled in `health_stream.py`. It uses `xml.etree.ElementTree.iterparse()` so the app can stream through the XML file instead of loading the entire export at once.

Hevy parsing is handled in `parse_workouts.py`. It reads the CSV with `csv.DictReader`, localizes workout timestamps with `zoneinfo`, and converts workout rows into workout and set records.

Data storage is handled in `db.py`. The revised final version uses:

- `workouts`
- `workout_sets`
- `workout_health_summary`
- `daily_health`
- `daily_sleep`
- `apple_workouts`
- `import_meta`

**[REVISED]** I am no longer planning to use CSV cache files as a main storage method. SQLite is the required storage layer for the final version.

**[REVISED] Error Handling**

The final version should give clear messages when:

- A selected file does not exist.
- The Apple Health or Hevy file is not in the expected format.
- The disk is full or SQLite cannot open the database.
- Optional data like sleep, HRV, or VO2 max is missing.
- The import succeeds, but some workouts cannot be matched to health metrics.

### Vignette 2: Matching Workout Logs With Heart-Rate Data

**[UNCHANGED]** FitLens still connects Hevy workouts with Apple Health records from the same time window. For example, if Hevy says a workout started at 5:30 PM and ended at 6:25 PM, FitLens searches Apple Health records during that same window.

**[REVISED]** This matching is now part of the import pipeline in `engine.py` and `health_stream.py`. During import, FitLens sends the workout time windows into the Apple Health streaming parser. The parser accumulates matching Apple Health metrics for each workout and writes summaries to `workout_health_summary`.

Workout-level outputs currently include:

- Average heart rate
- Max heart rate
- Physical effort, when present in Apple Health
- Active energy, when present
- Other workout-window metrics supported by the parser

**[REVISED]** The original spec mentioned time spent in broad heart-rate zones. That is now a stretch goal, not a required final feature. The current recommendation logic uses simpler cardio classification based on workout title keywords, effort, average heart rate, max heart rate, and workout duration.

**[UNCHANGED] Edge Cases**

The app still needs to handle:

- Missing heart-rate data
- Missing optional Apple Health metrics
- Time zone differences
- Multiple workouts on the same day
- Large Apple Health XML exports
- Repeated imports without duplicating the same workouts

### Vignette 3: Generating a Monthly Coaching Report

**Original idea:** The user would run:

```bash
python fitlens.py report --month 2026-06
```

and receive a monthly report.

**[REVISED]** The final class version will not require month-specific report commands. The app now uses menu screens that summarize the latest available data. The main coaching screens are:

- **Coach insights:** a recent training and recovery snapshot
- **Coach recommendations:** latest 30 days compared to the previous 30 days
- **Recovery trends:** 7/30/60/90-day recovery windows
- **Movement balance:** latest 30 days of strength volume by muscle group

**[REVISED]** The app is still basically a monthly coaching check-in tool, but it does not currently export a single polished monthly report file. For the final version, the required output is a desktop GUI that displays the coaching summary clearly. A generated PDF/monthly report can still be a stretch feature after the GUI is working.

**Current Technical Details**

The coaching logic is in `insights.py`.

`coach_recommendations()`:

- Finds the latest imported data date.
- Builds a latest 30-day window.
- Builds the previous 30-day comparison window.
- Calculates training load, strength sets, cardio minutes, Zone 2 minutes, hard cardio minutes, sleep, HRV, resting heart rate, and muscle volume.
- Runs rule-based readiness logic.
- Generates priority recommendations.
- Generates a four-week plan.

**[REVISED]** The recommendation engine will stay rule-based for the class version. AI-generated coaching is a possible future direction, but not required for the final submission.

### Vignette 4: Reviewing Historical Charts and Training Trends

**Original idea:** FitLens would generate charts for workout volume, strength progress, resting heart rate, HRV, VO2 max, consistency, and other trends.

**[REVISED]** This is now part of the Version 2 GUI focus, but with a realistic scope. The final GUI does not need every chart from the original spec, but it should make the trend data easier to understand visually than terminal tables alone.

**[REVISED]** The most realistic final chart/visual features are:

- Weekly training volume
- Sleep or HRV trend
- Resting heart rate trend
- Strength volume by week
- Muscle group balance shown as a readable visual/table hybrid

**[REVISED]** A full commercial-style dashboard, workout consistency calendar, and highly interactive chart system are still out of scope. The goal is a usable desktop GUI with clear views, not a perfect analytics product.

### Vignette 5: Comparing Months and Getting Recommendations Going Forward

**[UNCHANGED]** This is still one of the main goals. FitLens should help answer whether my training is improving, staying consistent, or possibly pushing recovery too hard.

**[REVISED]** The current implementation compares the latest 30 days to the previous 30 days instead of requiring explicit calendar-month selection. This is more practical because the app is based on exported data, and the latest useful window may not line up perfectly with the current calendar month.

The recommendation logic currently checks things like:

- Whether sleep is under 6.5 or 7 hours
- Whether HRV is down compared with the previous window
- Whether resting heart rate is up
- Whether training load increased too quickly
- Whether hard cardio is high while recovery is down
- Whether Zone 2 cardio is low
- Whether strength volume is dropping or ready for a small progression
- Whether muscle balance looks uneven

**[REVISED] Recommendation Categories**

The original spec listed categories like Increase, Maintain, Deload, and Investigate. The actual app now presents recommendations as priority actions instead. Each recommendation has:

- Priority
- Area
- Recommendation title
- Evidence
- Action
- Timeframe

This is more useful in the CLI because it gives me concrete next steps instead of just a broad category.

### Vignette 6: Refreshing Data Over Time

**[UNCHANGED]** The app should stay useful over repeated imports. The user can export fresh Apple Health and Hevy files later and import them into the same local database.

**[REVISED]** The current import system already stores metadata in `import_meta`, including:

- `coverage_start`
- `coverage_start_local`
- `last_ingested_ts`
- `tz_name`
- `last_run`
- `xml_path`
- `csv_path`

The import pipeline uses a small overlap window so recent health and sleep data can settle correctly. It also uses stable IDs and upsert-style database writes to avoid duplicating already-imported data.

**[DEFERRED]** Backup/export of the FitLens database is still a good future feature, but it is not required for the final class version.

## 3. Revised Design / CLI and Desktop GUI Flow

**Original Version 1 CLI Flow**

```bash
python fitlens.py import --apple export.xml --hevy workouts.csv
python fitlens.py report --month 2026-06
python fitlens.py compare --month 2026-06 --against previous
python fitlens.py charts --last 90 --output charts/
python fitlens.py status
```

**[REVISED] Current CLI Flow**

```bash
python fitlens.py
```

The app is guided now. The user does not need to remember subcommands.

Main menu:

- Coach insights
- Coach recommendations
- Movement balance
- Recent workouts
- Weekly training summary
- Recovery trends
- Data coverage
- Import new data
- Quit

**[REVISED] Reason for the change:** I realized that a menu-driven CLI is more usable for this project than a bunch of command flags. I kept forgetting exactly what commands I wanted, and the menu makes the app easier to demo and easier to use repeatedly.

**[REVISED] Version 2 Desktop GUI Flow**

The final version should open as a desktop application instead of requiring the user to live in the terminal.

Planned desktop screens:

- **Import / Setup:** choose Apple Health XML, choose Hevy CSV, pick timezone/history window, run import, and show progress.
- **Dashboard / Overview:** show imported data coverage, latest training range, and quick access to the main views.
- **Coach Insights:** show the latest 7-day training/recovery snapshot in readable panels.
- **Coach Recommendations:** show readiness, priority actions, evidence, and the next four-week plan.
- **Movement Balance:** show latest 30-day muscle-group volume and balance ratios.
- **Recent Workouts:** show a table of recent workouts with duration, sets, volume, average HR, and effort.
- **Weekly Training:** show weekly workload totals and at least one simple visual summary.
- **Recovery Trends:** show 7/30/60/90-day recovery averages and changes.

**[REVISED] GUI technology choice:** The most feasible plan is to build the desktop interface with Python's Tkinter/ttk or CustomTkinter. I will only use a heavier GUI framework if the lighter option blocks something important. The main goal is to reuse the current backend instead of rewriting the project.

## 4. Revised Technical Flow

**Original technical flow:** Apple Health XML and Hevy CSV would be parsed into DataFrames, cleaned, stored locally, matched, summarized, and displayed through CLI or GUI.

**[REVISED] Actual technical flow:**

```text
Apple Health XML         Hevy CSV
      |                     |
      v                     v
health_stream.py       parse_workouts.py
      |                     |
      +----------+----------+
                 |
                 v
             engine.py
     import coordination + matching
                 |
                 v
              db.py
          SQLite storage
                 |
                 v
            insights.py
     queries + summaries + rules
                 |
                 v
            fitlens.py
       guided CLI + rich tables
                 |
                 v
        desktop GUI layer
  Tkinter/ttk or CustomTkinter views
```

**[REVISED] Key implementation decisions**

- Use SQLite as the main storage layer.
- Use streaming XML parsing for Apple Health.
- Keep the guided CLI as the Version 1 fallback interface.
- Add a desktop GUI as the Version 2/final interface.
- Use transparent rule-based recommendations.
- Keep everything local to the user's machine.
- Avoid rewriting the working backend while adding the GUI.

## 5. Revised Feature Scope for Remaining Weeks

The class ends in early August, so the final version needs to be realistic. The revised scope is:

### Required Final Scope

- Desktop GUI startup and navigation.
- GUI file selection for Apple Health XML and Hevy CSV.
- GUI import progress/status and import summary.
- Import Apple Health XML and Hevy CSV.
- Store imported data locally in SQLite.
- Re-import new exports without duplicating old workouts.
- Show recent workouts in the GUI.
- Show weekly training load in the GUI.
- Show recovery trends across 7, 30, 60, and 90 days in the GUI.
- Show coach insights in the GUI.
- Show coach recommendations with evidence and next actions in the GUI.
- Show movement balance by muscle group in the GUI.
- Show data coverage ranges and import status in the GUI.
- Keep the current CLI working as a fallback.
- Include demo data and documentation.
- Include screenshots and final review documents.

### Stretch Goals

- More polished charts and exportable PNGs.
- Better exercise taxonomy coverage.
- More detailed strength progression logic for specific lifts.
- A generated monthly report file.
- GUI theming/polish beyond the basic final interface.

### Not in Final Class Scope

- Web application.
- Live API integrations.
- Machine learning recommendation engine.
- Medical or diagnostic advice.
- A full commercial-style interactive dashboard.
- Cloud sync or accounts.

## 6. Revised Function / Module Plan

**Original idea:** The first spec proposed classes like `AppleHealthParser`, `HevyWorkoutParser`, `LocalDatabase`, `WorkoutHeartRateMatcher`, `HistoricalMetricsCalculator`, `MonthlySummaryGenerator`, `RecommendationEngine`, and `ReportGenerator`.

**[REVISED]** The app ended up using modules and functions instead of a large class hierarchy. This fits the current size of the project better.

Current module responsibilities:

- `fitlens.py`: guided CLI, menu screens, Rich tables, user prompts
- `engine.py`: import workflow, coverage window logic, repeated import handling
- `health_stream.py`: Apple Health XML streaming parser
- `parse_workouts.py`: Hevy CSV parser
- `db.py`: SQLite schema and insert/upsert helpers
- `insights.py`: queries, summaries, recommendations, recovery windows, movement balance
- `taxonomy.py`: exercise-to-muscle classification
- `common.py`: small shared helpers
- planned GUI module: desktop windows/views that call `engine.py` and `insights.py`

**[REVISED]** I am not planning to refactor everything into classes before the final deadline. That would be risky and would not improve the user-facing project enough. Instead, I will add the GUI as a layer on top of the existing modules and only refactor functions when the GUI needs a cleaner return value or display format.

## 7. Revised Milestones for Version 2

### Milestone 1: Submission and Documentation Polish

Finish the Version 1 review, revised project spec, screenshots, and PR description. Make sure the repo has the required docs and that the app can be explained clearly.

### Milestone 2: GUI Shell and Navigation

Create the desktop app window, navigation/sidebar or tabs, and placeholder screens for Import, Overview, Coach Insights, Coach Recommendations, Movement Balance, Recent Workouts, Weekly Training, Recovery Trends, and Data Coverage.

### Milestone 3: GUI Import Flow

Connect the GUI import screen to the existing `engine.ingest()` workflow. Add file pickers, a timezone/default history setting, progress/status text, and a readable import summary.

### Milestone 4: GUI Data Views

Move the existing CLI menu outputs into GUI views by calling the same `insights.py` functions. The first version can use tables and text panels; charts can be added after the views are stable.

### Milestone 5: Import Reliability and Error Handling

Improve error messages and edge-case handling around file paths, missing optional data, SQLite failures, and repeated imports. The app should fail in a way that is understandable instead of dumping a confusing traceback.

### Milestone 6: Recommendation Transparency

Review the rule-based coach recommendations and make sure each one has a clear reason. If the app says to add Zone 2, hold volume, or improve sleep, the screen should show what data caused that recommendation.

### Milestone 7: Movement Balance and Taxonomy Cleanup

Expand and clean up `taxonomy.py` so common exercises are classified correctly. Make unmapped exercises easy to identify and fix.

### Milestone 8: Final Polish and Demo Readiness

Clean up README instructions, verify the demo data works, take final screenshots of the desktop GUI, and make sure the final project is stable on a fresh run.

### Stretch Milestone: Charts or Report Export

If the required GUI scope is done early, add a small chart/export feature or a generated monthly report. This should only happen after the GUI import flow and core views are stable.

## 8. Revised Self-Assessment

**[REVISED]** I am more satisfied with the project now because the core pipeline actually works. FitLens can import real data, store it in SQLite, and show useful summaries. That gives me a much better foundation for building the desktop GUI because I am not trying to solve the interface and data problems at the same time anymore.

**[REVISED]** I do think I can finish the project by early August if I keep the GUI scope focused. The biggest course correction is that the GUI should be a clean wrapper around the existing working features, not a huge new dashboard with every possible chart and interaction. The realistic final version is a local desktop fitness analysis app with a working import flow and clear summary screens.

**[REVISED] Expectations vs. reality**

What was easier than expected:

- Building a guided CLI with `rich` and `questionary`
- Storing structured data in SQLite
- Creating useful table-based summaries once the data was imported

What was harder than expected:

- Apple Health XML exports are huge and awkward to parse
- Matching workout logs to Apple Health data requires careful timestamp logic
- Recommendation logic is harder than just calculating numbers because the advice needs to be fair and explainable
- Building a GUI is still a risk because it adds layout/state work on top of the backend
- System issues like iCloud folder performance and disk space can make debugging confusing

**[REVISED] Light bulb moment**

The main insight I had is that importing data is not the whole project. The real challenge is turning messy exported data into something trustworthy enough to guide decisions. The GUI should make those decisions easier to understand, but it should not hide or replace the backend logic that already works.

## 9. AI Disclosure

**[UNCHANGED]** I use AI tools such as ChatGPT, Claude, and Gemini as a rubber duck for brainstorming, planning, debugging, and writing polish. I still review and adapt the output myself, and I am responsible for understanding the code and the final submitted work.

**[REVISED]** For this revised spec, AI was used to help convert the original PDF plan into a clearer Markdown revision and to help organize my thoughts on original planned vs currently executed and future planned. 
