package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ControlsTest {
    private var now = 1_000L
    private val got = mutableListOf<Press>()

    @Before fun clock() { Clock.now = { now } }

    private fun rec(vararg p: Press, repeat: Boolean = false) = PressRecognizer(p.toSet(), repeat, emit = { got += it })

    private fun PressRecognizer.press(ms: Long = 60, gap: Long = 0) {
        down(now); repeat((ms / 10).toInt()) { now += 10; tick(now) }; up(now)
        repeat((gap / 10).toInt()) { now += 10; tick(now) }
    }

    // ---------------------------------------------------------------- presses

    @Test fun tapOnlyFiresOnKeyDown() {
        val r = rec(Press.TAP)
        r.down(now)
        assertEquals(listOf(Press.TAP), got)
        r.up(now + 50)
        assertEquals(listOf(Press.TAP), got)
    }

    @Test fun movesRepeatWhileHeld() {
        val r = rec(Press.TAP, repeat = true)
        r.down(now)
        now += PressRecognizer.REPEAT_DELAY_MS + 2 * PressRecognizer.REPEAT_EVERY_MS; r.tick(now)
        assertEquals(4, got.size)
        r.up(now); now += 1000; r.tick(now)
        assertEquals(4, got.size)
    }

    @Test fun tapAndHoldNeedNoWaitAfterRelease() {
        val r = rec(Press.TAP, Press.HOLD)
        r.press(80); assertEquals(listOf(Press.TAP), got)
        got.clear(); r.down(now); now += PressRecognizer.HOLD_MS; r.tick(now)
        assertEquals(listOf(Press.HOLD), got)                          // at the threshold, before release
        r.up(now + 500); assertEquals(listOf(Press.HOLD), got)
    }

    @Test fun doubleAndTripleCount() {
        val r = rec(Press.TAP, Press.DOUBLE, Press.TRIPLE)
        r.press(gap = 400); assertEquals(listOf(Press.TAP), got)
        got.clear(); r.press(gap = 100); r.press(gap = 400); assertEquals(listOf(Press.DOUBLE), got)
        got.clear(); r.press(gap = 100); r.press(gap = 100); r.press(); assertEquals(listOf(Press.TRIPLE), got)  // no wait after the 3rd
    }

    @Test fun doubleOnlyIgnoresSinglesAndFiresOnSecondRelease() {
        val r = rec(Press.DOUBLE)
        r.press(gap = 400); assertTrue(got.isEmpty())
        r.press(gap = 100); r.press(); assertEquals(listOf(Press.DOUBLE), got)
    }

    @Test fun osKeyRepeatIgnored() {
        val r = rec(Press.TAP)
        r.down(now); r.down(now + 30); r.down(now + 60)
        assertEquals(1, got.size)
    }

    // ---------------------------------------------------------------- controls

    @Test fun everyPresetHasTheFourFunctions() {
        Presets.ALL.forEach { p ->
            listOf(OrbitActions.OPEN, OrbitActions.SELECT, OrbitActions.FORWARD).forEach { a ->
                assertTrue("${p.name}: $a", p.controls.triggers(a).isNotEmpty())
            }
        }
    }

    @Test fun addingATriggerMovesItAndSaysFromWhere() {
        val c = Presets.VOLUME_KEYS.controls
        val (c2, lost) = c.add(OrbitActions.SELECT, Trigger("key:24"))       // Volume + tap was "Move right"
        assertEquals(OrbitActions.FORWARD, lost)
        assertTrue(c2.triggers(OrbitActions.FORWARD).isEmpty())
        assertTrue(Trigger("key:24") in c2.triggers(OrbitActions.SELECT))
        assertNull(c2.preset)                                                  // no longer the preset as shipped
    }

    @Test fun aFunctionCanHaveSeveralTriggers() {
        var c = Presets.CMF.controls
        c = c.add(OrbitActions.FORWARD, Trigger("key:24")).first
        assertEquals(2, c.triggers(OrbitActions.FORWARD).size)
        c = c.remove(OrbitActions.FORWARD, Trigger("vol:up"))
        assertEquals(listOf(Trigger("key:24")), c.triggers(OrbitActions.FORWARD))
    }

    @Test fun countedInputsAreAlwaysTaps() {
        val (c, _) = Controls(emptyList()).add(OrbitActions.OPEN, Trigger("backtap:1", Press.HOLD))
        assertEquals(Press.TAP, c.triggers(OrbitActions.OPEN).single().press)
    }

    @Test fun labels() {
        assertEquals("Volume + · double tap", Trigger("key:24", Press.DOUBLE).label())
        assertEquals("Ctrl+Shift+Space · tap", Trigger("key:62+ctrl+shift").label())
        assertEquals("Back double tap", Trigger("backtap:1").label())
        assertEquals("Enter · hold on K380", Trigger("key:66", Press.HOLD, "dev", "K380").label())
    }

    // ---------------------------------------------------------------- hub

    @Test fun hubSwallowsOnlyItsKeysAndPrefersTheRecordedDevice() {
        val events = mutableListOf<DialEvent>()
        val hub = ControlsHub { events += it }
        hub.set(Controls(listOf(
            Binding(OrbitActions.FORWARD, Trigger("key:24")),                              // any device
            Binding(OrbitActions.SELECT, Trigger("key:66", Press.TAP, "k380", "K380")),    // that keyboard only
        )))
        assertTrue(hub.onKey("builtin", "key:24", true, now))
        assertTrue(hub.onKey("selfie", "key:24", true, now + 1)); hub.onKey("selfie", "key:24", false, now + 2)
        assertTrue(hub.onKey("k380", "key:66", true, now))
        assertFalse(hub.onKey("other-keyboard", "key:66", true, now))
        assertFalse(hub.onKey("builtin", "key:25", true, now))
        assertEquals(listOf(1, 1), events.filter { it.kind == Kind.ROTATE }.map { it.delta })
        assertEquals(1, events.count { it.action == OrbitActions.SELECT })
    }

    @Test fun shortcutsMatchExactly() {
        val hub = ControlsHub { }
        hub.set(Controls(listOf(Binding(OrbitActions.OPEN, Trigger("key:62+ctrl")))))
        assertTrue(hub.has(null, "key:62+ctrl"))
        assertFalse(hub.has(null, "key:62"))                                   // plain Space still types
    }

    @Test fun mixedSourcesInOneSetup() {
        val events = mutableListOf<DialEvent>()
        val hub = ControlsHub { events += it }
        hub.set(Presets.VOLUME_BACKTAP.controls)
        assertTrue(hub.pulse("backtap:2"))
        assertEquals(OrbitActions.OPEN, events.last().action)
        assertTrue(hub.pulse("backtap:1"))
        assertEquals(OrbitActions.SELECT, events.last().action)
        assertFalse(hub.pulse("media:play"))                                   // not in this setup: music keeps playing
        assertFalse(hub.volumeIsDial())
    }

    @Test fun dialTurnsCarryTheirCount() {
        val events = mutableListOf<DialEvent>()
        val hub = ControlsHub { events += it }
        hub.set(Presets.CMF.controls)
        hub.pulse("vol:up", 3, "android-volume")
        assertEquals(DialEvent(Kind.ROTATE, 3, "android-volume", now), events.single())
        assertTrue(hub.volumeIsDial())
    }

    @Test fun cableButtonCountsTapsDoublesHolds() {
        val events = mutableListOf<DialEvent>()
        val hub = ControlsHub { events += it }
        hub.set(Presets.WIRED.controls)
        hub.onKey("headphones", "media:hook", true, now); hub.onKey("headphones", "media:hook", false, now + 60)
        hub.onKey("headphones", "media:hook", true, now + 120); hub.onKey("headphones", "media:hook", false, now + 180)
        assertEquals(OrbitActions.SELECT, events.single().action)              // double = select, no wait after the 2nd
    }

    @Test fun presetsHaveOnlyTheFourFunctions() {
        (Presets.ALL + Presets.BACKTAP).forEach { p ->
            assertTrue(p.name, p.controls.bindings.all { it.action in OrbitActions.CORE })
        }
    }

    @Test fun earbudsPlusVolumeKeysKeepsBoth() {
        val c = Presets.combine(Presets.CMF, Presets.VOLUME_KEYS)
        assertEquals(2, c.triggers(OrbitActions.FORWARD).size)                 // dial forward, Volume +
        assertTrue(c.uses("media:") && c.uses("key:24"))
        assertFalse(c.uses("media:hold"))                                       // no hold, so no voice-command permission
        assertNull(c.preset)
        assertEquals(Presets.CMF.id, Presets.combine(Presets.CMF).preset)
    }
}
