#!/usr/bin/env python3
"""FitLens desktop entry point."""

from pathlib import Path

import customtkinter as ctk

from desktop.desktop_app import DashboardApp


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "fitlens.db"


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = DashboardApp(DEFAULT_DB)
    app.mainloop()


if __name__ == "__main__":
    main()
