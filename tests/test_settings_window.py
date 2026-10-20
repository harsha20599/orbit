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
    w.controls_sec.load_preset(Presets.MOUSE, ask=False)
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


def test_reset_clears_every_trigger(tmp_path):
    from orbit.core.controls import Controls
    w, saved, app, _ = window(tmp_path)
    w.controls_sec.reset(ask=False)
    assert w.controls_sec.controls == Controls()
    assert all(r.trig.text() == "Not set" for r in w.controls_sec.rows.values())
    assert any("Nothing opens" in p for p in w.controls_sec.problems())


def test_add_menu_has_no_assistant():
    from orbit.core import controls as ctl
    assert ctl.ASSISTANT not in ctl.EXTRA


def test_choose_accordion_search_and_save_and_close(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Press, Presets, Trigger
    from orbit.ui.controls_ui import FunctionDialog
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()})
    sec = w.controls_sec
    d = FunctionDialog(sec, ctl.SELECT)
    assert all(not c.body.isVisibleTo(d) for c in d.cats)          # categories start closed
    d.search.setText("mouse forward")
    mouse = next(c for c in d.cats if c.title == "Mouse buttons")
    assert mouse.head.isChecked() and mouse.items["mouse:forward"].isVisibleTo(d)
    assert not mouse.items["mouse:back"].isVisibleTo(d)
    d.pick("mouse:forward")
    d.press_btns[Press.HOLD].click()
    assert d.pending == Trigger("mouse:forward", Press.HOLD)
    n = len(saved)
    d.save_and_close()                                               # saves now: no separate Save
    assert len(saved) == n + 1
    assert Trigger("mouse:forward", Press.HOLD) in sec.controls.triggers(ctl.SELECT)
    assert saved[-1]["controls"]["bindings"]


def test_choosing_a_used_trigger_says_it_moves(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Presets
    from orbit.ui.controls_ui import FunctionDialog
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()})
    d = FunctionDialog(w.controls_sec, ctl.SELECT)
    d.pick("key:f14")                                                # F14 tap is Next
    assert "Next" in d.note.text()
    d.save_and_close()
    assert w.controls_sec.controls.triggers(ctl.FORWARD) == []


def test_cancel_forgets(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Presets
    from orbit.ui.controls_ui import FunctionDialog
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()})
    before = w.controls_sec.controls
    d = FunctionDialog(w.controls_sec, ctl.SELECT)
    d._remove(before.triggers(ctl.SELECT)[0])
    d.pick("mouse:back")
    d.reject()
    assert w.controls_sec.controls == before and not saved


def test_record_then_save_and_close(tmp_path):
    import time
    from orbit.core import controls as ctl
    from orbit.core.controls import Captured, Press, Presets, Router, Trigger
    from orbit.ui.controls_ui import FunctionDialog
    r = Router(lambda e: None, lambda m: None)
    w, saved, app, _ = window(tmp_path, {"controls": Presets.F_KEYS.controls.to_json()}, router=r)
    d = FunctionDialog(w.controls_sec, ctl.OPEN)
    d.tabs.setCurrentIndex(1)
    assert r.capture_keys is True
    clock = w.controls_sec.preview.clock
    d.on_captured(Captured("key:ctrl+f20", True))
    d.on_captured(Captured("key:ctrl+f20", False))
    deadline = time.monotonic() + 1.5
    while d._rec_got is None and time.monotonic() < deadline:
        app.processEvents()
        d._rec and d._rec.tick(clock())
    assert d._rec_got == Trigger("key:ctrl+f20", Press.TAP) == d.pending
    assert "Adding" in d.pending_lab.text()
    d.save_and_close()
    assert Trigger("key:ctrl+f20") in w.controls_sec.controls.triggers(ctl.OPEN)
    assert saved and r.capture_keys is False


def test_record_a_trackpad_gesture_or_modifier_scroll(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Captured, Trigger
    from orbit.ui.controls_ui import FunctionDialog
    w, saved, app, _ = window(tmp_path)
    d = FunctionDialog(w.controls_sec, ctl.FORWARD)
    d.tabs.setCurrentIndex(1)
    d.on_captured(Captured("scroll:ctrl+down", True, counted=True))
    assert d.pending == Trigger("scroll:ctrl+down")
    d._rec_reset()
    d.on_captured(Captured("touchpad:3-swipe-right", True, counted=True))
    assert d.pending == Trigger("touchpad:3-swipe-right")
    d.done(0)


def test_catalog_per_platform():
    from orbit.ui.controls_ui import catalog
    win = {t: ins for t, _, ins in catalog("win32")}
    mac = {t: ins for t, _, ins in catalog("darwin")}
    assert "touchpad:3-swipe-left" in win["Trackpad gestures"] and "touchpad:pinch-in" in mac["Trackpad gestures"]
    assert "scroll:ctrl+up" in win["Scroll + a key"] and "scroll:cmd+up" in mac["Scroll + a key"]


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
    from orbit.core import controls as ctl
    from orbit.core.controls import Trigger
    w, saved, app, _ = window(tmp_path, has_hold=False)
    c, _ = w.controls_sec.controls.add(ctl.LAST_TOOL, Trigger("media:hold"))
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


def test_scroll_reset_to_defaults(tmp_path):
    w, saved, app, base = window(tmp_path, {"scroll": {"max_gain": 7.0, "notches_per_detent": 2.5}})
    assert w.fast_scroll.value() == 7.0
    w.reset_scroll()
    assert w.fast_scroll.value() == float(base["tools"]["scroll"]["max_gain"])
    assert w.click_scroll.value() == float(base["tools"]["scroll"].get("notches_per_detent", 1.0))


def test_onboarding_picks(tmp_path):
    from orbit.core.controls import Controls, Presets
    from orbit.ui.controls_ui import OnboardingDialog
    w, *_ = window(tmp_path)
    d = OnboardingDialog(w)
    assert d.picked() == "cmf"
    d._next()                                                        # CMF: the Nothing X step next
    assert d.page == 1 and d.next.text() == "Finish"
    d._next()
    assert d.result_controls == Presets.CMF.controls
    d2 = OnboardingDialog(w)
    d2.options[""].setChecked(True)                                  # explore myself: from scratch
    d2._next()
    assert d2.result_controls == Controls()
    d3 = OnboardingDialog(w)
    d3.options["mouse"].setChecked(True)
    d3._next()
    assert d3.result_controls == Presets.MOUSE.controls


def test_onboarded_flag_is_kept(tmp_path):
    w, saved, *_ = window(tmp_path, {"onboarded": True})
    w.save()
    assert saved[-1]["onboarded"] is True
    w2, saved2, *_ = window(tmp_path)
    w2.save()
    assert "onboarded" not in saved2[-1]


def test_gestures_show_no_press_choice_keys_do(tmp_path):
    from orbit.core import controls as ctl
    from orbit.core.controls import Press, Trigger
    from orbit.ui.controls_ui import FunctionDialog
    w, *_ = window(tmp_path)
    d = FunctionDialog(w.controls_sec, ctl.OPEN)
    d.show()
    assert not d.press_row.isVisible()                               # nothing picked yet
    d.pick("touchpad:4-swipe-up")
    assert not d.press_row.isVisible() and d.pending == Trigger("touchpad:4-swipe-up")
    d.pick("key:f13")
    assert d.press_row.isVisible() and all(b.isVisible() for b in d.press_btns.values())
    d.press_btns[Press.DOUBLE].click()
    assert d.pending == Trigger("key:f13", Press.DOUBLE)
    d.done(0)


def test_choose_record_toggle(tmp_path):
    from orbit.core import controls as ctl
    from orbit.ui.controls_ui import FunctionDialog
    w, *_ = window(tmp_path)
    d = FunctionDialog(w.controls_sec, ctl.OPEN)
    seen = []
    d.tabs.currentChanged.connect(seen.append)
    assert d.tabs.currentIndex() == 0 and d.tabs.buttons[0].isChecked()
    d.tabs.buttons[1].click()
    assert d.tabs.currentIndex() == 1 and d.tabs.buttons[1].isChecked() and not d.tabs.buttons[0].isChecked()
    assert seen == [1]
    d.done(0)


def test_rows_in_order_menu_first(tmp_path):
    from orbit.core import controls as ctl
    w, *_ = window(tmp_path)
    assert list(w.controls_sec.rows)[:4] == [ctl.OPEN, ctl.SELECT, ctl.BACK, ctl.FORWARD]
    assert w.controls_sec.reset_btn.text() == "" and not w.controls_sec.reset_btn.icon().isNull()
