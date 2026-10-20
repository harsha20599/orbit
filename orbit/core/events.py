"""Normalized input events.

Every input source (volume watcher, media session, ETW sniffer, a future
firmware-level press/release decoder, a macOS backend...) translates whatever
the hardware gives it into these events. The engine only ever sees these.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    ROTATE = "rotate"    # delta: +n clockwise, -n counter-clockwise (detents)
    CLICK = "click"      # firmware-decoded single press
    DOUBLE = "double"    # firmware-decoded double press
    TRIPLE = "triple"    # firmware-decoded triple press
    HOLD = "hold"        # firmware-decoded long press (no release info)
    PRESS = "press"      # raw button down  (future: needs press/release decoding)
    RELEASE = "release"  # raw button up    (future)
    ACTION = "action"    # a control asked for a specific function (InputEvent.action)


class Capability(str, Enum):
    """What a source can deliver. The engine adapts its gesture model to these."""
    ROTATE = "rotate"
    CLICKS = "clicks"            # click / double / triple
    HOLD = "hold"
    PRESS_RELEASE = "press_release"


@dataclass(frozen=True)
class InputEvent:
    kind: Kind
    delta: int = 0
    source: str = ""
    t: float = field(default_factory=time.monotonic)
    action: str | None = None          # set by controls (orbit/core/controls.py)

    def __str__(self):
        what = self.action if self.action else self.kind.value
        return f"{what}{'' if not self.delta else f'({self.delta:+d})'} <{self.source}>"
