"""App wiring: config -> platform sources/output -> engine <-> Qt UI.

Threading: sources fire from their own threads; the Bus hops every event onto
the Qt main thread, so the engine and UI never need locks.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QPointF, QTimer, Qt, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from orbit.core import config as config_mod
from orbit.core import settings as user_settings
from orbit.core.engine import Engine
from orbit.core.events import Capability, InputEvent
from orbit.platform import get_platform
from orbit.ui.qtui import QtUI

log = logging.getLogger("orbit")


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    d = Path(base) / "Orbit" if base else Path.home() / ".orbit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(debug: bool):
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname).1s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(data_dir() / "orbit.log", maxBytes=1_000_000, backupCount=2,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    for noisy in ("comtypes", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if sys.stdout:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)


class Bus(QObject):
    event = Signal(object)

    def post(self, ev: InputEvent):  # any thread
        self.event.emit(ev)


ICONS = Path(__file__).resolve().parent / "ui" / "icons"


def app_icon() -> QIcon:
    """The Orbit mark (rendered by tools/make_icon.py)."""
    return QIcon(str(ICONS / "orbit.png"))


def light_taskbar() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def tray_icon(accent: str, on: bool = True) -> QIcon:
    """The Orbit mark as a tray glyph: a ring with the lit item. macOS gets a template the
    menu bar tints; Windows a ring that contrasts with the taskbar (the full app icon is
    a dark tile that vanished on a dark taskbar, issue #2). Off = hollow, grey."""
    if sys.platform == "darwin" and (ICONS / "orbit_tray.png").exists():
        icon = QIcon(str(ICONS / "orbit_tray.png"))
        icon.setIsMask(True)
        return icon
    ink = QColor("#1B1E26") if light_taskbar() else QColor("#F4F6FB")
    dot = QColor(accent) if on else QColor("#8A8F9C")
    if not on:
        ink.setAlpha(150)
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        s = size / 32
        p.setPen(QPen(ink, 3.0 * s))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(16 * s, 16 * s), 12.2 * s, 12.2 * s)
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(16 * s + 7.2 * s * 0.643, 16 * s - 7.2 * s * 0.766), 4.4 * s, 4.4 * s)
        p.end()
        icon.addPixmap(pm)
    return icon


INSTANCE = f"orbit-{os.environ.get('USERNAME') or os.environ.get('USER') or 'user'}"


def ping_running(msg: str) -> bool:
    """Send `msg` to a running Orbit; True if one answered."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE)
    if not sock.waitForConnected(400):
        return False
    sock.write(msg.encode())
    sock.flush()
    sock.waitForBytesWritten(400)
    sock.disconnectFromServer()
    return True


def self_args(argv: list[str]) -> list[str]:
    """Arguments that start Orbit again: the packaged exe runs itself, a source checkout
    runs `python -m orbit`."""
    return list(argv) if getattr(sys, "frozen", False) else ["-m", "orbit", *argv]


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="orbit", description="Orbit: a wheel of tools you drive with any buttons")
    ap.add_argument("--config", help="path to config.toml")
    ap.add_argument("--no-elevate", action="store_true", help="don't ask for admin (press-and-hold stays off)")
    ap.add_argument("--dev", action="store_true", help="accept injected events on udp 127.0.0.1:47800")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--autostart", choices=("on", "off"), help="start with Windows (packaged app, set by the installer)")
    return ap.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    setup_logging(args.debug)

    # Already running? Ask it to open Settings and stop here: before the admin prompt,
    # so a second click on Orbit never asks for admin just to say "already running".
    if ping_running("show"):
        log.info("Orbit is already running: opened its Settings")
        return 0

    plat = get_platform()
    if not plat.is_elevated() and not args.no_elevate:
        log.info("asking for admin (needed to read press-and-hold)")
        if plat.relaunch_elevated(self_args(argv)):
            return 0
        log.warning("elevation declined — continuing without press-and-hold")

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Orbit")
    app.setWindowIcon(app_icon())

    lock = QLockFile(str(data_dir() / "orbit.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        ping_running("show")
        log.info("Orbit is already running: opened its Settings")
        return 0

    settings_now = user_settings.load()
    cfg, cfg_path = config_mod.load(args.config, user_settings=settings_now)
    log.info("config: %s (+ %s)", cfg_path, user_settings.path())

    sources = plat.create_sources(cfg)
    if args.dev:
        from orbit.platform.dev import UdpDevSource
        sources.append(UdpDevSource())
    out = plat.create_output(cfg)
    ui = QtUI(cfg)

    # Start sources first so the engine sees what actually works (e.g. falls back to
    # triple-press for the wheel when the hold sniffer can't start).
    bus = Bus()
    # Every input goes through the controls router: the buds' sources here, keyboard /
    # mouse hooks below. It turns them into the functions the user set up.
    from orbit.core.controls import Controls, Router, replay_with
    router = Router(bus.post, out.media)
    router.hub.replay = replay_with(out)
    router.set_controls(Controls.from_json(settings_now.get("controls")))

    def post(ev: InputEvent):
        router.from_source(ev)
        for src in sources:
            src.observe(ev)

    for s in sources:
        try:
            s.start(post)
            log.info("source up: %s%s", s.describe(), "" if s.available else " (unavailable)")
        except Exception:
            log.exception("source failed: %s", s.name)
    # The engine is rebuilt in place when settings change; everything holds `live`.
    live = {"engine": Engine(cfg, out, ui, sources)}
    engine = live["engine"]
    engine.set_volume_dial(router.hub.volume_is_dial())
    bus.event.connect(lambda ev: live["engine"].handle(ev), Qt.QueuedConnection)

    services = plat.create_services(cfg)
    for svc in services:
        try:
            svc.start()
        except Exception:
            log.exception("service failed: %s", type(svc).__name__)

    ticker = QTimer()
    ticker.setInterval(50)
    ticker.timeout.connect(lambda: live["engine"].tick())
    ticker.start()
    hub_ticker = QTimer()                     # holds, double taps, repeats: needs finer timing
    hub_ticker.setInterval(15)
    hub_ticker.timeout.connect(router.hub.tick)
    hub_ticker.start()

    key_capture = None
    try:
        key_capture = plat.create_key_capture(router)
        if key_capture:
            key_capture.start()
            log.info("key capture up: %s", key_capture.describe())
    except Exception:
        log.exception("key capture failed: keys and mouse buttons can't be controls")
        key_capture = None

    # ---- tray
    off_flag = data_dir() / "off"
    tray = QSystemTrayIcon(tray_icon(cfg["ui"]["accent"]))
    tray.setToolTip("Orbit: press your Open menu button to open the wheel")
    menu = QMenu()
    a_status = QAction("")
    a_status.setEnabled(False)
    a_on = QAction("Orbit on")
    a_on.setCheckable(True)

    def set_on(on: bool):
        router.paused = not on
        live["engine"].set_paused(not on)
        try:
            off_flag.unlink() if on else off_flag.write_text("off")
        except OSError:
            pass
        tray.setIcon(tray_icon(cfg["ui"]["accent"], on))
        tray.setToolTip("Orbit is on: press your Open menu button to open the wheel" if on else
                        "Orbit is off: every button works as normal")
        if a_on.isChecked() != on:
            a_on.setChecked(on)

    a_on.toggled.connect(set_on)

    def refresh_status():
        rot = [s for s in sources if hasattr(s, "level")]
        bound = bool(rot) and "no device" not in rot[0].describe()
        match = cfg["device"].get("audio_endpoint_match", "CMF Buds Pro 2")
        a_status.setText("Buds connected" if bound else f"Buds not connected (looking for '{match}')")

    menu.aboutToShow.connect(refresh_status)
    a_cfg = QAction("Open config")              # your overrides (a short stub on first open)
    a_cfg.triggered.connect(lambda: out.launch(str(config_mod.find(args.config))))
    a_log = QAction("Open log")
    a_log.triggered.connect(lambda: out.launch(str(data_dir() / "orbit.log")))
    a_wheel = QAction("Show wheel")
    a_wheel.triggered.connect(lambda: live["engine"].open_wheel())
    a_settings = QAction("Settings…")

    def apply_settings(new: dict):
        try:
            cfg2, _ = config_mod.load(args.config, user_settings=new)
        except Exception:
            log.exception("settings rejected; keeping the current ones")
            return
        old = live["engine"]
        if old.state.value == "wheel":
            ui.wheel_cancel()
        old.shutdown()
        ui.bridge.set_appearance(cfg2["ui"]["appearance"])
        paused = old.paused
        live["engine"] = Engine(cfg2, out, ui, sources)
        router.set_controls(Controls.from_json(new.get("controls")))
        live["engine"].set_volume_dial(router.hub.volume_is_dial())
        live["engine"].set_paused(paused)
        log.info("settings applied — wheel: %s, start: %s, wheel opens with: %s",
                 live["engine"].wheel_ids, live["engine"].tool.id, sorted(live["engine"].open_with))

    windows = []

    def open_settings():
        from orbit.ui.settings_window import SettingsWindow
        if windows and windows[0].isVisible():
            windows[0].raise_()
            windows[0].activateWindow()
            return
        base, _ = config_mod.load(args.config)
        e = live["engine"]
        has_hold = Capability.HOLD in e.caps or Capability.PRESS_RELEASE in e.caps
        w = SettingsWindow(base, user_settings.load(), has_hold, cfg["ui"]["accent"], apply_settings, router=router,
                           first_run_setup=True)
        windows[:] = [w]
        w.show()
        w.raise_()
        w.activateWindow()

    a_settings.triggered.connect(open_settings)
    a_restart = QAction("Restart (reload config)")
    a_quit = QAction("Quit")
    a_quit.triggered.connect(app.quit)

    def restart():
        shutdown()  # release the ETW session + lock before the new instance claims them
        import subprocess
        extra = [] if plat.is_elevated() or "--no-elevate" in argv else ["--no-elevate"]
        subprocess.Popen([sys.executable, *self_args([*extra, *argv])],
                         creationflags=0x08000000 if sys.platform == "win32" else 0)
        app.quit()

    a_restart.triggered.connect(restart)

    # live toggles
    toggles = []
    for svc in services:
        if getattr(svc, "toggle_label", None):
            a = QAction(svc.toggle_label)
            a.setCheckable(True)
            a.setChecked(svc.enabled)
            a.toggled.connect(lambda on, s=svc: setattr(s, "enabled", on))
            toggles.append(a)
    if sys.platform == "win32":
        from orbit.platform.windows import autostart
        if autostart.available() and plat.is_elevated():
            if args.autostart:
                autostart.set_enabled(args.autostart == "on")
            a_auto = QAction("Start with Windows")
            a_auto.setCheckable(True)
            a_auto.setChecked(autostart.enabled())
            a_auto.toggled.connect(lambda on: autostart.set_enabled(on) or a_auto.setChecked(autostart.enabled()))
            toggles.append(a_auto)

    menu.addAction(a_status)
    menu.addAction(a_on)
    menu.addSeparator()
    for a in (a_settings, a_wheel, a_cfg, a_log, a_restart):
        menu.addAction(a)
    menu.addSeparator()
    for a in toggles:
        menu.addAction(a)
    menu.addSeparator()
    menu.addAction(a_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: open_settings() if reason == QSystemTrayIcon.Trigger else None)
    tray.show()
    a_on.setChecked(not off_flag.exists())
    set_on(not off_flag.exists())

    # a second launch (Start menu, desktop shortcut) shows Settings instead of nothing
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.WorldAccessOption)   # the second launch isn't elevated yet
    QLocalServer.removeServer(INSTANCE)

    def on_ping():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            if bytes(conn.readAll()).strip() == b"show":
                open_settings()
        conn.readyRead.connect(read)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_ping)
    if not server.listen(INSTANCE):
        log.warning("single-instance channel unavailable: %s", server.errorString())

    # first run: say where Orbit lives, and open Settings so there's something to see
    welcomed = data_dir() / "welcomed"
    if not welcomed.exists():
        where = "in the system tray (click ^ by the clock if you don't see it)" if sys.platform == "win32" \
            else "in the menu bar"
        QTimer.singleShot(1500, lambda: tray.showMessage(
            "Orbit is running", f"It lives {where}. Press your Open menu button to open the wheel.",
            app_icon(), 8000))
        QTimer.singleShot(1800, open_settings)
        try:
            welcomed.write_text("1")
        except OSError:
            pass

    done = []

    def shutdown():
        if done:
            return
        done.append(True)
        live["engine"].shutdown()
        for s in [*sources, *services, *([key_capture] if key_capture else [])]:
            try:
                s.stop()
            except Exception:
                pass
        lock.unlock()

    app.aboutToQuit.connect(shutdown)
    log.info("Orbit running — tool: %s, wheel: %s, caps: %s", engine.tool.id, engine.wheel_ids,
             sorted(c.value for c in engine.caps))
    return app.exec()
