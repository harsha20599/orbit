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

    private fun rec(vararg p: Press, repeat: Boolean = false) = PressRecognizer(p.toSet(), repeat) { got += it }

    private fun PressRecognizer.press(ms: Long = 60, gap: Long = 0) {
        down(now); repeat((ms / 10).toInt()) { now += 10; tick(now) }; up(now)
        repeat((gap / 10).toInt()) { now += 10; tick(now) }
    }

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
        r.press(80); assertEquals(listOf(Press.TAP), got)            // on release, no gap wait
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

    @Test fun defaultsByButtonCount() {
        fun ins(n: Int) = (1..n).map { Input("key:$it", "K$it") }
        fun cfg(n: Int) = Config("a", "A", "d", ins(n), Config.defaults(ins(n)))
        assertEquals(Trigger("key:1", Press.TAP), cfg(1).triggerFor(OrbitActions.FORWARD))
        assertEquals(Trigger("key:1", Press.HOLD), cfg(1).triggerFor(OrbitActions.OPEN))
        assertEquals(Trigger("key:1", Press.DOUBLE), cfg(1).triggerFor(OrbitActions.SELECT))
        assertEquals(Trigger("key:2", Press.TAP), cfg(2).triggerFor(OrbitActions.BACK))
        assertEquals(Trigger("key:2", Press.HOLD), cfg(2).triggerFor(OrbitActions.OPEN))
        assertEquals(Trigger("key:4", Press.TAP), cfg(4).triggerFor(OrbitActions.OPEN))
        for (n in 1..4) {
            assertTrue("$n buttons can open the wheel", cfg(n).triggerFor(OrbitActions.OPEN) != null)
            assertTrue("$n buttons can select", cfg(n).triggerFor(OrbitActions.SELECT) != null)
        }
    }

    @Test fun everyPresetOpensTheWheel() {
        Presets.ALL.forEach { p -> assertTrue(p.name, Config.headphones(p).triggerFor(OrbitActions.OPEN) != null) }
        assertTrue(Config.backTap("b").triggerFor(OrbitActions.SELECT) != null)
    }

    @Test fun cmfPresetMatchesTheBudsGestures() {
        val c = Config.headphones(Presets.CMF)
        assertEquals(OrbitActions.OPEN, c.actionFor(Presets.NEXT, Press.TAP))
        assertEquals(OrbitActions.FORWARD, c.actionFor(Presets.UP, Press.TAP))
        assertEquals(OrbitActions.SELECT, c.actionFor(Presets.PLAY, Press.TAP))
    }

    @Test fun bindingMovesATriggerAndReportsWhoLostIt() {
        val c = Config.keys("a", "A", "d", listOf(Input("key:1", "A"), Input("key:2", "B")))
        val (c2, lost) = c.bind(OrbitActions.SELECT, Trigger("key:2", Press.TAP))       // B tap was "back"
        assertEquals(OrbitActions.BACK, lost)
        assertNull(c2.triggerFor(OrbitActions.BACK))
        assertEquals(OrbitActions.SELECT, c2.actionFor("key:2", Press.TAP))
        val (c3, _) = c2.bind(OrbitActions.SELECT, null)
        assertNull(c3.triggerFor(OrbitActions.SELECT))
    }

    @Test fun removingAButtonDropsItsBindings() {
        val c = Config.keys("a", "A", "d", listOf(Input("key:1", "A"), Input("key:2", "B")))
        val c2 = c.withInputs(listOf(Input("key:1", "A")))
        assertTrue(c2.bindings.all { it.trigger.input == "key:1" })
    }

    @Test fun hubRoutesByDeviceAndSwallowsOnlyItsButtons() {
        val events = mutableListOf<DialEvent>()
        val hub = ConfigHub { events += it }
        hub.set(listOf(Config.keys("a", "Remote", "remote", listOf(Input("key:24", "Vol+"))),
            Config.phoneVolumeKeys("p")))
        assertTrue(hub.onKey("remote", "key:24", true, now)); hub.onKey("remote", "key:24", false, now + 40)
        assertTrue(hub.onKey(Config.BUILTIN, "key:24", true, now)); hub.onKey(Config.BUILTIN, "key:24", false, now + 40)
        hub.tick(now + 400)                                   // 1-button remote: its tap waits for a possible double
        assertFalse(hub.onKey("remote", "key:66", true, now))
        assertFalse(hub.onKey("other", "key:24", true, now))
        assertEquals(listOf(1, 1), events.map { it.delta })
        assertEquals(setOf(CONTROLLER + "Remote", CONTROLLER + "Phone volume keys"), events.map { it.source }.toSet())
    }

    @Test fun pulsesUseTheirTapBindingWithCount() {
        val events = mutableListOf<DialEvent>()
        val hub = ConfigHub { events += it }
        hub.set(listOf(Config.headphones(Presets.CMF)))
        assertTrue(hub.pulse(Config.HEADPHONES, Presets.UP, 3, "android-volume"))
        assertTrue(hub.pulse(Config.HEADPHONES, Presets.NEXT))
        assertEquals(DialEvent(Kind.ROTATE, 3, "android-volume", now), events[0])
        assertEquals(OrbitActions.OPEN, events[1].action)
        assertTrue(hub.volumeIsDial())
        hub.set(listOf(Config.headphones(Presets.EARBUDS)))
        assertFalse(hub.volumeIsDial())
        assertFalse(hub.pulse(Config.HEADPHONES, Presets.UP))
    }

    @Test fun disabledConfigsDoNothing() {
        val hub = ConfigHub { }
        hub.set(listOf(Config.phoneVolumeKeys("p").copy(enabled = false)))
        assertFalse(hub.onKey(Config.BUILTIN, "key:24", true, now))
    }
}
