# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""StepStartRenderer — renders step_start events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class StepStartRenderer(EventRenderer):
    event_types = ("step_start",)

    def render(self, event: dict[str, Any]) -> bool:
        step_type = event.get("part", {}).get("type", "step-start")
        phase = self.context.phase
        label = self.context.label
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(f"[{phase}] {label}: {step_type}", style="cyan"))
        elif self.plain:
            self.sink.write_text(C.info(f"[{phase}] {label}: {step_type}"))
        return True
