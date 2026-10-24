"""macOS: keys, media keys and mouse buttons as Orbit controls.

A Quartz event tap (session level, can drop events) on its own run-loop thread. A key
or button a control uses is swallowed and handed to the controls router; everything
else passes untouched. Events Orbit posts itself carry ORBIT_EVENT in their user-data
field (orbit/platform/mac/output.py), so Orbit can't trigger itself. Media keys arrive
as NSSystemDefined events; the tap sees those too.

Needs the Accessibility permission Orbit already asks for. macOS switches a tap off if
its callback is slow or the user's input is blocked; the callback re-enables it.

Keeping it working (Hammerspoon, MiddleClick and Mac Mouse Fix hit all of these):
  - A watchdog every WATCH_S re-enables a tap macOS switched off without telling us.
  - Permission granted after Orbit started: the watchdog creates the tap then.
  - Permission removed while running: AXIsProcessTrusted keeps saying yes, so the
    watchdog tries creating a throwaway listen-only tap; when that fails, Orbit's own tap
    is torn down at once (a dead active tap can leave clicks blocked system-wide).
  - Secure Input (a password field, some apps leak it): keyboard events stop reaching
    taps and key-ups get lost, so held keys are let go and it is logged once.
  - The tap, its run-loop source and the callback are kept referenced (PyObjC would
    otherwise free them and the tap silently stops).
"""
from __future__ import annotations

import logging
import threading

from orbit.platform.mac.keytap import (KEY_NAMES, Gestures, ScrollNotches, TapTracker, mods_of, swipe_input,
                                       system_key)

log = logging.getLogger("orbit.keys")

ORBIT_EVENT = 0x4F52_4254          # "ORBT": Orbit's own synthetic events
WATCH_S = 3.0
NX_SYSDEFINED = 14
# NSEvent types the tap also sees (trackpad)
EV_ROTATE, EV_MAGNIFY, EV_SWIPE, EV_SMART_MAGNIFY, EV_SCROLL = 18, 30, 31, 32, 22


class MacKeyCapture:
    def __init__(self, router):
        self.router = router
        self.tracker = TapTracker(router.wants, router.key)
        self.gestures = Gestures()
        self.notches = ScrollNotches()
        self._tap = None
        self._src = None
        self._loop = None
        self._cb = self._on_event          # referenced for as long as the tap lives
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._secure = False
        self.rebuilds = 0

    def describe(self):
        return "event tap " + ("up" if self._tap is not None else "unavailable (Accessibility?)")

    def start(self):
        threading.Thread(target=self._run, name="key-tap", daemon=True).start()
        self._ready.wait(2.0)

    def stop(self):
        self._stop.set()
        if self._loop is not None:
            import Quartz as Q
            Q.CFRunLoopStop(self._loop)

    @staticmethod
    def _mask():
        import Quartz as Q
        return (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp) |
                Q.CGEventMaskBit(Q.kCGEventOtherMouseDown) | Q.CGEventMaskBit(Q.kCGEventOtherMouseUp) |
                (1 << NX_SYSDEFINED) | (1 << EV_SCROLL) | (1 << EV_ROTATE) | (1 << EV_MAGNIFY) |
                (1 << EV_SWIPE) | (1 << EV_SMART_MAGNIFY))

    def _create(self) -> bool:
        """Make the tap and add it to the tap thread's run loop (callable from any thread)."""
        import Quartz as Q
        tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionDefault,
                                 self._mask(), self._cb, None)
        if tap is None:
            return False
        src = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
        Q.CFRunLoopAddSource(self._loop, src, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(tap, True)
        Q.CFRunLoopWakeUp(self._loop)
        self._tap, self._src = tap, src
        return True

    def _teardown(self):
        import Quartz as Q
        tap, src, self._tap, self._src = self._tap, self._src, None, None
        if tap is not None:
            Q.CGEventTapEnable(tap, False)
            if src is not None:
                Q.CFRunLoopRemoveSource(self._loop, src, Q.kCFRunLoopCommonModes)
            Q.CFMachPortInvalidate(tap)
        self.release_all()

    def release_all(self):
        self.tracker.release_all()
        self.router.hub.release_all()

    def _run(self):
        import Quartz as Q
        self._loop = Q.CFRunLoopGetCurrent()
        if not self._create():
            log.error("event tap refused: allow Orbit in System Settings → Privacy & Security → Accessibility "
                      "(Orbit picks it up once allowed)")
        threading.Thread(target=self._watch, name="key-tap-watch", daemon=True).start()
        self._ready.set()
        # a run loop with no sources returns at once: keep it alive until the tap arrives
        while not self._stop.is_set():
            Q.CFRunLoopRunInMode(Q.kCFRunLoopDefaultMode, 1.0, False)

    @staticmethod
    def _permitted() -> bool:
        """Try a throwaway listen-only tap: the only reliable test (AXIsProcessTrusted lies
        after the permission is removed)."""
        import Quartz as Q
        t = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGTailAppendEventTap, Q.kCGEventTapOptionListenOnly,
                               Q.CGEventMaskBit(Q.kCGEventKeyDown), lambda *a: a[2], None)
        if t is None:
            return False
        Q.CFMachPortInvalidate(t)
        return True

    @staticmethod
    def secure_input() -> bool:
        try:
            import ctypes
            carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
            return bool(carbon.IsSecureEventInputEnabled())
        except Exception:
            return False

    def _watch(self):
        import Quartz as Q
        while not self._stop.wait(WATCH_S):
            try:
                if not self._permitted():
                    if self._tap is not None:
                        log.warning("Accessibility permission gone: event tap removed (allow Orbit again to resume)")
                        self._teardown()
                    continue
                if self._tap is None:
                    if self._create():
                        self.rebuilds += 1
                        log.info("event tap up (permission allowed)")
                    continue
                if not Q.CGEventTapIsEnabled(self._tap):
                    Q.CGEventTapEnable(self._tap, True)
                    log.info("event tap was off: switched back on")
                secure = self.secure_input()
                if secure and not self._secure:
                    self.release_all()
                    log.warning("Secure Input is on (a password field or an app holding it): keys can't reach "
                                "Orbit until it ends")
                elif not secure and self._secure:
                    log.info("Secure Input ended")
                self._secure = secure
            except Exception:
                log.exception("event tap watchdog")

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
            elif etype == EV_SCROLL:
                mods = mods_of(Q.CGEventGetFlags(event))
                if mods:
                    v = Q.CGEventGetDoubleValueField(event, Q.kCGScrollWheelEventFixedPtDeltaAxis1)
                    h = Q.CGEventGetDoubleValueField(event, Q.kCGScrollWheelEventFixedPtDeltaAxis2)
                    coasting = bool(Q.CGEventGetIntegerValueField(event, Q.kCGScrollWheelEventMomentumPhase))
                    inp, n = self.notches.feed(v, h, mods, momentum=coasting)
                    if inp and self.router.wants_gesture(inp):
                        for _ in range(n):
                            self.router.gesture(inp)
                        return None
            elif etype in (EV_MAGNIFY, EV_ROTATE, EV_SWIPE, EV_SMART_MAGNIFY):
                if self._gesture(etype, event):
                    return None
            elif etype in (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp):
                b = Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventButtonNumber)
                if self.tracker.mouse(b, etype == Q.kCGEventOtherMouseDown):
                    return None
        except Exception:
            log.exception("event tap")
        return event

    def _gesture(self, etype, event) -> bool:
        """True = swallow (a control uses this kind of gesture, so apps don't zoom / rotate too)."""
        from AppKit import NSEvent
        ns = NSEvent.eventWithCGEvent_(event)
        if ns is None:
            return False
        r = self.router
        if etype == EV_MAGNIFY:
            g = self.gestures.magnify(ns.magnification(), ns.phase())
            ours = r.wants_gesture("touchpad:pinch-in") or r.wants_gesture("touchpad:pinch-out")
        elif etype == EV_ROTATE:
            g = self.gestures.rotate(ns.rotation(), ns.phase())
            ours = r.wants_gesture("touchpad:rotate-left") or r.wants_gesture("touchpad:rotate-right")
        elif etype == EV_SWIPE:
            g = swipe_input(ns.deltaX(), ns.deltaY())
            ours = bool(g) and r.wants_gesture(g)
        else:
            g, ours = "touchpad:smart-zoom", r.wants_gesture("touchpad:smart-zoom")
        if g and r.wants_gesture(g):
            r.gesture(g)
        return ours
