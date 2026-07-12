"""First-run import view for the FitLens desktop application."""

from __future__ import annotations

from pathlib import Path
import queue
import threading
from tkinter import StringVar, filedialog
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import customtkinter as ctk
import engine

from .desktop_components import DashboardCard
from .desktop_formatting import detect_local_timezone
from .desktop_theme import COLORS, LOOKBACK_CHOICES


DOWNLOADS = Path.home() / "Downloads"


class OnboardingView(ctk.CTkFrame):
    """Collect export paths and import them without freezing the UI."""

    def __init__(
        self,
        master,
        db_path: Path,
        on_complete: Callable,
        existing_user: bool = False,
        default_timezone: str | None = None,
        on_cancel: Callable | None = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.db_path = Path(db_path)
        self.on_complete = on_complete
        self.existing_user = existing_user
        self.default_timezone = default_timezone
        self.on_cancel = on_cancel
        self.import_queue = queue.Queue()
        self.import_thread: threading.Thread | None = None
        self.controls: list = []

        self._build()

    def _build(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title = "Import new data" if self.existing_user else "Welcome to FitLens"
        subtitle = (
            "Reconcile your latest exports with the existing FitLens database."
            if self.existing_user
            else "Bring your training and Apple Health exports together in one place."
        )
        ctk.CTkLabel(
            self,
            text=title,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=29, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            self,
            text=subtitle,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        card_title = "Add the latest exports" if self.existing_user else "Import your data"
        card_subtitle = (
            "FitLens will reconcile these files with the data already in your database."
            if self.existing_user
            else "You only need to do this once to build your local FitLens database."
        )
        card = DashboardCard(
            self,
            card_title,
            card_subtitle,
        )
        card.grid(row=2, column=0, sticky="nsew", pady=(22, 0))
        card.body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card.body,
            text=(
                "FitLens uses the existing import watermark to add only new records, "
                "then returns you to the dashboard."
                if self.existing_user
                else "FitLens reads the two exports on this computer, matches your "
                "workouts with Apple Health metrics, and then opens the dashboard."
            ),
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
            wraplength=680,
        ).grid(row=0, column=0, sticky="w", pady=(0, 20))

        self.xml_path_var = StringVar(value=self._default_export("export.xml"))
        self.csv_path_var = StringVar(value=self._default_export("workouts.csv"))
        self.timezone_var = StringVar(
            value=self.default_timezone or detect_local_timezone()
        )
        self.lookback_var = StringVar(value="Past year (recommended)")

        self._file_picker_row(
            card.body,
            row=1,
            label="Apple Health export",
            variable=self.xml_path_var,
            button_text="Choose XML",
            filetypes=(("Apple Health XML", "*.xml"), ("All files", "*.*")),
        )
        self._file_picker_row(
            card.body,
            row=2,
            label="Hevy workout export",
            variable=self.csv_path_var,
            button_text="Choose CSV",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )

        timezone_entry = self._form_row(card.body, 3, "Timezone", self.timezone_var)
        self.controls.append(timezone_entry)

        if not self.existing_user:
            history_row = ctk.CTkFrame(card.body, fg_color="transparent")
            history_row.grid(row=4, column=0, sticky="ew", pady=6)
            history_row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                history_row,
                text="History to import",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(0, 20))
            self.lookback_menu = ctk.CTkOptionMenu(
                history_row,
                variable=self.lookback_var,
                values=list(LOOKBACK_CHOICES),
                width=240,
                fg_color=COLORS["accent_dark"],
                button_color=COLORS["accent_dark"],
                button_hover_color="#28615C",
            )
            self.lookback_menu.grid(row=0, column=1, sticky="w")
            self.controls.append(self.lookback_menu)

        status_row = 4 if self.existing_user else 5
        button_row = status_row + 1

        self.status_label = ctk.CTkLabel(
            card.body,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w",
            wraplength=680,
        )
        self.status_label.grid(row=status_row, column=0, sticky="w", pady=(16, 8))

        actions = ctk.CTkFrame(card.body, fg_color="transparent")
        actions.grid(row=button_row, column=0, sticky="w", pady=(4, 0))
        self.import_button = ctk.CTkButton(
            actions,
            text=(
                "Import new data and refresh dashboard"
                if self.existing_user
                else "Import data and open dashboard"
            ),
            height=40,
            width=250,
            corner_radius=9,
            fg_color=COLORS["accent_dark"],
            hover_color="#28615C",
            text_color=COLORS["text"],
            command=self.start_import,
        )
        self.import_button.grid(row=0, column=0, sticky="w")
        self.controls.append(self.import_button)

        if self.existing_user and self.on_cancel:
            cancel_button = ctk.CTkButton(
                actions,
                text="Cancel",
                height=40,
                width=90,
                fg_color="transparent",
                border_width=1,
                border_color=COLORS["card_border"],
                hover_color=COLORS["card_border"],
                text_color=COLORS["muted"],
                command=self.on_cancel,
            )
            cancel_button.grid(row=0, column=1, sticky="w", padx=(10, 0))
            self.controls.append(cancel_button)

    @staticmethod
    def _default_export(filename: str) -> str:
        path = DOWNLOADS / filename
        return str(path) if path.is_file() else ""

    def _file_picker_row(self, parent, row, label, variable, button_text, filetypes):
        form_row = ctk.CTkFrame(parent, fg_color="transparent")
        form_row.grid(row=row, column=0, sticky="ew", pady=6)
        form_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            form_row,
            text=label,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
            width=140,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))
        entry = ctk.CTkEntry(
            form_row,
            textvariable=variable,
            height=36,
            border_color=COLORS["card_border"],
        )
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        button = ctk.CTkButton(
            form_row,
            text=button_text,
            width=105,
            height=36,
            command=lambda: self._choose_file(variable, label, filetypes),
        )
        button.grid(row=0, column=2, sticky="e")
        self.controls.extend((entry, button))

    @staticmethod
    def _form_row(parent, row, label, variable):
        form_row = ctk.CTkFrame(parent, fg_color="transparent")
        form_row.grid(row=row, column=0, sticky="ew", pady=6)
        form_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            form_row,
            text=label,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
            width=140,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))
        entry = ctk.CTkEntry(
            form_row,
            textvariable=variable,
            height=36,
            border_color=COLORS["card_border"],
        )
        entry.grid(row=0, column=1, sticky="ew")
        return entry

    @staticmethod
    def _choose_file(variable, label, filetypes):
        path = filedialog.askopenfilename(title=f"Choose {label}", filetypes=filetypes)
        if path:
            variable.set(path)

    def start_import(self):
        xml_path = Path(self.xml_path_var.get().strip().strip('"').strip("'"))
        csv_path = Path(self.csv_path_var.get().strip().strip('"').strip("'"))
        timezone = self.timezone_var.get().strip()
        lookback_kind, lookback_value = LOOKBACK_CHOICES[self.lookback_var.get()]

        if not xml_path.is_file():
            self._set_error("Choose a valid Apple Health XML export first.")
            return
        if not csv_path.is_file():
            self._set_error("Choose a valid Hevy CSV export first.")
            return
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            self._set_error(f"I couldn't find the timezone '{timezone}'.")
            return

        self._set_controls("disabled")
        self.status_label.configure(
            text="Starting import... Apple Health exports can take a little while to scan.",
            text_color=COLORS["accent"],
        )
        self.import_thread = threading.Thread(
            target=self._run_import,
            args=(xml_path, csv_path, timezone, lookback_kind, lookback_value),
            daemon=True,
        )
        self.import_thread.start()
        self.after(100, self._poll_import_queue)

    def _run_import(self, xml_path, csv_path, timezone, lookback_kind, lookback_value):
        kwargs = {"tz_name": timezone}
        if lookback_kind == "all":
            kwargs["all_history"] = True
        else:
            kwargs["lookback_days"] = lookback_value

        try:
            report = engine.ingest(
                str(xml_path),
                str(csv_path),
                str(self.db_path),
                progress=lambda count: self.import_queue.put(("progress", count)),
                **kwargs,
            )
            self.import_queue.put(("complete", report))
        except Exception as error:
            self.import_queue.put(("error", error))

    def _poll_import_queue(self):
        try:
            event, value = self.import_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_import_queue)
            return

        if event == "progress":
            self.status_label.configure(
                text=f"Reading Apple Health export... {value:,} records scanned.",
                text_color=COLORS["accent"],
            )
            self.after(100, self._poll_import_queue)
            return

        if event == "error":
            self._set_error(f"The import could not finish:\n{value}")
            self._set_controls("normal")
            self.import_thread = None
            return

        self.import_thread = None
        self.on_complete(value)

    def _set_controls(self, state: str):
        for control in self.controls:
            control.configure(state=state)

    def _set_error(self, message: str):
        self.status_label.configure(text=message, text_color=COLORS["red"])
