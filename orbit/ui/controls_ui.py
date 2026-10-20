"""Settings window: Controls. Which trigger does which function (orbit/core/controls.py).

Mirrors the Android app's Setup controls:
  - the functions (Single press / Select, Open menu, Previous, Next, plus added ones),
    each with its triggers in green and a Change button; Load preset (asks first when
    something is set), Reset (clears every trigger), Run setup again
  - while the window is in front, every input Orbit hears is shown ("Last heard") and
    lights up its function, and nothing acts (the router's capture)
  - Change opens one function: Choose (categories you open, or search; then tap /
    double / triple / hold) or Record (press it the way you'll use it); Save and close
    saves it straight away
"""
from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QRadioButton, QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from orbit.core import controls as ctl
from orbit.core.controls import Controls, ControlsHub, Press, PressRecognizer, Presets, Trigger

GREEN = "#3DDC97"
INK2 = "#A4AAB8"
INK3 = "#6E7483"
WARN = "#F2B46B"


def catalog(platform: str | None = None) -> list[tuple[str, str, list[str]]]:
    """(category, what it covers, inputs) for this OS."""
    mac = (platform or sys.platform) == "darwin"
    mod = "cmd" if mac else "ctrl"
    pad = (["touchpad:swipe-left", "touchpad:swipe-right", "touchpad:swipe-up", "touchpad:swipe-down",
            "touchpad:pinch-in", "touchpad:pinch-out", "touchpad:rotate-left", "touchpad:rotate-right",
            "touchpad:smart-zoom"] if mac else
           [f"touchpad:{n}-swipe-{d}" for n in (3, 4) for d in ("left", "right", "up", "down")] +
           ["touchpad:3-tap", "touchpad:4-tap"])
    return [
        ("Earbuds & the CMF dial", "Press, double, triple, hold; turning the dial",
         ["media:play", "media:next", "media:prev", "media:hold", "vol:up", "vol:down"]),
        ("Volume & media keys", "A keyboard's volume knob, media keys, remotes",
         ["key:volumeup", "key:volumedown", "key:mute", "key:playpause", "key:nexttrack", "key:prevtrack"]),
        ("Mouse buttons", "The side buttons and the middle button",
         ["mouse:back", "mouse:forward", "mouse:middle"]),
        ("Scroll + a key", "Hold a key and scroll",
         [f"scroll:{m}+{d}" for m in (mod, "alt", "shift") for d in ("up", "down")]),
        ("Trackpad gestures", "Pinch, rotate, swipe" if mac else "Three- and four-finger swipes and taps", pad),
        ("Keyboard keys", "Spare keys, arrows, Page up / down. For any other key or a shortcut: Record",
         [f"key:f{i}" for i in range(13, 25)] +
         ["key:pageup", "key:pagedown", "key:up", "key:down", "key:left", "key:right", "key:space", "key:enter"]),
    ]


TRACKPAD_NOTE = {
    "win32": "Windows runs its own three- and four-finger gestures too. To use them only for Orbit, set them to "
             "“Nothing” in Settings → Bluetooth & devices → Touchpad.",
    "darwin": "Swipes reach Orbit when System Settings → Trackpad → More Gestures → Swipe between pages is set "
              "to three fingers.",
}


class _Bridge(QObject):
    """Hook / source threads -> the Qt thread."""
    got = Signal(object)


def _font(px: float, weight=QFont.Normal) -> QFont:
    from orbit.ui.settings_window import _font as f
    return f(px, weight)


def triggers_text(ts: list[Trigger]) -> str:
    return "  or  ".join(t.label() for t in ts) if ts else "Not set"


def _mark(lab: QLabel, on: bool):
    """A small, quiet set / not-set mark."""
    lab.setText("✓" if on else "")
    lab.setStyleSheet(f"color: {GREEN}; border: 1px solid {GREEN}; border-radius: 8px; font-size: 10px;" if on
                      else f"border: 1px solid #4A5060; border-radius: 8px;")


def _confirm(parent, title: str, text: str, ok: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(ok, QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes


class _Card(QPushButton):
    """A checkable card: bold title, dim second line (accordion headers, onboarding choices)."""

    def __init__(self, title: str, sub: str, chevron: bool = False):
        super().__init__()
        self.setObjectName("card")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(10)
        self.chev = QLabel("▸") if chevron else None
        if self.chev:
            self.chev.setFixedWidth(12)
            self.chev.setStyleSheet(f"color: {INK2}; background: transparent;")
            h.addWidget(self.chev)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.t = QLabel(title)
        self.t.setFont(_font(14, QFont.DemiBold))
        self.t.setStyleSheet("background: transparent;")
        self.s = QLabel(sub)
        self.s.setWordWrap(True)
        self.s.setStyleSheet(f"color: {INK2}; background: transparent;")
        col.addWidget(self.t)
        col.addWidget(self.s)
        h.addLayout(col, 1)
        for w in (self.t, self.s, *([self.chev] if self.chev else [])):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.toggled.connect(lambda on: self.chev and self.chev.setText("▾" if on else "▸"))

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


CARD_QSS = """
    QPushButton#card { text-align: left; border: 1px solid #262A34; border-radius: 12px;
                       background: #1A1D25; padding: 0; }
    QPushButton#card:hover { border-color: #3A4050; }
    QPushButton#card:checked { border: 2px solid #7C9CFF; background: rgba(124,156,255,0.10); }
"""


class _FunctionRow(QFrame):
    def __init__(self, label: str, on_change: Callable[[], None]):
        super().__init__()
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 10, 12, 10)
        h.setSpacing(12)
        self.mark = QLabel()
        self.mark.setFixedSize(16, 16)
        self.mark.setAlignment(Qt.AlignCenter)
        h.addWidget(self.mark)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = QLabel(label)
        self.name.setFont(_font(14, QFont.DemiBold))
        col.addWidget(self.name)
        self.trig = QLabel()
        self.trig.setWordWrap(True)
        col.addWidget(self.trig)
        h.addLayout(col, 1)
        self.btn = QPushButton("Change")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(on_change)
        h.addWidget(self.btn)
        self._lit = False

    def show_triggers(self, ts: list[Trigger]):
        self.trig.setText(triggers_text(ts))
        self.trig.setStyleSheet(f"color: {GREEN if ts else INK3};")
        _mark(self.mark, bool(ts))

    def light(self, on: bool):
        if on != self._lit:
            self._lit = on
            self.setStyleSheet("QFrame#row { background: rgba(124,156,255,0.16); }" if on else "")


class ControlsSection(QWidget):
    """The Controls group of the Settings window. `controls` is the draft; `changed`
    is called on every edit; `persist` saves the window's settings now (Save and close)."""

    def __init__(self, controls: Controls, router, has_hold: bool, changed: Callable[[], None], group_cls,
                 persist: Callable[[], None] | None = None, on_setup: Callable[[], None] | None = None):
        super().__init__()
        self.controls = controls
        self.router = router
        self.has_hold = has_hold
        self.changed = changed
        self.persist = persist or (lambda: None)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)

        top = QHBoxLayout()
        self.help = QLabel("What opens the menu, moves and selects. Mix earbuds, keys, a knob, the mouse, "
                           "the trackpad.")
        self.help.setObjectName("meta2")
        self.help.setWordWrap(True)
        top.addWidget(self.help, 1)
        self.preset_btn = QToolButton()
        self.preset_btn.setText("Load preset  ▾")
        self.preset_btn.setCursor(Qt.PointingHandCursor)
        self.preset_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.preset_btn)
        for p in Presets.here():
            a = menu.addAction(p.name)
            a.setToolTip(p.about)
            a.triggered.connect(lambda _=False, p=p: self.load_preset(p))
        self.preset_btn.setMenu(menu)
        top.addWidget(self.preset_btn)
        self.reset_btn = QToolButton()
        self.reset_btn.setText("Reset")
        self.reset_btn.setToolTip("Remove every trigger")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self.reset)
        top.addWidget(self.reset_btn)
        if on_setup:
            setup = QToolButton()
            setup.setText("Run setup again")
            setup.setCursor(Qt.PointingHandCursor)
            setup.clicked.connect(on_setup)
            top.addWidget(setup)
        self.v.addLayout(top)
        self.v.addSpacing(14)

        self.group = group_cls()
        self.v.addWidget(self.group)
        self.heard = QLabel()
        self.heard.setObjectName("meta")
        self.heard.setWordWrap(True)
        self.v.addSpacing(8)
        self.v.addWidget(self.heard)

        self.rows: dict[str, _FunctionRow] = {}
        self._lit: tuple[str, float] | None = None
        self.bridge = _Bridge()
        self.bridge.got.connect(self.on_captured, Qt.QueuedConnection)
        self.preview = ControlsHub(self.bridge.got.emit)
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.dialog: FunctionDialog | None = None
        self.rebuild()
        self.show_heard(None)

    # ---------------------------------------------------------------- building
    def rebuild(self):
        for r in self.group.rows():
            if r is not None:
                r.setParent(None)
        self.rows.clear()
        for a in self.controls.actions:
            row = _FunctionRow(ctl.action_label(a), lambda _=False, a=a: self.edit(a))
            row.show_triggers(self.controls.triggers(a))
            self.rows[a] = row
            self.group.box.addWidget(row)
        add = QPushButton("  Add a function")
        add.setObjectName("quiet")
        add.setCursor(Qt.PointingHandCursor)
        m = QMenu(add)
        for a in ctl.EXTRA:
            if a in self.controls.actions:
                continue
            if a == ctl.CUSTOM:
                m.addAction("Custom command…").triggered.connect(self.add_custom)
            else:
                m.addAction(ctl.action_label(a)).triggered.connect(lambda _=False, a=a: self.edit(a))
        add.setMenu(m)
        add.setEnabled(not m.isEmpty())
        self.group.box.addWidget(add, 0, Qt.AlignLeft)
        self.group.restyle()
        self.preview.set(self.controls)

    def set_controls(self, c: Controls):
        self.controls = c
        self.rebuild()
        self.changed()

    def load_preset(self, p, ask: bool = True):
        if ask and self.controls.bindings and self.controls != p.controls and not _confirm(
                self, "Load preset", f"Replace your controls with “{p.name}”?", "Replace"):
            return
        self.set_controls(p.controls)

    def reset(self, ask: bool = True):
        if ask and self.controls.bindings and not _confirm(
                self, "Reset controls", "Remove every trigger from every function?", "Remove all"):
            return
        self.set_controls(Controls())

    def problems(self) -> list[str]:
        out = []
        if not self.controls.triggers(ctl.OPEN):
            out.append("Nothing opens the menu, so you can't switch tools. Set “Open menu”.")
        if self.controls.uses("media:hold") and not self.has_hold:
            out.append("“Earbuds: press and hold” can't be read here (macOS keeps it from apps; "
                       "Windows needs Orbit running as admin).")
        return out

    # ---------------------------------------------------------------- editing
    def edit(self, action: str):
        self.dialog = FunctionDialog(self, action)
        self.dialog.exec()
        self.dialog = None

    def add_custom(self):
        d = CustomCommandDialog(self)
        if d.exec() and d.spec():
            self.edit(ctl.CUSTOM + d.spec())

    # ---------------------------------------------------------------- live test
    def capture_on(self, on: bool):
        if self.router is None:
            return
        self.router.capture = self.bridge.got.emit if on else None
        if not on:
            self.router.capture_keys = False

    def on_captured(self, cap):
        if isinstance(cap, ctl.Captured):
            if self.dialog is not None:
                self.dialog.on_captured(cap)
                return
            if cap.down:
                used = self.controls.uses(cap.input) and (cap.counted or self.preview.has(cap.input))
                self.show_heard((ctl.input_label(cap.input), used))
            if cap.counted:
                self.preview.pulse(cap.input)
            else:
                self.preview.key(cap.input, cap.down)
        else:                                   # an InputEvent from the preview hub
            a = cap.action or (ctl.FORWARD if cap.kind.value == "rotate" and cap.delta > 0 else
                               ctl.BACK if cap.kind.value == "rotate" else ctl.SELECT)
            self._lit = (a, self.preview.clock())

    def show_heard(self, heard):
        if heard is None:
            self.heard.setText("Press a button on your earbuds, keyboard, knob, mouse or trackpad: "
                               "its function lights up.")
            self.heard.setStyleSheet("")
        elif heard[1]:
            self.heard.setText(f"Last heard: {heard[0]}")
            self.heard.setStyleSheet("")
        else:
            self.heard.setText(f"Last heard: {heard[0]}. Not used: add it to a function, or load a preset that uses it.")
            self.heard.setStyleSheet(f"color: {WARN};")

    def _tick(self):
        self.preview.tick()
        lit = self._lit
        now = self.preview.clock()
        for a, row in self.rows.items():
            row.light(lit is not None and lit[0] == a and now - lit[1] < 0.7)


class _Category(QWidget):
    """One accordion: a header you click to open, then its triggers."""

    def __init__(self, title: str, about: str, inputs: list[str], dlg: "FunctionDialog", note: str = ""):
        super().__init__()
        self.inputs = inputs
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.head = _Card(title, about, chevron=True)
        self.head.toggled.connect(self._sync)
        self.title, self.about = title, about
        v.addWidget(self.head)
        self.body = QWidget()
        bv = QVBoxLayout(self.body)
        bv.setContentsMargins(14, 2, 6, 8)
        bv.setSpacing(2)
        if note:
            n = QLabel(note)
            n.setObjectName("meta")
            n.setWordWrap(True)
            bv.addWidget(n)
        self.items: dict[str, QPushButton] = {}
        for i in inputs:
            b = QPushButton()
            b.setObjectName("pick")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            dlg.picks.addButton(b)
            b.clicked.connect(lambda _=False, i=i: dlg.pick(i))
            if i == "media:hold" and not dlg.sec.has_hold:
                b.setEnabled(False)
                b.setToolTip("Not readable on this computer")
            self.items[i] = b
            bv.addWidget(b)
        v.addWidget(self.body)
        self._sync(False)

    def _sync(self, open_: bool):
        self.body.setVisible(open_)

    def filter(self, q: str, labels: Callable[[str], str]) -> bool:
        hit_cat = q in self.title.lower() or q in self.about.lower()
        any_hit = False
        for i, b in self.items.items():
            show = not q or hit_cat or q in ctl.input_label(i).lower()
            b.setVisible(show)
            b.setText(labels(i))
            any_hit |= show
        self.setVisible(any_hit)
        if q:
            self.head.setChecked(any_hit)
        return any_hit


class FunctionDialog(QDialog):
    """One function: its triggers; add one by choosing or recording. Save and close
    saves it all (no separate Save needed); Cancel forgets."""

    def __init__(self, sec: ControlsSection, action: str):
        super().__init__(sec.window())
        self.sec = sec
        self.action = action
        self.draft = sec.controls
        self.pending: Trigger | None = None
        self.setWindowTitle(ctl.action_label(action))
        self.setMinimumSize(560, 640)
        self.setStyleSheet(sec.window().styleSheet() + CARD_QSS + f"""
            QPushButton#pick {{ text-align: left; padding: 7px 12px; border: none; border-radius: 8px;
                                background: transparent; color: #F2F4F8; font-weight: 400; }}
            QPushButton#pick:hover {{ background: rgba(255,255,255,0.05); }}
            QPushButton#pick:checked {{ background: rgba(124,156,255,0.22); }}
            QPushButton#press {{ padding: 6px 12px; border-radius: 14px; }}
            QPushButton#press:checked {{ background: rgba(124,156,255,0.30); border-color: #7C9CFF; }}
        """)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        title = QLabel(ctl.action_label(action))
        title.setFont(_font(18, QFont.DemiBold))
        v.addWidget(title)
        hint = QLabel(ctl.action_hint(ctl.CUSTOM if action.startswith(ctl.CUSTOM) else action))
        hint.setObjectName("meta2")
        hint.setWordWrap(True)
        v.addWidget(hint)
        v.addSpacing(10)
        self.current = QVBoxLayout()
        v.addLayout(self.current)
        self.note = QLabel()
        self.note.setObjectName("meta")
        self.note.setWordWrap(True)
        v.addWidget(self.note)
        v.addSpacing(6)

        self.tabs = QTabWidget()
        # ---- Choose: categories (accordions) + search
        choose = QWidget()
        cv = QVBoxLayout(choose)
        cv.setContentsMargins(0, 10, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search a trigger")
        self.search.textChanged.connect(self._filter)
        cv.addWidget(self.search)
        self.picks = QButtonGroup(self)
        self.picks.setExclusive(True)
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 6, 0, 0)
        hv.setSpacing(6)
        self.cats = [_Category(t, a, ins, self, TRACKPAD_NOTE.get(sys.platform, "") if t == "Trackpad gestures" else "")
                     for t, a, ins in catalog()]
        for c in self.cats:
            hv.addWidget(c)
        self.nothing = QLabel("Nothing found. Try Record: press it and Orbit finds it.")
        self.nothing.setObjectName("meta")
        hv.addWidget(self.nothing)
        hv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(holder)
        cv.addWidget(scroll, 1)
        self.press_row = QWidget()
        pr = QHBoxLayout(self.press_row)
        pr.setContentsMargins(0, 6, 0, 0)
        pr.addWidget(QLabel("How"))
        self.press_group = QButtonGroup(self)
        self.press_btns: dict[Press, QPushButton] = {}
        for p in Press:
            b = QPushButton(p.label)
            b.setObjectName("press")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.press_group.addButton(b)
            b.clicked.connect(lambda _=False, p=p: self._set_press(p))
            self.press_btns[p] = b
            pr.addWidget(b)
        pr.addStretch(1)
        self.press_btns[Press.TAP].setChecked(True)
        cv.addWidget(self.press_row)
        self.tabs.addTab(choose, "Choose")
        # ---- Record
        rec = QWidget()
        rv = QVBoxLayout(rec)
        rv.addStretch(1)
        self.rec_title = QLabel("Press it now")
        self.rec_title.setFont(_font(18, QFont.Medium))
        self.rec_title.setAlignment(Qt.AlignCenter)
        rv.addWidget(self.rec_title)
        self.rec_sub = QLabel("The way you'll use it: tap, double tap, triple tap or hold. Keys, shortcuts, "
                              "media keys, mouse buttons, a key + scroll, trackpad gestures or your earbuds.")
        self.rec_sub.setObjectName("meta2")
        self.rec_sub.setWordWrap(True)
        self.rec_sub.setAlignment(Qt.AlignCenter)
        rv.addWidget(self.rec_sub)
        again_row = QHBoxLayout()
        again_row.addStretch(1)
        self.again = QPushButton("Try again")
        self.again.clicked.connect(self._rec_reset)
        again_row.addWidget(self.again)
        again_row.addStretch(1)
        rv.addLayout(again_row)
        rv.addStretch(2)
        self.tabs.addTab(rec, "Record")
        self.tabs.currentChanged.connect(self._tab)
        v.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        self.pending_lab = QLabel()
        self.pending_lab.setObjectName("meta2")
        bar.addWidget(self.pending_lab, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(cancel)
        self.save_btn = QPushButton("Save and close")
        self.save_btn.setObjectName("primary")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save_and_close)
        bar.addWidget(self.save_btn)
        v.addLayout(bar)

        self._rec_got: Trigger | None = None
        self._rec_input: str | None = None
        self._rec: PressRecognizer | None = None
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(15)
        self._rec_timer.timeout.connect(lambda: self._rec and self._rec.tick(self.sec.preview.clock()))
        self._rec_timer.start()
        self._chosen: str | None = None
        self._show_current()
        self._filter()
        self._rec_reset()
        self._sync_pending()

    # ---------------------------------------------------------------- triggers set now
    def _show_current(self):
        while self.current.count():
            w = self.current.takeAt(0).widget()
            if w:
                w.setParent(None)
        ts = self.draft.triggers(self.action)
        if not ts:
            lab = QLabel("Not set yet.")
            lab.setObjectName("meta")
            self.current.addWidget(lab)
        for t in ts:
            r = QFrame()
            h = QHBoxLayout(r)
            h.setContentsMargins(0, 2, 0, 2)
            mark = QLabel()
            mark.setFixedSize(16, 16)
            mark.setAlignment(Qt.AlignCenter)
            _mark(mark, True)
            h.addWidget(mark)
            lab = QLabel(t.label())
            lab.setStyleSheet(f"color: {GREEN};")
            h.addWidget(lab, 1)
            x = QToolButton()
            x.setText("✕")
            x.setToolTip("Remove")
            x.clicked.connect(lambda _=False, t=t: self._remove(t))
            h.addWidget(x)
            self.current.addWidget(r)

    def _remove(self, t: Trigger):
        self.draft = self.draft.remove(self.action, t)
        self._show_current()
        self._filter()

    # ---------------------------------------------------------------- choose
    def _labels(self, i: str) -> str:
        users = [ctl.action_label(b.action) for b in self.draft.bindings
                 if b.trigger.input == i and b.action != self.action]
        return ctl.input_label(i) + (f"     · now {', '.join(users)}" if users else "")

    def _filter(self, *_):
        q = self.search.text().strip().lower()
        hits = [c.filter(q, self._labels) for c in self.cats]
        self.nothing.setVisible(not any(hits))

    def pick(self, inp: str):
        self._chosen = inp
        counted = ctl.counted(inp)
        for b in self.press_btns.values():
            b.setEnabled(not counted)
        self._set_pending(Trigger(inp, Press.TAP if counted else self._press()))

    def _press(self) -> Press:
        return next((p for p, b in self.press_btns.items() if b.isChecked()), Press.TAP)

    def _set_press(self, p: Press):
        if self._chosen and not ctl.counted(self._chosen):
            self._set_pending(Trigger(self._chosen, p))

    # ---------------------------------------------------------------- record
    def _tab(self, i: int):
        if self.sec.router is not None:
            self.sec.router.capture_keys = i == 1
        self._rec_reset()

    def _rec_reset(self):
        self._rec_got, self._rec_input, self._rec = None, None, None
        self.rec_title.setText("Press it now")
        if self.tabs.currentIndex() == 1:
            self._set_pending(None)

    def on_captured(self, cap):
        if self.tabs.currentIndex() != 1 or self._rec_got is not None:
            return
        now = self.sec.preview.clock()
        if cap.counted:
            if cap.down:
                self._got(Trigger(cap.input))
            return
        if self._rec_input != cap.input:
            if not cap.down:
                return
            self._rec_input = cap.input
            self.rec_title.setText("Keep going…")
            self._rec = PressRecognizer(set(Press), False, lambda p, i=cap.input: self._got(Trigger(i, p)))
            self._rec.down(now)
        elif self._rec:
            (self._rec.down if cap.down else self._rec.up)(now)

    def _got(self, t: Trigger):
        self._rec_got = t
        self.rec_title.setText(t.label())
        self._set_pending(t)

    # ---------------------------------------------------------------- save
    def _set_pending(self, t: Trigger | None):
        self.pending = t
        self._sync_pending()

    def _sync_pending(self):
        t = self.pending
        if t is None:
            self.pending_lab.setText("")
            self.note.setText("")
            return
        other = self.draft.action_for(t.normalized())
        self.pending_lab.setText(f"Adding: {t.label()}")
        self.note.setText(f"That's “{ctl.action_label(other)}” now; saving moves it here."
                          if other and other != self.action else "")

    def save_and_close(self):
        c = self.draft
        if self.pending is not None:
            c, _ = c.add(self.action, self.pending)
        self.sec.set_controls(c)
        self.sec.persist()
        self.accept()

    def done(self, r):
        if self.sec.router is not None:
            self.sec.router.capture_keys = False
        super().done(r)


class CustomCommandDialog(QDialog):
    """Custom command: press a key combo, or open an app."""

    def __init__(self, sec: ControlsSection):
        super().__init__(sec.window())
        from orbit.ui.settings_window import KeyField
        self.setWindowTitle("Custom command")
        self.setStyleSheet(sec.window().styleSheet())
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        t = QLabel("Custom command")
        t.setFont(_font(18, QFont.DemiBold))
        v.addWidget(t)
        self.keys_rb = QRadioButton("Press a key combo")
        self.app_rb = QRadioButton("Open an app")
        g = QButtonGroup(self)
        g.addButton(self.keys_rb)
        g.addButton(self.app_rb)
        self.keys_rb.setChecked(True)
        self.keys = KeyField("", lambda: None)
        self.app = QLineEdit()
        self.app.setPlaceholderText("App name, e.g. Notepad, Spotify, Safari")
        for w in (self.keys_rb, self.keys, self.app_rb, self.app):
            v.addWidget(w)
        bar = QHBoxLayout()
        bar.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Next: pick its trigger")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        bar.addWidget(cancel)
        bar.addWidget(ok)
        v.addLayout(bar)

    def spec(self) -> str:
        if self.keys_rb.isChecked():
            k = self.keys.combo()
            return f"keys:{k}" if k else ""
        name = self.app.text().strip()
        return f"launch:{name}" if name else ""


# ==================================================================== onboarding

ONBOARD = [
    ("cmf", "CMF Buds Pro 2", "The case dial: turn it to move, press to select, double press to open."),
    ("earbuds", "Other earbuds or headphones", "Their press gestures: once, twice, three times."),
    ("media_keys", "A keyboard volume knob or media keys", "Volume keys move; play / pause selects."),
    ("mouse", "Mouse side buttons", "Back / forward move; hold them to select or open."),
    ("trackpad", "Trackpad gestures", "Swipes and taps (Windows) or rotate and pinch (Mac)."),
    ("mod_scroll", "A key + scroll", "Hold Ctrl and scroll."),
    ("f_keys", "A macro pad or spare keys (F13–F16)", "For pads and remotes that send F13–F16."),
    ("", "Explore and set it up myself", "Start from scratch: pick every trigger yourself."),
]


class OnboardingDialog(QDialog):
    """What do you want to control Orbit with? One pick sets the controls; CMF buds get
    the Nothing X step. Can be run again from Settings → Controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up Orbit")
        self.setMinimumSize(560, 600)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet() + CARD_QSS)
        self.result_controls: Controls | None = None
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 24, 26, 20)
        self.pages = []
        self.page = 0

        # page 1: what will you use?
        p1 = QWidget()
        a = QVBoxLayout(p1)
        a.setContentsMargins(0, 0, 0, 0)
        t = QLabel("What do you want to control Orbit with?")
        t.setFont(_font(20, QFont.DemiBold))
        t.setWordWrap(True)
        a.addWidget(t)
        s = QLabel("Pick one to start. You can add more and change everything later in Settings → Controls.")
        s.setObjectName("meta2")
        s.setWordWrap(True)
        a.addWidget(s)
        a.addSpacing(10)
        self.choice = QButtonGroup(self)
        self.choice.setExclusive(True)
        self.options: dict[str, _Card] = {}
        here = {p.id for p in Presets.here()}
        for pid, name, about in ONBOARD:
            if pid and pid not in here:
                continue
            rb = _Card(name, about)
            self.choice.addButton(rb)
            self.options[pid] = rb
            a.addWidget(rb)
            a.addSpacing(4)
        self.choice.buttonClicked.connect(lambda _: self._show(self.page))
        self.options["cmf"].setChecked(True)
        a.addStretch(1)
        # page 2: the CMF dial in Nothing X
        p2 = QWidget()
        b = QVBoxLayout(p2)
        b.setContentsMargins(0, 0, 0, 0)
        t2 = QLabel("Set the dial in Nothing X")
        t2.setFont(_font(20, QFont.DemiBold))
        b.addWidget(t2)
        s2 = QLabel("The dial talks to Orbit through its music controls. In the Nothing X app → Controls → Dial:\n\n"
                    "   Single press   →  Play / Pause\n   Double press  →  Next track\n"
                    "   Triple press    →  Previous track\n   Press and hold  →  Voice assistant\n\n"
                    "Then make the buds this computer's sound output.")
        s2.setObjectName("meta2")
        s2.setWordWrap(True)
        b.addWidget(s2)
        b.addStretch(1)
        self.pages = [p1, p2]
        for p in self.pages:
            v.addWidget(p, 1)
        bar = QHBoxLayout()
        self.back = QPushButton("Back")
        self.back.clicked.connect(lambda: self._show(0))
        bar.addWidget(self.back)
        bar.addStretch(1)
        skip = QPushButton("Not now")
        skip.clicked.connect(self.reject)
        bar.addWidget(skip)
        self.next = QPushButton("Continue")
        self.next.setObjectName("primary")
        self.next.clicked.connect(self._next)
        bar.addWidget(self.next)
        v.addLayout(bar)
        self._show(0)

    def picked(self) -> str:
        return next((pid for pid, rb in self.options.items() if rb.isChecked()), "")

    def _show(self, i: int):
        self.page = i
        for k, p in enumerate(self.pages):
            p.setVisible(k == i)
        self.back.setVisible(i > 0)
        self.next.setText("Finish" if i == 1 or self.picked() != "cmf" else "Continue")

    def _next(self):
        if self.page == 0 and self.picked() == "cmf":
            self._show(1)
            return
        pid = self.picked()
        p = next((x for x in Presets.here() if x.id == pid), None)
        self.result_controls = p.controls if p else Controls()
        self.accept()
