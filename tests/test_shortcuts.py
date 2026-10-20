"""Custom key-shortcut wheel items and the Claude shortcut."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orbit.core import actions, config as config_mod, settings as st, shortcuts  # noqa: E402
from orbit.core.engine import Engine  # noqa: E402
from orbit.core.events import Capability, InputEvent, Kind  # noqa: E402
from tests.test_engine import FakeOut, FakeRot, FakeSrc, FakeUI  # noqa: E402


def test_qt_names_become_orbit_combos():
    assert shortcuts.from_qt("Ctrl+Alt+V", "win32") == "ctrl+alt+v"
    assert shortcuts.from_qt("Meta+Shift+S", "win32") == "win+shift+s"
    assert shortcuts.from_qt("Ctrl+Shift+PgDown", "win32") == "ctrl+shift+pagedown"
    assert shortcuts.from_qt("Ctrl++", "win32") == "ctrl+plus"
    assert shortcuts.from_qt("F5", "win32") == "f5"
    # macOS: Qt calls Cmd "Ctrl" and Control "Meta"
    assert shortcuts.from_qt("Ctrl+Shift+4", "darwin") == "cmd+shift+4"
    assert shortcuts.from_qt("Meta+Alt+Space", "darwin") == "ctrl+alt+space"
    assert shortcuts.from_qt("", "win32") == ""


def test_round_trip_and_pretty():
    for combo in ("ctrl+alt+v", "win+shift+s", "ctrl+pagedown"):
        assert shortcuts.from_qt(shortcuts.to_qt(combo, "win32"), "win32") == combo
    assert shortcuts.from_qt(shortcuts.to_qt("cmd+shift+4", "darwin"), "darwin") == "cmd+shift+4"
    assert shortcuts.pretty("ctrl+alt+v", "win32") == "Ctrl + Alt + V"
    assert shortcuts.pretty("cmd+shift+4", "darwin") == "⌘⇧4"


def test_shortcut_items_join_the_wheel_and_press_their_keys():
    cfg, _ = config_mod.load(platform="windows", user_settings={
        "shortcuts": [{"id": "abc123", "label": "Snip", "keys": "win+shift+s"}]})
    tid = st.shortcut_tool_id("abc123")
    assert tid in cfg["wheel"]["items"]
    out = FakeOut()
    e = Engine(cfg, out, FakeUI(), [FakeRot(), FakeSrc((Capability.CLICKS, Capability.HOLD))])
    e.handle(InputEvent(Kind.DOUBLE, 0, "t"))
    e.handle(InputEvent(Kind.ROTATE, e.wheel_ids.index(tid) - e.index, "t"))
    e.handle(InputEvent(Kind.CLICK, 0, "t"))
    assert ("keys", "win+shift+s") in out.log


def test_saved_order_keeps_shortcuts_where_the_user_put_them():
    base, _ = config_mod.load(platform="windows")
    tid = st.shortcut_tool_id("abc123")
    s = {"shortcuts": [{"id": "abc123", "label": "Snip", "keys": "win+shift+s"}],
         "wheel": {"order": [tid, "volume", "scroll"], "enabled": [tid, "scroll"]}}
    assert st.apply(base, s)["wheel"]["items"] == [tid, "scroll"]


def test_shortcut_without_keys_is_ignored():
    base, _ = config_mod.load(platform="windows")
    out = st.apply(base, {"shortcuts": [{"id": "x1", "label": "Empty", "keys": ""}]})
    assert st.shortcut_tool_id("x1") not in out["tools"]


def test_claude_shortcut_action_uses_the_setting():
    cfg, _ = config_mod.load(platform="windows", user_settings={"claude_shortcut": "ctrl+shift+space"})
    out = FakeOut()
    e = Engine(cfg, out, FakeUI(), [FakeRot(), FakeSrc((Capability.CLICKS, Capability.HOLD))])
    actions.parse("claude_shortcut")(e)
    assert ("keys", "ctrl+shift+space") in out.log


def test_zoom_is_off_by_default():
    cfg, _ = config_mod.load(platform="windows")
    assert "zoom" not in cfg["wheel"]["items"] and "zoom" in cfg["tools"]


def test_window_adds_records_and_removes_shortcuts(tmp_path):
    from PySide6.QtWidgets import QApplication
    from orbit.ui.settings_window import SettingsWindow
    QApplication.instance() or QApplication([])
    base, _ = config_mod.load(platform="windows")
    saved = []
    w = SettingsWindow(base, {}, True, "#7C9CFF", saved.append, settings_path=tmp_path / "s.json")
    w.add_shortcut()
    sid = next(iter(w.sc_rows))
    row = w.sc_rows[sid]
    row.label.setText("Snip")
    w.shortcut_renamed(sid)
    row.keys.setText("win+shift+s")
    w.claude_keys.setText("ctrl+shift+space")
    assert st.shortcut_tool_id(sid) in [t for t, *_ in w.preview.items]
    w.save()
    s = saved[-1]
    assert s["shortcuts"] == [{"id": sid, "label": "Snip", "keys": "win+shift+s"}]
    assert s["claude_shortcut"] == "ctrl+shift+space"
    assert st.shortcut_tool_id(sid) in s["wheel"]["enabled"]
    w2 = SettingsWindow(base, s, True, "#7C9CFF", saved.append, settings_path=tmp_path / "s.json")
    w2.remove_shortcut(sid)
    assert w2.collect()["shortcuts"] == [] and st.shortcut_tool_id(sid) not in w2.order


def test_window_keeps_old_gestures_and_saves_scroll_feel(tmp_path):
    from PySide6.QtWidgets import QApplication
    from orbit.ui.settings_window import SettingsWindow
    QApplication.instance() or QApplication([])
    base, _ = config_mod.load(platform="windows")
    saved = []
    w = SettingsWindow(base, {"gestures": {"triple": "launch:Spotify"}}, True, "#7C9CFF", saved.append,
                       settings_path=tmp_path / "s.json")
    w.fast_scroll.slider.setValue(round(2.5 / 0.5))
    w.save()
    s = saved[-1]
    assert s["gestures"] == {"triple": "launch:Spotify"}         # an older settings.json's choice survives a save
    assert s["scroll"]["max_gain"] == 2.5
    cfg = st.apply(base, s)
    assert cfg["tools"]["scroll"]["max_gain"] == 2.5
