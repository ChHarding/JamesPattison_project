"""Data objects used by the desktop views."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import engine
import insights


@dataclass(frozen=True)
class DashboardData:
    """The monthly coaching slice needed by the dashboard."""

    recommendations: dict
    recovery: dict
    database: dict | None

    @classmethod
    def load(cls, db_path: Path) -> "DashboardData":
        recommendations = insights.coach_recommendations(str(db_path))
        recovery = insights.recovery_summary(str(db_path))

        return cls(
            recommendations=recommendations,
            recovery=recovery,
            database=engine.db_snapshot(str(db_path)),
        )
