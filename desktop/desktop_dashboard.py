"""The monthly coaching dashboard view."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from desktop.desktop_components import DashboardCard, MetricRow, SmoothScrollableFrame
from desktop.desktop_data import DashboardData
from desktop.desktop_formatting import (
    format_change_style,
    format_date,
    format_minutes,
    format_number,
    format_volume,
    readiness_colors,
    trend_style,
)
from desktop.desktop_theme import COLORS


class DashboardView(ctk.CTkFrame):
    """Owns the dashboard header, responsive card grid, and refresh behavior."""

    def __init__(
        self,
        master,
        db_path: Path,
        on_import_requested: Callable[[], None],
        on_data_loaded: Callable[[DashboardData], None],
    ):
        super().__init__(master, fg_color="transparent")
        self.db_path = Path(db_path)
        self.on_import_requested = on_import_requested
        self.on_data_loaded = on_data_loaded
        self.card_columns = 0
        self.cards: list[DashboardCard] = []

        self._build_shell()
        self.bind("<Configure>", self._window_changed)
        self.refresh()

    def _build_shell(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Dashboard",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=29, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="A monthly coaching view of training load, recovery, and next steps.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        self.import_button = ctk.CTkButton(
            header,
            text="Import new data",
            width=140,
            height=34,
            corner_radius=8,
            fg_color=COLORS["accent_dark"],
            hover_color="#28615C",
            text_color=COLORS["text"],
            command=self.on_import_requested,
        )
        self.import_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 10))

        self.refresh_button = ctk.CTkButton(
            header,
            text="Refresh",
            width=100,
            height=34,
            corner_radius=8,
            fg_color=COLORS["accent_dark"],
            hover_color="#28615C",
            text_color=COLORS["text"],
            command=self.refresh,
        )
        self.refresh_button.grid(row=0, column=2, rowspan=2, sticky="e")

        self.window_label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.window_label.grid(row=1, column=0, sticky="ew", pady=(22, 12))

        self.card_grid = SmoothScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
        )
        self.card_grid.grid(row=2, column=0, sticky="nsew")
        for column in range(3):
            self.card_grid.grid_columnconfigure(column, weight=1)

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.status_label.grid(row=3, column=0, sticky="ew", pady=(10, 0))

    def _window_changed(self, event):
        if event.widget is not self or event.width <= 0 or not hasattr(self, "card_grid"):
            return
        columns = 3 if event.width >= 900 else 2
        if columns != self.card_columns:
            self.card_columns = columns
            self._arrange_cards()

    def _arrange_cards(self):
        if not self.card_columns:
            self.card_columns = 3 if self.winfo_width() >= 900 else 2

        row = 0
        column = 0
        for card in self.cards:
            full_width = getattr(card, "full_width", False)
            if full_width:
                if column:
                    row += 1
                column = 0
                column_span = self.card_columns
            else:
                if column >= self.card_columns:
                    row += 1
                    column = 0
                column_span = 1

            card.grid(
                row=row,
                column=column,
                columnspan=column_span,
                sticky="nsew",
                padx=6,
                pady=6,
            )

            if full_width:
                row += 1
                column = 0
            else:
                column += column_span

        for column in range(self.card_columns):
            self.card_grid.grid_columnconfigure(column, weight=1)

    def _clear_card_grid(self):
        for child in self.card_grid.winfo_children():
            child.destroy()
        self.cards = []
        self.card_columns = 0

    def refresh(self):
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.status_label.configure(text="Refreshing dashboard...")
        self.update_idletasks()
        try:
            data = DashboardData.load(self.db_path)
            if not data.database:
                self._show_load_error(
                    RuntimeError(
                        "No imported workouts were found. Use Import new data "
                        "to add an export pair."
                    )
                )
                return

            self._render_cards(data)
            self._update_context(data)
            self.on_data_loaded(data)
            self.set_status("Updated")
        except Exception as error:
            self._show_load_error(error)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def set_status(self, message: str):
        self.status_label.configure(text=message)

    def _render_cards(self, data: DashboardData):
        self._clear_card_grid()
        self.cards = [
            self._monthly_status_card(data.recommendations),
            self._month_card(data.recommendations),
            self._recovery_card(data.recovery),
            self._plan_card(data.recommendations),
            self._recommendations_card(data.recommendations),
        ]
        self._arrange_cards()

    def _update_context(self, data: DashboardData):
        latest = data.recommendations.get("latest_date")
        if latest:
            self.window_label.configure(
                text=(
                    f"Coaching window ends {format_date(latest)} · "
                    "latest 30 days vs prior 30 days"
                )
            )
        else:
            self.window_label.configure(text="No imported data yet")

    def _show_load_error(self, error: Exception):
        self._clear_card_grid()
        error_card = DashboardCard(self.card_grid, "Dashboard unavailable")
        error_card.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        error_card.show_empty(f"FitLens could not read the database.\n\n{error}")
        self.set_status("Refresh failed. Check the database and try again.")

    def _monthly_status_card(self, data: dict) -> DashboardCard:
        card = DashboardCard(
            self.card_grid,
            "Monthly Coaching Status",
            "Latest 30 days vs prior 30 days",
        )
        readiness = data.get("readiness")
        if not readiness:
            card.show_empty("Import data to get a monthly coaching status.")
            return card

        foreground, background = readiness_colors(readiness)
        ctk.CTkLabel(
            card.body,
            text=readiness.upper(),
            text_color=foreground,
            fg_color=background,
            corner_radius=9,
            font=ctk.CTkFont(size=14, weight="bold"),
            padx=14,
            pady=6,
        ).grid(row=0, column=0, sticky="w")

        reasons = data.get("readiness_reasons") or ["No explanation was returned."]
        ctk.CTkLabel(
            card.body,
            text=reasons[0].capitalize(),
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
            wraplength=340,
        ).grid(row=1, column=0, sticky="w", pady=(16, 0))

        window = data.get("current_window")
        if window:
            ctk.CTkLabel(
                card.body,
                text=f"Window: {format_date(window[0])} – {format_date(window[1])}",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).grid(row=2, column=0, sticky="w", pady=(12, 0))
        return card

    def _month_card(self, data: dict) -> DashboardCard:
        card = DashboardCard(
            self.card_grid,
            "This Month",
            "Latest 30 days vs prior 30 days",
        )
        current = data.get("current")
        previous = data.get("previous")
        if not current or not previous or not data.get("latest_date"):
            card.show_empty("Import data to see this month's training load.")
            return card

        values = (
            ("Workouts", format_number(current.get("workouts")), "workouts"),
            ("Strength sets", format_number(current.get("strength_sets")), "strength_sets"),
            ("Volume", format_volume(current.get("volume_lbs")), "volume_lbs"),
            ("Training time", format_minutes(current.get("duration_min")), "duration_min"),
            ("Cardio", format_minutes(current.get("cardio_min")), "cardio_min"),
            ("Zone 2", format_minutes(current.get("zone2_min")), "zone2_min"),
        )
        for row, (label, value, key) in enumerate(values):
            change_text, change_color = format_change_style(
                current.get(key),
                previous.get(key),
            )
            self._add_metric(
                card.body,
                row,
                label,
                value,
                change_text,
                change_color,
            )
        return card

    def _recovery_card(self, data: dict) -> DashboardCard:
        card = DashboardCard(
            self.card_grid,
            "Recovery Snapshot",
            "30-day averages vs prior 30 days",
        )
        if not data.get("latest_date"):
            card.show_empty("Import Apple Health data to see recovery trends.")
            return card

        sleep = data["sleep"]
        metrics = data["metrics"]
        rows = (
            (
                "Sleep",
                format_minutes(sleep.get("asleep_min_30")),
                sleep.get("asleep_change_30_pct"),
                False,
            ),
            (
                "HRV",
                format_number(metrics["HeartRateVariabilitySDNN"].get("avg_30"), 1, " ms"),
                metrics["HeartRateVariabilitySDNN"].get("change_30_pct"),
                False,
            ),
            (
                "Resting HR",
                format_number(metrics["RestingHeartRate"].get("avg_30"), 1, " bpm"),
                metrics["RestingHeartRate"].get("change_30_pct"),
                True,
            ),
        )
        for row, (label, value, change, lower_is_better) in enumerate(rows):
            arrow, arrow_color = trend_style(change, lower_is_better=lower_is_better)
            self._add_metric(card.body, row, label, value, arrow, arrow_color)
        return card

    def _recommendations_card(self, data: dict) -> DashboardCard:
        card = DashboardCard(
            self.card_grid,
            "Priority Actions",
            "From Coach Recommendations",
        )
        card.full_width = True
        card.body.grid_columnconfigure(0, weight=1)
        card.body.grid_columnconfigure(1, weight=1)
        recommendations = data.get("recommendations") or []
        if not recommendations:
            card.show_empty("Import more data to generate coaching actions.")
            return card

        for index, recommendation in enumerate(recommendations):
            row, column = divmod(index, 2)
            action = ctk.CTkFrame(card.body, fg_color="transparent")
            action.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 10, 10 if column == 0 else 0),
                pady=(0 if row == 0 else 12, 0),
            )
            action.grid_columnconfigure(0, weight=1)
            priority = recommendation.get("priority", "").upper()
            area = recommendation.get("area", "").title()
            ctk.CTkLabel(
                action,
                text=f"{priority} · {area}",
                text_color=COLORS["accent"],
                font=ctk.CTkFont(size=10, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(
                action,
                text=recommendation.get("title", "Recommendation"),
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
                wraplength=280,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(3, 0))
            ctk.CTkLabel(
                action,
                text=recommendation.get("action", ""),
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=11),
                anchor="w",
                wraplength=280,
                justify="left",
            ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        return card

    def _plan_card(self, data: dict) -> DashboardCard:
        card = DashboardCard(
            self.card_grid,
            "Next 4 Weeks",
            "Monthly plan from Coach Recommendations",
        )
        card.full_width = True
        plan = data.get("monthly_plan") or []
        if not plan:
            card.show_empty("Import more data to build the four-week plan.")
            return card

        for row, week in enumerate(plan[:4]):
            block = ctk.CTkFrame(card.body, fg_color="transparent")
            block.grid(
                row=row,
                column=0,
                sticky="ew",
                pady=(0 if row == 0 else 9, 0),
            )
            block.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                block,
                text=week.get("week", f"Week {row + 1}"),
                text_color=COLORS["accent"],
                font=ctk.CTkFont(size=11, weight="bold"),
                width=56,
                anchor="w",
            ).grid(row=0, column=0, sticky="nw", padx=(0, 10))
            summary = (
                f"{week.get('lifting', '')} · {week.get('cardio', '')} · "
                f"{week.get('recovery', '')}"
            )
            ctk.CTkLabel(
                block,
                text=summary,
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=11),
                anchor="w",
                wraplength=610,
                justify="left",
            ).grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(
                block,
                text=week.get("progression", ""),
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=10),
                anchor="w",
                wraplength=610,
                justify="left",
            ).grid(row=1, column=1, sticky="w", pady=(2, 0))
        return card

    @staticmethod
    def _add_metric(parent, row, label, value, suffix=None, suffix_color=None):
        metric = MetricRow(parent, label, value, suffix, suffix_color)
        metric.grid(row=row, column=0, sticky="ew", pady=3)
