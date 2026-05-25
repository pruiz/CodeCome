# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""StepStartRenderer — renders step_start events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class StepStartRenderer(EventRenderer):
    event_types = ("step_start",)

    def __init__(self, context, *, phase: str = "", label: str = ""):
        super().__init__(context)
        self.phase = phase
        self.label = label

    def render(self, event: dict[str, Any]) -> bool:
        step_type = event.get("part", {}).get("type", "step-start")
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(f"[{self.phase}] {self.label}: {step_type}", style="cyan"))
        elif self.plain:
            self.sink.write_text(C.info(f"[{self.phase}] {self.label}: {step_type}"))
        return True
