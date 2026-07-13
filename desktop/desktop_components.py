"""Reusable visual components shared by the desktop screens."""

from __future__ import annotations

import sys

import customtkinter as ctk

from desktop.desktop_theme import COLORS


class DashboardCard(ctk.CTkFrame):
    """A rounded card with a heading and content body."""

    def __init__(self, master, title: str, subtitle: str | None = None):
        super().__init__(
            master,
            fg_color=COLORS["card"],
            border_width=1,
            border_color=COLORS["card_border"],
            corner_radius=16,
        )
        self.full_width = False
        self.grid_columnconfigure(0, weight=1)

        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 0))
        heading.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            heading,
            text=title,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        if subtitle:
            ctk.CTkLabel(
                heading,
                text=subtitle,
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(14, 20))
        self.body.grid_columnconfigure(0, weight=1)

    def show_empty(self, message: str):
        ctk.CTkLabel(
            self.body,
            text=message,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
            wraplength=340,
        ).grid(row=0, column=0, sticky="w", pady=(6, 6))


class MetricRow(ctk.CTkFrame):
    """A label/value row with an optional colored change marker."""

    def __init__(
        self,
        master,
        label: str,
        value: str,
        suffix: str | None = None,
        suffix_color: str | None = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=label,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            self,
            text=value,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        if suffix:
            ctk.CTkLabel(
                self,
                text=suffix,
                text_color=suffix_color or COLORS["accent"],
                font=ctk.CTkFont(size=12 if len(suffix) > 1 else 17, weight="bold"),
                width=68 if len(suffix) > 1 else 25,
                anchor="e",
            ).grid(row=0, column=2, sticky="e", padx=(8, 0))


class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """A scrollable frame that eases wheel movement instead of jumping. (Added smooth scrolling from my testing)"""

    def __init__(self, *args, **kwargs):
        self._smooth_target_x = None
        self._smooth_target_y = None
        self._smooth_job = None
        super().__init__(*args, **kwargs)

    def _mouse_wheel_all(self, event):
        if not self._check_if_valid_scroll(event.widget):
            return

        direction = self._wheel_direction(event)
        if direction == 0:
            return


        canvas = self._parent_canvas
        if self._shift_pressed:
            self._queue_scroll(canvas, "x", direction)
        else:
            self._queue_scroll(canvas, "y", direction)

    def _wheel_direction(self, event) -> int:
        if sys.platform.startswith("win") or sys.platform == "darwin":
            if not event.delta:
                return 0
            return -1 if event.delta > 0 else 1
        return -1 if event.num == 4 else 1

    def _queue_scroll(self, canvas, axis: str, direction: int):
        if axis == "x":
            region = canvas.bbox("all")
            viewport = canvas.winfo_width()
            start = canvas.xview()[0]
            target = self._smooth_target_x
        else:
            region = canvas.bbox("all")
            viewport = canvas.winfo_height()
            start = canvas.yview()[0]
            target = self._smooth_target_y

        if not region:
            return

        content_size = region[2] - region[0] if axis == "x" else region[3] - region[1]
        scrollable_size = content_size - viewport
        if scrollable_size <= 0:
            return

        current_offset = (target * scrollable_size) if target is not None else start * scrollable_size
        distance = 72 if sys.platform == "darwin" else 96
        target_offset = max(0.0, min(scrollable_size, current_offset + direction * distance))
        target_fraction = target_offset / scrollable_size

        if axis == "x":
            self._smooth_target_x = target_fraction
        else:
            self._smooth_target_y = target_fraction

        if self._smooth_job is None:
            self._smooth_job = self.after(8, self._animate_scroll)

    def _animate_scroll(self):
        canvas = self._parent_canvas
        region = canvas.bbox("all")
        if not region:
            self._smooth_job = None
            return

        finished = True
        for axis, target in (("x", self._smooth_target_x), ("y", self._smooth_target_y)):
            if target is None:
                continue

            if axis == "x":
                current = canvas.xview()[0]
                viewport = canvas.winfo_width()
                content_size = region[2] - region[0]
            else:
                current = canvas.yview()[0]
                viewport = canvas.winfo_height()
                content_size = region[3] - region[1]

            scrollable_size = content_size - viewport
            if scrollable_size <= 0:
                continue

            next_position = current + (target - current) * 0.28
            if abs(target - current) < 0.002:
                next_position = target
            else:
                finished = False

            if axis == "x":
                canvas.xview_moveto(next_position)
            else:
                canvas.yview_moveto(next_position)

        if finished:
            self._smooth_job = None
        else:
            self._smooth_job = self.after(8, self._animate_scroll)

    def destroy(self):
        if self._smooth_job is not None:
            self.after_cancel(self._smooth_job)
            self._smooth_job = None
        super().destroy()
