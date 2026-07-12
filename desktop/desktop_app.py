"""Application shell for the FitLens desktop UI."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import engine

from .desktop_dashboard import DashboardView
from .desktop_onboarding import OnboardingView
from .desktop_theme import COLORS


class DashboardApp(ctk.CTk):
    """Main window for the dashboard and import screens."""

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = Path(db_path)
        self.main_view = None

        self.title("FitLens")
        self.geometry("1240x860")
        self.minsize(900, 620)
        self.configure(fg_color=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._build_shell()
        self._show_start_view()

    def _build_shell(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(
            self,
            width=224,
            corner_radius=0,
            fg_color=COLORS["sidebar"],
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=24, pady=(28, 34))
        ctk.CTkLabel(
            brand,
            text="FITLENS",
            text_color=COLORS["accent"],
            font=ctk.CTkFont(size=21, weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Personal training intelligence",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        ctk.CTkLabel(
            sidebar,
            text="OVERVIEW",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))

        active = ctk.CTkFrame(sidebar, fg_color=COLORS["accent_dark"], corner_radius=9)
        active.grid(row=2, column=0, sticky="ew", padx=14)
        self.active_section = ctk.CTkLabel(
            active,
            text="  Dashboard",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self.active_section.pack(fill="x", padx=10, pady=9)

        self.sidebar_status = ctk.CTkLabel(
            sidebar,
            text="Loading data...",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            justify="left",
            anchor="sw",
            wraplength=170,
        )
        self.sidebar_status.grid(row=3, column=0, sticky="sw", padx=24, pady=(0, 28))

        self.sidebar_help = ctk.CTkLabel(
            sidebar,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            justify="left",
            anchor="nw",
        )
        self.sidebar_help.grid(row=5, column=0, sticky="sw", padx=24, pady=(0, 28))

        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=(28, 34), pady=(26, 28))
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

    def _show_start_view(self):
        if engine.db_snapshot(str(self.db_path)):
            self.show_dashboard()
        else:
            self.show_onboarding()

    def _clear_main_view(self):
        if self.main_view is not None:
            self.main_view.destroy()
        self.main_view = None

    def show_onboarding(self):
        self._show_import_view(existing_user=False)

    def show_import(self):
        snapshot = engine.db_snapshot(str(self.db_path)) or {}
        self._show_import_view(
            existing_user=True,
            default_timezone=snapshot.get("tz_name"),
        )

    def _show_import_view(self, existing_user: bool, default_timezone: str | None = None):
        self._clear_main_view()
        if existing_user:
            self.active_section.configure(text="  Import Data")
            self.sidebar_status.configure(text="Ready to reconcile new exports")
            self.sidebar_help.configure(
                text=(
                    "Import workflow\n\nChoose the newest Apple Health\n"
                    "XML and Hevy CSV exports.\n\nExisting data stays local."
                )
            )
        else:
            self.active_section.configure(text="  Setup")
            self.sidebar_status.configure(text="Ready for your first import")
            self.sidebar_help.configure(
                text=(
                    "Import workflow\n\nSelect your Apple Health\n"
                    "XML export and Hevy CSV.\n\nYour data stays local."
                )
            )
        self.main_view = OnboardingView(
            self.main_area,
            self.db_path,
            on_complete=self._onboarding_complete,
            existing_user=existing_user,
            default_timezone=default_timezone,
            on_cancel=self.show_dashboard if existing_user else None,
        )
        self.main_view.grid(row=0, column=0, sticky="nsew")

    def show_dashboard(self):
        self._clear_main_view()
        self.active_section.configure(text="  Dashboard")
        self.sidebar_help.configure(
            text=(
                "Import workflow\n\nFor later exports, click\n"
                "Import new data above.\n\nThe CLI is also available:\n"
                "python fitlens.py"
            )
        )
        self.main_view = DashboardView(
            self.main_area,
            self.db_path,
            on_import_requested=self.show_import,
            on_data_loaded=self._update_sidebar,
        )
        self.main_view.grid(row=0, column=0, sticky="nsew")

    def _onboarding_complete(self, report):
        self.show_dashboard()
        self.main_view.set_status(
            f"Import complete — {report.new_workouts:,} workouts, "
            f"{report.new_sets:,} sets, and "
            f"{report.sleep_nights_written:,} sleep nights saved."
        )

    def _update_sidebar(self, data):
        snapshot = data.database
        if not snapshot:
            self.sidebar_status.configure(text="No imported data yet")
            return

        self.sidebar_status.configure(
            text=(
                f"{snapshot['workouts']:,} workouts\n"
                f"{snapshot['days']:,} health days\n"
                f"{snapshot['nights']:,} sleep nights"
            )
        )
