"""macOS: keys, media keys and mouse buttons as Orbit controls.

A Quartz event tap (session level, can drop events) on its own run-loop thread. A key
or button a control uses is swallowed and handed to the controls router; everything
else passes untouched. Events Orbit posts itself carry ORBIT_EVENT in their user-data
field (orbit/platform/mac/output.py), so Orbit can't trigger itself. Media keys arrive
as NSSystemDefined events; the tap sees those too.

Needs the Accessibility permission Orbit already asks for. macOS switches a tap off if
its callback is slow or the user's input is blocked; the callback re-enables it.
"""
from __future__ import annotations

import logging
import threading

from orbit.platform.mac.keytap import KEY_NAMES, TapTracker, mods_of, system_key

log = logging.getLogger("orbit.keys")

ORBIT_EVENT = 0x4F52_4254          # "ORBT": Orbit's own synthetic events
NX_SYSDEFINED = 14


class MacKeyCapture:
    def __init__(self, router):
        self.router = router
        self.tracker = TapTracker(router.wants, router.key)
        self._tap = None
        self._loop = None
        self._ready = threading.Event()

    def describe(self):
        return "event tap " + ("up" if self._tap is not None else "unavailable (Accessibility?)")

    def start(self):
        threading.Thread(target=self._run, name="key-tap", daemon=True).start()
        self._ready.wait(2.0)

    def stop(self):
        if self._loop is not None:
            import Quartz as Q
            Q.CFRunLoopStop(self._loop)

    def _run(self):
        import Quartz as Q
        mask = (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp) |
                Q.CGEventMaskBit(Q.kCGEventOtherMouseDown) | Q.CGEventMaskBit(Q.kCGEventOtherMouseUp) |
                (1 << NX_SYSDEFINED))
        self._tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionDefault,
                                       mask, self._on_event, None)
        if self._tap is None:
            log.error("event tap refused: allow Orbit in System Settings → Privacy & Security → Accessibility")
            self._ready.set()
            return
        src = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, src, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        self._ready.set()
        Q.CFRunLoopRun()

    def _on_event(self, proxy, etype, event, refcon):
        import Quartz as Q
        try:
            if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                Q.CGEventTapEnable(self._tap, True)
                return event
            if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData) == ORBIT_EVENT:
                return event
            if etype in (Q.kCGEventKeyDown, Q.kCGEventKeyUp):
                name = KEY_NAMES.get(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode))
                if name:
                    rep = bool(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat))
                    if self.tracker.key(name, mods_of(Q.CGEventGetFlags(event)), etype == Q.kCGEventKeyDown, rep):
                        return None
            elif etype == NX_SYSDEFINED:
                from AppKit import NSEvent
                ns = NSEvent.eventWithCGEvent_(event)
                k = system_key(ns.subtype(), ns.data1()) if ns is not None else None
                if k and self.tracker.key(k[0], set(), k[1], k[2]):
                    return None
            elif etype in (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp):
                b = Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventButtonNumber)
                if self.tracker.mouse(b, etype == Q.kCGEventOtherMouseDown):
                    return None
        except Exception:
            log.exception("event tap")
        return event
