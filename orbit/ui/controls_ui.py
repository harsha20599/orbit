"""Settings window: Controls. Which trigger does which function (orbit/core/controls.py).

Mirrors the Android app's Setup controls:
  - the functions (Single press / Select, Open menu, Previous, Next, plus added ones),
    each with its triggers in green and a Change button; Load preset; Add a function
  - while the window is in front, every input Orbit hears is shown ("Last heard") and
    lights up its function, and nothing acts (the router's capture)
  - Change opens one function: Choose (search, or browse by category; then tap /
    double / triple / hold) or Record (press it the way you'll use it)
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QPushButton, QRadioButton, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)

from orbit.core import controls as ctl
from orbit.core.controls import Controls, ControlsHub, Press, PressRecognizer, Presets, Trigger

GREEN = "#3DDC97"

CATALOG: list[tuple[str, list[str]]] = [
    ("Earbuds & the CMF dial", ["media:play", "media:next", "media:prev", "media:hold", "vol:up", "vol:down"]),
    ("Volume & media keys", ["key:volumeup", "key:volumedown", "key:mute", "key:playpause", "key:nexttrack",
                             "key:prevtrack"]),
    ("Mouse keys", ["mouse:back", "mouse:forward", "mouse:middle"]),
    ("Keyboard", [f"key:f{i}" for i in range(13, 25)] +
     ["key:pageup", "key:pagedown", "key:up", "key:down", "key:left", "key:right", "key:space", "key:enter"]),
]


class _Bridge(QObject):
    """Hook / source threads -> the Qt thread."""
    got = Signal(object)


def _font(px: float, weight=QFont.Normal) -> QFont:
    from orbit.ui.settings_window import _font as f
    return f(px, weight)


def triggers_text(ts: list[Trigger]) -> str:
    return "  or  ".join(t.label() for t in ts) if ts else "Not set"


class _FunctionRow(QFrame):
    def __init__(self, label: str, on_change: Callable[[], None]):
        super().__init__()
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 10, 12, 10)
        h.setSpacing(12)
        self.mark = QLabel()
        self.mark.setFixedSize(22, 22)
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
        self.trig.setStyleSheet(f"color: {GREEN if ts else '#6E7483'};")
        on = bool(ts)
        self.mark.setText("✓" if on else "")
        self.mark.setStyleSheet(f"background: {GREEN}; color: #0B1A12; border-radius: 11px; font-weight: 700;" if on
                                else "border: 2px solid #4A5060; border-radius: 11px;")

    def light(self, on: bool):
        if on != self._lit:
            self._lit = on
            self.setStyleSheet("QFrame#row { background: rgba(124,156,255,0.16); }" if on else "")


class ControlsSection(QWidget):
    """The Controls group of the Settings window. `controls` is the draft; `changed`
    is called on every edit (the window saves with everything else)."""

    def __init__(self, controls: Controls, router, has_hold: bool, changed: Callable[[], None], group_cls):
        super().__init__()
        self.controls = controls
        self.router = router
        self.has_hold = has_hold
        self.changed = changed
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)

        top = QHBoxLayout()
        self.help = QLabel("What opens the menu, moves and selects. Mix earbuds, keys, a knob, mouse buttons.")
        self.help.setObjectName("meta2")
        self.help.setWordWrap(True)
        top.addWidget(self.help, 1)
        self.preset_btn = QToolButton()
        self.preset_btn.setText("Load preset  ▾")
        self.preset_btn.setCursor(Qt.PointingHandCursor)
        self.preset_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.preset_btn)
        for p in Presets.ALL:
            a = menu.addAction(p.name)
            a.setToolTip(p.about)
            a.triggered.connect(lambda _=False, p=p: self.load_preset(p))
        self.preset_btn.setMenu(menu)
        top.addWidget(self.preset_btn)
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
                act = m.addAction(ctl.action_label(a))
                act.triggered.connect(lambda _=False, a=a: self.edit(a))
        add.setMenu(m)
        add.setEnabled(not m.isEmpty())
        self.group.box.addWidget(add, 0, Qt.AlignLeft)
        self.group.restyle()
        self.preview.set(self.controls)

    def set_controls(self, c: Controls):
        self.controls = c
        self.rebuild()
        self.changed()

    def load_preset(self, p):
        self.set_controls(p.controls)

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
            self.heard.setText("Press a button on your earbuds, keyboard, knob or mouse: its function lights up.")
            self.heard.setStyleSheet("")
        elif heard[1]:
            self.heard.setText(f"Last heard: {heard[0]}")
            self.heard.setStyleSheet("")
        else:
            self.heard.setText(f"Last heard: {heard[0]}. Not used: add it to a function, or load a preset that uses it.")
            self.heard.setStyleSheet("color: #F2B46B;")

    def _tick(self):
        self.preview.tick()
        lit = self._lit
        now = self.preview.clock()
        for a, row in self.rows.items():
            row.light(lit is not None and lit[0] == a and now - lit[1] < 0.7)


class FunctionDialog(QDialog):
    """One function: its triggers; add one by choosing or recording."""

    def __init__(self, sec: ControlsSection, action: str):
        super().__init__(sec.window())
        self.sec = sec
        self.action = action
        self.setWindowTitle(ctl.action_label(action))
        self.setMinimumSize(520, 560)
        self.setStyleSheet(sec.window().styleSheet())
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        title = QLabel(ctl.action_label(action))
        title.setFont(_font(18, QFont.DemiBold))
        v.addWidget(title)
        hint = QLabel(ctl.action_hint(action.split(":")[0] + ":" if action.startswith(ctl.CUSTOM) else action))
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
        v.addSpacing(8)

        self.tabs = QTabWidget()
        # ---- Choose
        choose = QWidget()
        cv = QVBoxLayout(choose)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search a trigger")
        self.search.textChanged.connect(self._fill)
        cv.addWidget(self.search)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget { border: none; } QListWidget::item { padding: 7px 6px; border-radius: 8px; }"
                                "QListWidget::item:selected { background: rgba(124,156,255,0.22); color: #F2F4F8; }")
        self.list.itemDoubleClicked.connect(lambda _: self._add_chosen())
        self.list.currentItemChanged.connect(lambda *_: self._sync_press())
        cv.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.press = QComboBox()
        for p in Press:
            self.press.addItem(p.label, p)
        row.addWidget(QLabel("How"))
        row.addWidget(self.press)
        row.addStretch(1)
        self.add_btn = QPushButton("Add")
        self.add_btn.setObjectName("primary")
        self.add_btn.clicked.connect(self._add_chosen)
        row.addWidget(self.add_btn)
        cv.addLayout(row)
        self.tabs.addTab(choose, "Choose")
        # ---- Record
        rec = QWidget()
        rv = QVBoxLayout(rec)
        rv.addStretch(1)
        self.rec_title = QLabel("Press it now")
        self.rec_title.setFont(_font(20, QFont.DemiBold))
        self.rec_title.setAlignment(Qt.AlignCenter)
        rv.addWidget(self.rec_title)
        self.rec_sub = QLabel("The way you'll use it: tap, double tap, triple tap or hold. "
                              "Keys, shortcuts, media keys, mouse buttons or your earbuds.")
        self.rec_sub.setObjectName("meta2")
        self.rec_sub.setWordWrap(True)
        self.rec_sub.setAlignment(Qt.AlignCenter)
        rv.addWidget(self.rec_sub)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.again = QPushButton("Try again")
        self.again.clicked.connect(self._rec_reset)
        self.use = QPushButton("Use this")
        self.use.setObjectName("primary")
        self.use.clicked.connect(self._rec_use)
        btns.addWidget(self.again)
        btns.addWidget(self.use)
        btns.addStretch(1)
        rv.addLayout(btns)
        rv.addStretch(2)
        self.tabs.addTab(rec, "Record")
        self.tabs.currentChanged.connect(self._tab)
        v.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.clicked.connect(self.accept)
        bar.addWidget(done)
        v.addLayout(bar)

        self._rec_got: Trigger | None = None
        self._rec_input: str | None = None
        self._rec: PressRecognizer | None = None
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(15)
        self._rec_timer.timeout.connect(lambda: self._rec and self._rec.tick(self.sec.preview.clock()))
        self._rec_timer.start()
        self._show_current()
        self._fill()
        self._rec_reset()

    # ---------------------------------------------------------------- current
    def _show_current(self):
        while self.current.count():
            w = self.current.takeAt(0).widget()
            if w:
                w.setParent(None)
        ts = self.sec.controls.triggers(self.action)
        if not ts:
            lab = QLabel("Not set yet.")
            lab.setObjectName("meta")
            self.current.addWidget(lab)
        for t in ts:
            r = QFrame()
            h = QHBoxLayout(r)
            h.setContentsMargins(0, 2, 0, 2)
            lab = QLabel("✓  " + t.label())
            lab.setStyleSheet(f"color: {GREEN};")
            h.addWidget(lab, 1)
            x = QToolButton()
            x.setText("✕")
            x.setToolTip("Remove")
            x.clicked.connect(lambda _=False, t=t: self._remove(t))
            h.addWidget(x)
            self.current.addWidget(r)

    def _set(self, c: Controls, lost: str | None = None):
        self.sec.set_controls(c)
        self._show_current()
        self._fill()
        self.note.setText(f"That trigger was on “{ctl.action_label(lost)}”; it's moved here." if lost else "")

    def _remove(self, t: Trigger):
        self._set(self.sec.controls.remove(self.action, t))

    def _add(self, t: Trigger):
        c, lost = self.sec.controls.add(self.action, t)
        self._set(c, lost)

    # ---------------------------------------------------------------- choose
    def _fill(self):
        q = self.search.text().strip().lower()
        self.list.clear()
        for cat, inputs in CATALOG:
            hits = [i for i in inputs if not q or q in ctl.input_label(i).lower() or q in cat.lower()]
            if not hits:
                continue
            head = QListWidgetItem(cat.upper())
            head.setFlags(Qt.NoItemFlags)
            head.setForeground(Qt.gray)
            f = head.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() * 0.85); head.setFont(f)
            self.list.addItem(head)
            for i in hits:
                users = [ctl.action_label(b.action) for b in self.sec.controls.bindings
                         if b.trigger.input == i and b.action != self.action]
                text = ctl.input_label(i) + (f"   (now: {', '.join(users)})" if users else "")
                it = QListWidgetItem(text)
                it.setData(Qt.UserRole, i)
                if i == "media:hold" and not self.sec.has_hold:
                    it.setFlags(Qt.NoItemFlags)
                    it.setToolTip("Not readable on this computer")
                self.list.addItem(it)
        if not self.list.count():
            self.list.addItem(QListWidgetItem("Nothing found. Try Record: press it and Orbit finds it."))
        self._sync_press()

    def _chosen(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _sync_press(self):
        inp = self._chosen()
        self.press.setEnabled(bool(inp) and not ctl.counted(inp))
        self.add_btn.setEnabled(bool(inp))

    def _add_chosen(self):
        inp = self._chosen()
        if inp:
            self._add(Trigger(inp, self.press.currentData()))

    # ---------------------------------------------------------------- record
    def _tab(self, i: int):
        if self.sec.router is not None:
            self.sec.router.capture_keys = i == 1
        self._rec_reset()

    def _rec_reset(self):
        self._rec_got, self._rec_input, self._rec = None, None, None
        self.rec_title.setText("Press it now")
        self.use.setEnabled(False)

    def _rec_use(self):
        if self._rec_got:
            self._add(self._rec_got)
            self.tabs.setCurrentIndex(0)

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
        self.rec_title.setText("✓  " + t.label())
        self.use.setEnabled(True)

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
        ok = QPushButton("Next")
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
