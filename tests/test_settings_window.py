"""The Settings window builds, reflects changes in its preview, and saves what it shows."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from orbit.core import config as config_mod  # noqa: E402
from orbit.core import settings as st  # noqa: E402


def window(tmp_path, current=None, router=None, has_hold=True):
    from orbit.ui.settings_window import SettingsWindow
    app = QApplication.instance() or QApplication([])
    base, _ = config_mod.load(platform="windows")
    saved = []
    w = SettingsWindow(base, current or {}, has_hold, "#7C9CFF", saved.append, settings_path=tmp_path / "s.json",
                       router=router)
    return w, saved, app, base


def test_window_collects_toggles_order_and_controls(tmp_path):
    from orbit.core.controls import Presets
    w, saved, app, base = window(tmp_path)
    first, second = w.order[0], w.order[1]
    w.rows[second].switch.setChecked(False)
    w.move(first, 1)
    w.controls_sec.load_preset(Presets.MOUSE)
    assert second not in [t for t, *_ in w.preview.items]
    assert "Mouse forward button" in w.how.text()
    w.save()
    s = saved[-1]
    assert s["wheel"]["order"][:2] == [second, first]
    assert second not in s["wheel"]["enabled"]
    assert s["controls"]["preset"] == "mouse"
    assert st.load(tmp_path / "s.json") == s
    app.processEvents()


def test_controls_section_shows_the_saved_setup_and_default(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Presets
    w, saved, app, _ = window(tmp_path)
    sec = w.controls_sec
    assert sec.controls == Presets.default()
    assert list(sec.rows) == list(ctl.CORE)
    assert sec.rows[ctl.FORWARD].trig.text() == "Dial forward"
    w2, *_ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()})
    assert w2.controls_sec.rows[ctl.OPEN].trig.text() == "F16 · tap"


def test_function_dialog_choose_adds_and_moves_triggers(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Press, Presets, Trigger
    from orbit.ui.controls_ui import FunctionDialog
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()})
    sec = w.controls_sec
    d = FunctionDialog(sec, ctl.SELECT)
    d.search.setText("mouse forward")
    items = [d.list.item(i) for i in range(d.list.count())]
    target = next(it for it in items if it.data(0x0100) == "mouse:forward")
    d.list.setCurrentItem(target)
    d.press.setCurrentIndex(d.press.findData(Press.HOLD))
    d._add_chosen()
    assert Trigger("mouse:forward", Press.HOLD) in sec.controls.triggers(ctl.SELECT)
    d.search.setText("")
    f14 = next(d.list.item(i) for i in range(d.list.count()) if d.list.item(i).data(0x0100) == "key:f14")
    d.list.setCurrentItem(f14)
    d.press.setCurrentIndex(d.press.findData(Press.TAP))
    d._add_chosen()                                          # F14 tap was Next: it moves
    assert sec.controls.triggers(ctl.FORWARD) == [] and "Next" in d.note.text()
    assert "Nothing opens" not in " ".join(sec.problems())
    d.done(0)


def test_function_dialog_record_classifies_the_press(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Captured, Press, Presets, Trigger, Router
    r = Router(lambda e: None, lambda m: None)
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()}, router=r)
    from orbit.ui.controls_ui import FunctionDialog
    d = FunctionDialog(w.controls_sec, ctl.OPEN)
    d.tabs.setCurrentIndex(1)
    assert r.capture_keys is True                            # Record: every key is captured
    clock = w.controls_sec.preview.clock
    d.on_captured(Captured("key:ctrl+f20", True))
    d.on_captured(Captured("key:ctrl+f20", False))
    import time
    deadline = time.monotonic() + 1.5
    while d._rec_got is None and time.monotonic() < deadline:
        app.processEvents()
        d._rec and d._rec.tick(clock())
    assert d._rec_got == Trigger("key:ctrl+f20", Press.TAP)
    d._rec_use()
    assert Trigger("key:ctrl+f20") in w.controls_sec.controls.triggers(ctl.OPEN)
    d.done(0)
    assert r.capture_keys is False


def test_live_test_shows_last_heard_and_lights_the_function(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Captured, Presets, Router
    r = Router(lambda e: None, lambda m: None)
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()}, router=r)
    sec = w.controls_sec
    sec.capture_on(True)
    assert r.capture is not None
    sec.on_captured(Captured("key:f16", True))
    sec.on_captured(Captured("key:f16", False))
    app.processEvents()
    sec._tick()
    assert sec._lit and sec._lit[0] == ctl.OPEN
    assert "F16" in sec.heard.text()
    sec.on_captured(Captured("media:play", True, counted=True))
    assert "Not used" in sec.heard.text()
    sec.capture_on(False)
    assert r.capture is None


def test_hold_warning_when_the_hold_cant_be_read(tmp_path):
    w, saved, app, _ = window(tmp_path, has_hold=False)
    from orbit.core import controls as ctl
    from orbit.core.controls import Trigger
    c, _ = w.controls_sec.controls.add(ctl.ASSISTANT, Trigger("media:hold"))
    w.controls_sec.set_controls(c)
    assert any("press and hold" in p for p in w.controls_sec.problems())


def test_custom_command_spec(tmp_path):
    from orbit.ui.controls_ui import CustomCommandDialog
    w, *_ = window(tmp_path)
    d = CustomCommandDialog(w.controls_sec)
    assert d.spec() == ""
    d.app_rb.setChecked(True)
    d.app.setText("Spotify")
    assert d.spec() == "launch:Spotify"
