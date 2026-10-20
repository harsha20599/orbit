"""Settings window (Windows + macOS): the controls (which trigger does which function),
which tools are on the wheel and in what order, and the tool Orbit starts on.

Left: a live preview of the wheel, redrawn as items are switched or reordered.
Right: grouped lists of native controls. Writes orbit.core.settings
(settings.json); config.toml is never rewritten.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QUrl,
                            QVariantAnimation, Property)
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QKeySequence, QPainter, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSlider, QToolButton, QVBoxLayout, QWidget)

import uuid

from orbit.core import settings as st
from orbit.core import shortcuts as keys_mod
from orbit.core import tools as tools_mod
from orbit.ui import assets

# Same world as the overlay: near-black blue-tinted glass, one periwinkle accent.
CANVAS = "#101217"
PANEL = "#151820"
GROUP = "#1A1D25"
HAIR = "#262A34"
INK = "#F2F4F8"
INK2 = "#A4AAB8"
INK3 = "#6E7483"
WARN = "#F2B46B"

GESTURE_NAMES = {"click": "Press", "double": "Double press", "triple": "Triple press", "hold": "Press and hold"}
PRESETS = [
    ("Open the wheel", st.OPEN_WHEEL),
    ("Play / pause", "media:play_pause"),
    ("Next track", "media:next"),
    ("Previous track", "media:previous"),
    ("Back to previous tool", "last_tool"),
    ("Open an app…", "launch:"),
    ("Nothing", "none"),
]
OPEN_APP = "launch:"
MAX_ITEMS = 12
APPEARANCES = [("Match system", "system"), ("Dark", "dark"), ("Light", "light")]


def _summary(act) -> str:
    text = " → ".join(str(a) for a in act) if isinstance(act, list) else str(act)
    return text if len(text) <= 34 else text[:33] + "…"


def _icon(name: str, color: str) -> QIcon:
    url = assets.tinted_url(name, color)
    return QIcon(QUrl(url).toLocalFile()) if url else QIcon()


def _font(px: float, weight=QFont.Normal) -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    f.setPixelSize(round(px))
    f.setWeight(weight)
    return f


# ---------------------------------------------------------------- controls
class ToggleSwitch(QAbstractButton):
    """Yes/No switch with a sliding knob (Space toggles it when focused)."""

    def __init__(self, accent: str, checked: bool, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._accent = QColor(accent)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(40, 24)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(2, 2, self.width() - 4, self.height() - 4)
        off, on = QColor("#343946"), self._accent
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        if self.hasFocus():
            p.setPen(QPen(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 120), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), r.height() / 2 + 1.5, r.height() / 2 + 1.5)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * t
        p.setBrush(QColor("#FFFFFF") if t > 0.5 else QColor("#C9CDD6"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class GesturePips(QWidget):
    """How the gesture feels on the dial: one, two or three taps, or one long press."""

    def __init__(self, gesture: str, color: str):
        super().__init__()
        self.g = gesture
        self.c = QColor(color)
        self.setFixedSize(28, 16)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.c)
        cy = self.height() / 2
        if self.g == "hold":
            p.drawRoundedRect(QRectF(2, cy - 3, 22, 6), 3, 3)
            return
        n = {"click": 1, "double": 2, "triple": 3}[self.g]
        for i in range(n):
            p.drawEllipse(QPointF(5 + i * 8, cy), 3, 3)


class WheelPreview(QWidget):
    """The wheel as the overlay draws it: enabled items around the ring, the start
    tool lit. Items glide to their new places when the list changes."""

    def __init__(self, accent: str):
        super().__init__()
        self.accent = QColor(accent)
        self.items: list[tuple[str, str, str]] = []      # (id, label, icon)
        self.start = ""
        self.dark = True
        self._from: dict[str, float] = {}
        self._to: dict[str, float] = {}
        self._t = 1.0
        self._pix: dict[tuple[str, str], QIcon] = {}
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=420)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._step)
        self.setMinimumSize(290, 290)

    def _step(self, v):
        self._t = v
        self.update()

    def set_items(self, items, start: str):
        n = max(len(items), 1)
        cur = self._angles()
        self._from = {i[0]: cur.get(i[0], k * 360 / n) for k, i in enumerate(items)}
        self._to = {i[0]: k * 360 / n for k, i in enumerate(items)}
        self.items, self.start = list(items), start
        self._t = 0.0
        self._anim.stop()
        self._anim.start()

    def set_look(self, dark: bool):
        self.dark = dark
        self.update()

    def _angles(self) -> dict[str, float]:
        out = {}
        for tid in self._to:
            a, b = self._from.get(tid, self._to[tid]), self._to[tid]
            d = (b - a + 540) % 360 - 180                     # shortest way round
            out[tid] = a + d * self._t
        return out

    def _glyph(self, icon: str, color: str) -> QIcon:
        key = (icon, color)
        if key not in self._pix:
            self._pix[key] = _icon(icon, color)
        return self._pix[key]

    def _draw_icon(self, p: QPainter, icon: str, color: str, centre: QPointF, size: int = 20):
        # QIcon.paint renders at the screen's real pixel density; drawing a pixmap made for
        # it scaled it twice on Retina (Mac screenshot: icons ~2x, over the centre text)
        self._glyph(icon, color).paint(p, int(centre.x() - size / 2), int(centre.y() - size / 2), size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 60
        c = QPointF(self.width() / 2, self.height() / 2)
        R = side / 2
        dark = self.dark
        acc = QColor(self.accent) if dark else QColor(self.accent).darker(132)
        ink, ink2 = (QColor(INK), QColor(INK2)) if dark else (QColor("#12141A"), QColor("#6B7080"))

        def a(alpha):
            return QColor(acc.red(), acc.green(), acc.blue(), max(0, min(255, int(255 * alpha))))

        ang = self._angles()
        orbit_r = R * 0.68
        lit_a = ang.get(self.start)
        lp = None if lit_a is None else QPointF(c.x() + orbit_r * math.sin(math.radians(lit_a)),
                                                c.y() - orbit_r * math.cos(math.radians(lit_a)))
        k = 1.0 if dark else 0.8
        # shadow, then light spilling past the rim (drawn under the disc)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90 if dark else 36))
        p.drawEllipse(c + QPointF(0, 6), R, R)
        if lp is not None:
            g = QRadialGradient(lp, R * 0.84)
            for pos, al in ((0, 0.30), (0.18, 0.20), (0.40, 0.07), (0.70, 0.015), (1, 0)):
                g.setColorAt(pos, a(al * k))
            p.setBrush(g)
            p.drawEllipse(c, R + 26, R + 26)
        p.setBrush(QColor(10, 11, 15, 248) if dark else QColor(251, 251, 254, 248))
        p.setPen(QPen(QColor(255, 255, 255, 18) if dark else QColor(0, 0, 0, 20), 1))
        p.drawEllipse(c, R, R)
        if lp is not None:                                     # light across the disc
            g = QRadialGradient(lp, R * 1.24)
            for pos, al in ((0, 0.34), (0.08, 0.24), (0.20, 0.12), (0.38, 0.05), (0.60, 0.015), (1, 0)):
                g.setColorAt(pos, a(al * k))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, R - 1, R - 1)
            for span, al in ((2.0, 0.10), (1.1, 0.25), (0.5, 0.55)):    # the rim catching it
                p.setPen(QPen(a(al * k), 1.5, Qt.SolidLine, Qt.FlatCap))
                sp = 16 * min(360 / max(len(self.items), 1) * 1.1, 96) * span
                p.drawArc(QRectF(c.x() - R + 1, c.y() - R + 1, 2 * R - 2, 2 * R - 2), int((90 - lit_a) * 16 - sp / 2), int(sp))
        rim = R - 12
        p.setPen(QPen(QColor(ink.red(), ink.green(), ink.blue(), 16), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, rim, rim)
        for tid, label, icon in self.items:
            ia = math.radians(ang.get(tid, 0))
            pos = QPointF(c.x() + orbit_r * math.sin(ia), c.y() - orbit_r * math.cos(ia))
            lit = tid == self.start
            col = (QColor("#FFFFFF") if dark else acc) if lit else ink2
            self._draw_icon(p, icon, col.name(), pos)
        p.setPen(ink)
        p.setFont(_font(17, QFont.DemiBold))
        name = next((lbl for t, lbl, _ in self.items if t == self.start), "")
        p.drawText(QRectF(c.x() - 80, c.y() - 22, 160, 24), Qt.AlignCenter, name or "-")
        p.setPen(ink2)
        p.setFont(_font(12))
        n = len(self.items)
        p.drawText(QRectF(c.x() - 80, c.y() + 2, 160, 20), Qt.AlignCenter,
                   f"{n} item{'s' if n != 1 else ''} · starts here" if name else f"{n} items")


class _Group(QFrame):
    """One rounded list with hairline separators between rows."""

    def __init__(self):
        super().__init__()
        self.setObjectName("group")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(0)

    def rows(self) -> list[QWidget]:
        return [self.box.itemAt(i).widget() for i in range(self.box.count())]

    def restyle(self):
        rows = [r for r in self.rows() if r is not None]
        for i, r in enumerate(rows):
            r.setProperty("last", i == len(rows) - 1)
            r.style().unpolish(r)
            r.style().polish(r)


class _ToolRow(QFrame):
    def __init__(self, win: "SettingsWindow", tid: str, label: str, icon: str, sticky: bool, on: bool):
        super().__init__()
        self.tid, self.icon_name = tid, icon
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 8, 14, 8)
        h.setSpacing(10)
        for name, d, tip in (("chevron_up", -1, "Move up"), ("chevron_down", 1, "Move down")):
            b = QToolButton()
            b.setObjectName("move")
            b.setIcon(_icon(name, INK2))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, d=d: win.move(self.tid, d))
            h.addWidget(b)
        self.ic = QLabel()
        self.ic.setFixedSize(22, 22)
        h.addSpacing(4)
        h.addWidget(self.ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = QLabel(label)
        self.name.setFont(_font(14, QFont.DemiBold))
        col.addWidget(self.name)
        if not sticky:
            kind = QLabel("Runs once")
            kind.setObjectName("meta")
            col.addWidget(kind)
        h.addLayout(col, 1)
        self.state = QLabel()
        self.state.setObjectName("meta2")
        self.state.setFixedWidth(28)
        self.state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.state)
        self.switch = ToggleSwitch(win.accent, on)
        self.switch.setToolTip(f"Show {label} on the wheel")
        h.addWidget(self.switch)
        self.switch.toggled.connect(lambda _: (self._sync(), win.changed()))
        self._sync()

    def _sync(self):
        on = self.switch.isChecked()
        self.state.setText("Yes" if on else "No")
        self.name.setStyleSheet(f"color: {INK if on else INK3};")
        self.ic.setPixmap(_icon(self.icon_name, INK if on else INK3).pixmap(20, 20))


class _ComboRow(QFrame):
    def __init__(self, lead: QWidget | None, label: str, box: QComboBox):
        super().__init__()
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 8, 10, 8)
        h.setSpacing(12)
        if lead is not None:
            h.addWidget(lead)
        lab = QLabel(label)
        lab.setFont(_font(14, QFont.DemiBold))
        h.addWidget(lab, 1)
        box.setFixedWidth(250)
        h.addWidget(box)


class KeyField(QLineEdit):
    """A key combo field: press a chord (with Ctrl / Alt / Cmd / Win, or an F-key) to
    record it, or type it ("win+shift+s": the OS grabs some Win combos before any app
    sees them). Holds Orbit's combo format."""

    _RECORD_ALWAYS = {Qt.Key_Print, Qt.Key_Insert, Qt.Key_Pause, Qt.Key_ScrollLock} | {
        getattr(Qt, f"Key_F{i}") for i in range(1, 25)}
    _MODIFIERS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr}

    def __init__(self, combo: str, on_change: Callable[[], None]):
        super().__init__(combo)
        self.on_change = on_change
        self.setPlaceholderText("Press keys or type, e.g. ctrl+shift+s")
        self.setToolTip("Press the shortcut to record it, or type it")
        self.setFixedWidth(250)
        self.editingFinished.connect(self._tidy)
        self.textEdited.connect(lambda _: self.on_change())

    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        chord = mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
        if k in self._MODIFIERS:
            return
        if chord or k in self._RECORD_ALWAYS:
            seq = QKeySequence(e.keyCombination()).toString(QKeySequence.PortableText)
            combo = keys_mod.from_qt(seq)
            if combo:
                self.setText(combo)
                self.on_change()
            return
        super().keyPressEvent(e)

    def _tidy(self):
        t = "+".join(p.strip().lower() for p in self.text().split("+") if p.strip())
        if t != self.text():
            self.setText(t)
            self.on_change()

    def combo(self) -> str:
        return "+".join(p.strip().lower() for p in self.text().split("+") if p.strip())


class _ShortcutRow(QFrame):
    def __init__(self, win: "SettingsWindow", sc: dict):
        super().__init__()
        self.sid = sc["id"]
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 8, 8, 8)
        h.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(_icon("keyboard", INK2).pixmap(18, 18))
        ic.setFixedWidth(22)
        h.addWidget(ic)
        self.label = QLineEdit(sc.get("label", ""))
        self.label.setPlaceholderText("Name on the wheel")
        self.label.setObjectName("plain")
        self.label.textEdited.connect(lambda _: win.shortcut_renamed(self.sid))
        h.addWidget(self.label, 1)
        self.keys = KeyField(sc.get("keys", ""), lambda: win.changed())
        h.addWidget(self.keys)
        rm = QToolButton()
        rm.setObjectName("move")
        rm.setIcon(_icon("x", INK2))
        rm.setIconSize(QSize(16, 16))
        rm.setToolTip("Remove this shortcut")
        rm.setCursor(Qt.PointingHandCursor)
        rm.clicked.connect(lambda: win.remove_shortcut(self.sid))
        h.addWidget(rm)

    def value(self) -> dict:
        return {"id": self.sid, "label": self.label.text().strip() or "Shortcut", "keys": self.keys.combo()}


class _SliderRow(QFrame):
    """A labelled slider with its value shown (e.g. "3.5×")."""

    def __init__(self, label: str, hint: str, lo: float, hi: float, step: float, value: float,
                 fmt: Callable[[float], str], on_change: Callable[[], None]):
        super().__init__()
        self.setObjectName("row")
        self.step, self.fmt = step, fmt
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(14)
        col = QVBoxLayout()
        col.setSpacing(1)
        lab = QLabel(label)
        lab.setFont(_font(14, QFont.DemiBold))
        col.addWidget(lab)
        sub = QLabel(hint)
        sub.setObjectName("meta")
        col.addWidget(sub)
        h.addLayout(col, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(round(lo / step), round(hi / step))
        self.slider.setValue(round(value / step))
        self.slider.setFixedWidth(190)
        self.slider.setCursor(Qt.PointingHandCursor)
        h.addWidget(self.slider)
        self.val = QLabel()
        self.val.setObjectName("meta2")
        self.val.setFixedWidth(56)
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.val)
        self.slider.valueChanged.connect(lambda _: (self._sync(), on_change()))
        self._sync()

    def _sync(self):
        self.val.setText(self.fmt(self.value()))

    def value(self) -> float:
        return round(self.slider.value() * self.step, 2)


class _AppRow(QFrame):
    """Shown under a gesture set to "Open an app…": which app."""

    def __init__(self, name: str, on_change: Callable[[], None]):
        super().__init__()
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(56, 4, 10, 10)
        h.setSpacing(12)
        lab = QLabel("App to open")
        lab.setObjectName("meta2")
        h.addWidget(lab, 1)
        self.edit = QLineEdit(name)
        self.edit.setPlaceholderText("e.g. Spotify, DaVinci Resolve")
        self.edit.setToolTip("The app's name as in the Start menu / Applications folder, or a path")
        self.edit.setFixedWidth(250)
        self.edit.textEdited.connect(lambda _: on_change())
        h.addWidget(self.edit)


# ---------------------------------------------------------------- window
class SettingsWindow(QWidget):
    """`base_cfg`: config.toml merged for this platform, without settings.json.
    `on_save(settings)` is called with the new settings (already written to disk)."""

    def __init__(self, base_cfg: dict, current: dict, has_hold: bool, accent: str,
                 on_save: Callable[[dict], None], settings_path: Path | None = None, router=None,
                 first_run_setup: bool = False):
        super().__init__()
        self.current = current
        self.onboarded = bool(current.get("onboarded"))
        self.router = router
        self.base = base_cfg
        self.accent = accent
        self.on_save = on_save
        self.settings_path = settings_path
        self.has_hold = has_hold
        merged = st.apply(base_cfg, current)
        self.tools = {tid: tools_mod.build(tid, tc) for tid, tc in merged["tools"].items()}
        self.order, enabled = st.wheel_order(merged)

        self.setWindowTitle("Orbit settings")
        self.resize(900, 680)
        self.setMinimumSize(780, 520)
        self.setFont(_font(13))
        self.setStyleSheet(self._qss())

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- left: the wheel, live
        left = QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(320)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(28, 30, 28, 24)
        lv.setSpacing(6)
        title = QLabel("Orbit")
        title.setFont(_font(22, QFont.Bold))
        lv.addWidget(title)
        sub = QLabel("Your dial, your wheel.")
        sub.setObjectName("meta2")
        lv.addWidget(sub)
        lv.addSpacing(18)
        self.preview = WheelPreview(accent)
        lv.addWidget(self.preview, 0, Qt.AlignHCenter)
        lv.addSpacing(14)
        self.how = QLabel()
        self.how.setObjectName("meta2")
        self.how.setWordWrap(True)
        self.how.setAlignment(Qt.AlignHCenter)
        lv.addWidget(self.how)
        lv.addStretch(1)
        reset = QPushButton("  Reset to config")
        reset.setObjectName("quiet")
        reset.setIcon(_icon("rotate_ccw", INK2))
        reset.setIconSize(QSize(14, 14))
        reset.setCursor(Qt.PointingHandCursor)
        reset.setToolTip("Forget these choices and use config.toml as written")
        reset.clicked.connect(self.reset)
        lv.addWidget(reset, 0, Qt.AlignLeft)
        root.addWidget(left)

        # ---- right: the lists
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("body")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(32, 30, 32, 24)
        v.setSpacing(0)

        from orbit.core.controls import Controls
        from orbit.ui.controls_ui import ControlsSection
        v.addWidget(self._heading("Controls"))
        v.addSpacing(4)
        self.controls_sec = ControlsSection(Controls.from_json(current.get("controls")), router, has_hold,
                                            lambda: self.changed(), _Group, persist=self.apply_now,
                                            on_setup=self.run_setup)
        if first_run_setup and not self.onboarded:
            QTimer.singleShot(350, self.run_setup)
        v.addWidget(self.controls_sec)
        self._capture_poll = QTimer(self)                 # capture only while this window (or its dialog) is in front
        self._capture_poll.setInterval(200)
        self._capture_poll.timeout.connect(self._sync_capture)
        self._capture_poll.start()

        v.addSpacing(34)
        v.addWidget(self._heading("Wheel items"))
        v.addSpacing(4)
        v.addWidget(self._help("Switch on what the wheel shows. The order runs clockwise from the top."))
        v.addSpacing(14)
        self.items_group = _Group()
        self.rows: dict[str, _ToolRow] = {}
        for tid in self.order:
            t = self.tools[tid]
            row = _ToolRow(self, tid, t.label, t.icon, t.sticky, tid in set(enabled))
            self.rows[tid] = row
            self.items_group.box.addWidget(row)
        self.items_group.restyle()
        v.addWidget(self.items_group)

        v.addSpacing(34)
        v.addWidget(self._heading("Shortcuts"))
        v.addSpacing(4)
        v.addWidget(self._help("Wheel items that press a key combo. Pick one on the wheel and press the dial "
                               "to send it to the app you're in."))
        v.addSpacing(14)
        self.sc_group = _Group()
        self.sc_rows: dict[str, _ShortcutRow] = {}
        for sc in current.get("shortcuts") or []:
            if sc.get("id"):
                self._add_shortcut_row(sc)
        add = QPushButton("  Add shortcut")
        add.setObjectName("quiet")
        add.setIcon(_icon("plus", INK2))
        add.setIconSize(QSize(14, 14))
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.add_shortcut)
        self.sc_group.box.addWidget(add, 0, Qt.AlignLeft)
        self.sc_group.restyle()
        v.addWidget(self.sc_group)

        v.addSpacing(34)
        v.addWidget(self._heading("Look"))
        v.addSpacing(4)
        v.addWidget(self._help("The highlighted item lights up the wheel around it."))
        v.addSpacing(14)
        look = _Group()
        self.appearance_box = self._combo()
        for lbl, val in APPEARANCES:
            self.appearance_box.addItem(lbl, val)
        self.appearance_box.setCurrentIndex(max(0, self.appearance_box.findData(merged["ui"].get("appearance", "dark"))))
        self.appearance_box.currentIndexChanged.connect(lambda _: self.changed())
        lead = QLabel()
        lead.setPixmap(_icon("brightness", INK2).pixmap(16, 16))
        lead.setFixedWidth(28)
        look.box.addWidget(_ComboRow(lead, "Appearance", self.appearance_box))
        look.restyle()
        v.addWidget(look)

        v.addSpacing(34)
        v.addWidget(self._heading("Start"))
        v.addSpacing(4)
        v.addWidget(self._help("The tool Orbit starts on, before you pick one from the wheel."))
        v.addSpacing(14)
        dial = _Group()
        self.start = self._combo()
        for tid in self.order:
            if self.tools[tid].sticky:
                self.start.addItem(_icon(self.tools[tid].icon, INK2), self.tools[tid].label, tid)
        self.start.setCurrentIndex(max(0, self.start.findData(merged.get("default_tool", self.order[0]))))
        self.start.currentIndexChanged.connect(lambda _: self.changed())
        lead = QLabel()
        lead.setPixmap(_icon("star", INK2).pixmap(16, 16))
        lead.setFixedWidth(28)
        dial.box.addWidget(_ComboRow(lead, "Start with", self.start))
        dial.restyle()
        v.addWidget(dial)

        v.addSpacing(34)
        v.addWidget(self._heading("Scroll"))
        v.addSpacing(4)
        v.addWidget(self._help("How the Scroll tool feels on this computer. Apps scroll different distances "
                               "per notch on Windows and macOS, so this is saved per computer."))
        v.addSpacing(14)
        scroll_grp = _Group()
        sc_cfg = merged["tools"].get("scroll", {})
        self.fast_scroll = _SliderRow("Fast-turn speed", "How much further a quick turn goes", 1.0, 8.0, 0.5,
                                      float(sc_cfg.get("max_gain", 3.5)), lambda x: f"{x:g}×", lambda: self.changed())
        self.click_scroll = _SliderRow("Distance per click", "One careful click, in mouse-wheel notches", 0.25, 3.0,
                                       0.25, float(sc_cfg.get("notches_per_detent", 1.0)),
                                       lambda x: f"{x:g} notch" + ("" if x == 1 else "es"), lambda: self.changed())
        scroll_grp.box.addWidget(self.fast_scroll)
        scroll_grp.box.addWidget(self.click_scroll)
        scroll_grp.restyle()
        v.addWidget(scroll_grp)
        base_sc = base_cfg["tools"].get("scroll", {})
        self._scroll_defaults = (float(base_sc.get("max_gain", 3.5)), float(base_sc.get("notches_per_detent", 1.0)))
        sreset = QPushButton("  Reset scroll to defaults")
        sreset.setObjectName("quiet")
        sreset.setIcon(_icon("rotate_ccw", INK2))
        sreset.setIconSize(QSize(14, 14))
        sreset.setCursor(Qt.PointingHandCursor)
        sreset.clicked.connect(self.reset_scroll)
        v.addSpacing(6)
        v.addWidget(sreset, 0, Qt.AlignLeft)

        v.addSpacing(10)
        self.note = QLabel()
        self.note.setObjectName("warn")
        self.note.setWordWrap(True)
        v.addWidget(self.note)
        v.addStretch(1)
        right.addWidget(scroll, 1)

        bar_frame = QFrame()
        bar_frame.setObjectName("bar")
        bar = QHBoxLayout(bar_frame)
        bar.setContentsMargins(32, 14, 32, 16)
        bar.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.close)
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        bar.addWidget(cancel)
        bar.addSpacing(8)
        bar.addWidget(self.save_btn)
        right.addWidget(bar_frame)
        root.addLayout(right, 1)
        self.changed()

    # ------------------------------------------------------------------ building
    @staticmethod
    def _heading(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setFont(_font(17, QFont.DemiBold))
        return lab

    @staticmethod
    def _help(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("meta2")
        lab.setWordWrap(True)
        return lab

    @staticmethod
    def _combo() -> QComboBox:
        box = QComboBox()
        box.setCursor(Qt.PointingHandCursor)
        box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        box.setMinimumContentsLength(16)
        box.setIconSize(QSize(16, 16))
        return box

    def _gesture_box(self, g: str, from_config, current) -> QComboBox:
        box = self._combo()
        values = [v for _, v in PRESETS]
        if from_config not in values:
            steps = len(from_config) if isinstance(from_config, list) else 1
            if "claude_shortcut" in (from_config if isinstance(from_config, list) else [from_config]):
                name = "Open Claude dictation"
            else:
                name = "Your config's action" + (f" · {steps} steps" if steps > 1 else "")
            box.addItem(name, from_config)
            box.setItemData(box.count() - 1, _summary(from_config) if not isinstance(from_config, list)
                            else "\n".join(map(str, from_config)), Qt.ToolTipRole)
        for label, val in PRESETS:
            box.addItem(label, val)
        box.insertSeparator(box.count())
        for tid in self.order:
            if self.tools[tid].sticky:
                box.addItem(_icon(self.tools[tid].icon, INK2), f"Switch to {self.tools[tid].label}", f"tool:{tid}")
        if isinstance(current, str) and current.startswith(OPEN_APP):
            current = OPEN_APP                     # the app's name lives in the row below
        if box.findData(current) < 0:
            box.insertItem(0, f"Custom: {_summary(current)}", current)
        box.setCurrentIndex(max(0, box.findData(current)))
        if g == "hold" and not self.has_hold:
            box.setEnabled(False)
        return box

    def move(self, tid: str, d: int):
        i = self.order.index(tid)
        j = i + d
        if not 0 <= j < len(self.order):
            return
        self.order[i], self.order[j] = self.order[j], self.order[i]
        for k, t in enumerate(self.order):
            self.items_group.box.insertWidget(k, self.rows[t])
        self.items_group.restyle()
        self.changed()

    def _add_shortcut_row(self, sc: dict) -> _ShortcutRow:
        row = _ShortcutRow(self, sc)
        self.sc_rows[sc["id"]] = row
        self.sc_group.box.insertWidget(len(self.sc_rows) - 1, row)
        return row

    def add_shortcut(self):
        sc = {"id": uuid.uuid4().hex[:6], "label": "Shortcut", "keys": ""}
        row = self._add_shortcut_row(sc)
        self.sc_group.restyle()
        tid = st.shortcut_tool_id(sc["id"])
        self.tools[tid] = tools_mod.build(tid, st.shortcut_tool({**sc, "keys": "none"}))
        self.order.append(tid)
        t = self.tools[tid]
        self.rows[tid] = _ToolRow(self, tid, t.label, t.icon, t.sticky, True)
        self.items_group.box.addWidget(self.rows[tid])
        self.items_group.restyle()
        row.label.setFocus()
        row.label.selectAll()
        self.changed()

    def shortcut_renamed(self, sid: str):
        tid = st.shortcut_tool_id(sid)
        name = self.sc_rows[sid].value()["label"]
        if tid in self.tools:
            self.tools[tid].label = name
            self.rows[tid].name.setText(name)
        self.changed()

    def remove_shortcut(self, sid: str):
        row = self.sc_rows.pop(sid)
        row.setParent(None)
        row.deleteLater()
        tid = st.shortcut_tool_id(sid)
        if tid in self.rows:
            self.rows.pop(tid).setParent(None)
            self.order.remove(tid)
            self.tools.pop(tid, None)
        self.sc_group.restyle()
        self.items_group.restyle()
        self.changed()

    # ------------------------------------------------------------------ state
    def collect(self) -> dict:
        enabled = [t for t in self.order if self.rows[t].switch.isChecked()]
        return {
            "wheel": {"order": list(self.order), "enabled": enabled},
            "default_tool": self.start.currentData(),
            "appearance": self.appearance_box.currentData(),
            "controls": self.controls_sec.controls.to_json(),
            "scroll": {"max_gain": self.fast_scroll.value(), "notches_per_detent": self.click_scroll.value()},
            **({"claude_shortcut": self.current["claude_shortcut"]} if self.current.get("claude_shortcut") else {}),
            "shortcuts": [r.value() for r in self.sc_rows.values()],
            **({"onboarded": True} if self.onboarded else {}),
            **({"gestures": self.current["gestures"]} if self.current.get("gestures") else {}),
        }

    def _sync_capture(self):
        from PySide6.QtWidgets import QApplication
        dlg = self.controls_sec.dialog
        front = QApplication.activeWindow()
        self.controls_sec.capture_on(self.isVisible() and front is not None and (front is self or front is dlg))

    def closeEvent(self, e):
        self._capture_poll.stop()
        self.controls_sec.capture_on(False)
        super().closeEvent(e)

    def changed(self):
        if not hasattr(self, "controls_sec") or not hasattr(self, "start"):
            return
        s = self.collect()
        on = s["wheel"]["enabled"]
        self.preview.set_items([(t, self.tools[t].label, self.tools[t].icon) for t in on], s["default_tool"])
        hints = QGuiApplication.styleHints()
        system_dark = not hasattr(hints, "colorScheme") or hints.colorScheme() != Qt.ColorScheme.Light
        a = s["appearance"]
        self.preview.set_look(system_dark if a == "system" else a == "dark")
        from orbit.core import controls as ctl
        c = self.controls_sec.controls
        opens = [t.label() for t in c.triggers(ctl.OPEN)]
        self.how.setText(("Open it with " + " or ".join(opens) + "." if opens else "Nothing opens it yet.") +
                         "\nThen Next / Previous to pick, Select to choose.")
        problems = []
        if not on:
            problems.append("Switch on at least one item.")
        if len(on) > MAX_ITEMS:
            problems.append(f"{len(on)} items is too many to pick by feel. Keep it to {MAX_ITEMS} or fewer; 8 reads best.")
        problems += self.controls_sec.problems()
        blank = [sc["label"] for sc in s["shortcuts"] if not sc["keys"]]
        if blank:
            problems.append("Set the keys for: " + ", ".join(blank) + " (shortcuts without keys aren't saved).")
        self.note.setText("\n".join(problems))
        self.note.setVisible(bool(problems))
        self.save_btn.setEnabled(0 < len(on) <= MAX_ITEMS)

    def save(self):
        self.apply_now()
        self.close()

    def apply_now(self):
        """Save and apply everything shown, keeping the window open (a control's Save and close)."""
        s = self.collect()
        st.save(s, self.settings_path)
        self.on_save(s)
        self.current = s

    def reset_scroll(self):
        gain, notches = self._scroll_defaults
        self.fast_scroll.slider.setValue(round(gain / self.fast_scroll.step))
        self.click_scroll.slider.setValue(round(notches / self.click_scroll.step))

    def run_setup(self):
        from orbit.ui.controls_ui import OnboardingDialog
        d = OnboardingDialog(self)
        self._setup_dialog = d
        ok = d.exec()
        self._setup_dialog = None
        if ok and d.result_controls is not None:
            self.controls_sec.set_controls(d.result_controls)
        self.onboarded = True                      # asked once; "Run setup again" is always there
        self.apply_now()

    def reset(self):
        st.save({}, self.settings_path)
        self.on_save({})
        self.close()

    def _qss(self) -> str:
        a = self.accent
        return f"""
        QWidget {{ background: {CANVAS}; color: {INK}; }}
        QFrame#panel {{ background: {PANEL}; border-right: 1px solid {HAIR}; }}
        QFrame#panel QLabel, QFrame#panel QPushButton {{ background: transparent; }}
        QScrollArea, #body {{ background: {CANVAS}; }}
        QLabel#meta {{ color: {INK3}; font-size: 12px; background: transparent; }}
        QLabel#meta2 {{ color: {INK2}; font-size: 13px; background: transparent; }}
        QLabel#warn {{ color: {WARN}; font-size: 13px; background: transparent; }}
        QFrame#group {{ background: {GROUP}; border: 1px solid {HAIR}; border-radius: 12px; }}
        QFrame#row {{ background: transparent; border: none; border-bottom: 1px solid {HAIR}; }}
        QFrame#row[last="true"] {{ border-bottom: none; }}
        QFrame#row QLabel, QFrame#row QSlider {{ background: transparent; }}
        QToolButton#move {{ background: transparent; border: none; border-radius: 6px; padding: 3px; }}
        QToolButton#move:hover {{ background: #262A34; }}
        QToolButton#move:focus {{ border: 1px solid {a}; }}
        QLineEdit {{ background: #20242D; border: 1px solid #2D323D; border-radius: 8px; padding: 6px 10px;
                     font-size: 13px; selection-background-color: {a}; selection-color: #0B0D12; }}
        QLineEdit:focus {{ border-color: {a}; }}
        QLineEdit#plain {{ background: transparent; border: 1px solid transparent; font-weight: 600; font-size: 14px; }}
        QLineEdit#plain:hover {{ border-color: #2D323D; }}
        QLineEdit#plain:focus {{ border-color: {a}; background: #20242D; }}
        QSlider::groove:horizontal {{ height: 4px; background: #2D323D; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {a}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: #FFFFFF; width: 16px; height: 16px; margin: -6px 0;
                                      border-radius: 8px; }}
        QSlider::handle:horizontal:hover {{ background: #E8ECFF; }}
        QComboBox {{ background: #20242D; border: 1px solid #2D323D; border-radius: 8px;
                     padding: 6px 10px; font-size: 13px; }}
        QComboBox:hover {{ border-color: #3B4150; }}
        QComboBox:focus {{ border-color: {a}; }}
        QComboBox:disabled {{ color: {INK3}; background: transparent; border-color: {HAIR}; }}
        QComboBox::drop-down {{ border: none; width: 26px; }}
        QComboBox::down-arrow {{ image: url("{QUrl(assets.tinted_url("chevron_down", INK2)).toLocalFile()}");
                                 width: 14px; height: 14px; }}
        QComboBox QAbstractItemView {{ background: #20242D; border: 1px solid #2D323D; padding: 4px;
                                       selection-background-color: {a}; selection-color: #0B0D12;
                                       outline: none; }}
        QPushButton {{ background: #20242D; border: 1px solid #2D323D; border-radius: 8px;
                       padding: 8px 18px; font-size: 13px; }}
        QPushButton:hover {{ border-color: #3B4150; }}
        QPushButton:focus {{ border-color: {a}; }}
        QPushButton#primary {{ background: {a}; color: #0B0D12; border: 1px solid {a}; font-weight: 600; }}
        QPushButton#primary:hover {{ background: #91ACFF; }}
        QPushButton#primary:disabled {{ background: #2A2F3A; border-color: #2A2F3A; color: {INK3}; }}
        QPushButton#quiet {{ background: transparent; border: none; color: {INK2}; padding: 6px 4px; }}
        QPushButton#quiet:hover {{ color: {INK}; }}
        QFrame#bar {{ background: {CANVAS}; border-top: 1px solid {HAIR}; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
        QScrollBar::handle:vertical {{ background: #2D323D; border-radius: 3px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: #3B4150; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        QToolTip {{ background: #20242D; color: {INK}; border: 1px solid #2D323D; padding: 4px 8px; }}
        """
