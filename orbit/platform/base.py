"""Platform contracts. Each OS backend implements these; core code depends only on them."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from orbit.core.events import Capability, InputEvent

Emit = Callable[[InputEvent], None]


class InputSource(ABC):
    """Turns some hardware/OS signal into InputEvents. Runs on its own thread(s)."""

    name: str = "source"
    capabilities: frozenset[Capability] = frozenset()

    @abstractmethod
    def start(self, emit: Emit) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @property
    def available(self) -> bool:
        """False when the source cannot run here (missing rights, device absent...)."""
        return True

    def describe(self) -> str:
        return self.name

    def observe(self, ev: InputEvent) -> None:
        """Sees every event from every source (any thread). Lets a source self-check."""


class RotationSource(InputSource):
    """A source whose rotation is borrowed from another OS function (e.g. volume).

    passthrough=True  -> rotation keeps its native effect (volume really changes)
    passthrough=False -> rotation is consumed; the source undoes the side effect.
    """

    @abstractmethod
    def set_passthrough(self, on: bool) -> None: ...

    def set_duck(self, factor: float | None) -> None:
        """Lower the native level by `factor` while the wheel is open; None restores it."""

    def level(self) -> float | None:
        """Current native level 0..1 (for HUD display), if meaningful."""
        return None


class Output(ABC):
    """Everything an action can do to the OS."""

    @abstractmethod
    def keys(self, combo: str) -> None:
        """Tap a combo like 'ctrl+shift+z', 'alt+tab', 'win+h', 'f5'."""

    @abstractmethod
    def key_down(self, key: str) -> None: ...

    @abstractmethod
    def key_up(self, key: str) -> None: ...

    @abstractmethod
    def scroll(self, notches: float, horizontal: bool = False) -> None:
        """Positive = down/right."""

    @abstractmethod
    def media(self, command: str) -> None:
        """play_pause | next | previous | stop, delivered to the real media app."""

    @abstractmethod
    def launch(self, target: str) -> None:
        """Open an app, file or URL."""

    def active_window_title(self) -> str:
        return ""

    def volume_step(self, n: int) -> None:
        """System output volume up / down by n steps (a control in the Volume tool, no buds)."""
        for _ in range(abs(n)):
            self.keys("volumeup" if n > 0 else "volumedown")

    def brightness_get(self) -> float | None:
        """Display brightness 0..100, or None if not controllable. May take ~150 ms."""
        return None

    def brightness_set(self, value: float) -> None:
        """Set display brightness 0..100 (blocking; callers coalesce)."""

    def press_app_button(self, app_title: str, name_pattern: str) -> None:
        """Bring an app forward and press a button in it by accessible name."""

    def center_window(self, title: str) -> None:
        """Move the small foreground window called `title` to the middle of the cursor's screen."""


class Platform(ABC):
    name: str = "unknown"

    @abstractmethod
    def create_sources(self, cfg: dict) -> list[InputSource]: ...

    @abstractmethod
    def create_output(self, cfg: dict) -> Output: ...

    def create_services(self, cfg: dict) -> list:
        """Background helpers with start()/stop() and an `enabled` flag (+ optional
        `toggle_label` for the tray), e.g. hiding the OS volume flyout. Call after create_sources."""
        return []

    def create_key_capture(self, router):
        """Keyboard / media-key / mouse-button hooks feeding `router` (orbit/core/controls.py),
        with start() / stop() / describe(); None where the OS gives no such hook."""
        return None

    def is_elevated(self) -> bool:
        return True

    def relaunch_elevated(self, argv: list[str]) -> bool:
        return False
