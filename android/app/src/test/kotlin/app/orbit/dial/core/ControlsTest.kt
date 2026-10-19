package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ControlsTest {
    private var now = 1_000L
    private val got = mutableListOf<Act>()

    @Before fun clock() { Clock.now = { now } }

    private fun rec(n: Int) = ButtonRecognizer(Controller.layout((1..n).map { it to "K$it" })) { a, _ -> got += a }

    private fun ButtonRecognizer.press(key: Int, ms: Long) {
        down(key, now)
        val end = now + ms
        while (now < end) { now += 10; tick(now) }
        up(key, now)
    }

    @Test fun layoutsByButtonCount() {
        val one = Controller.layout(listOf(1 to "a"))
        assertEquals(Act.NEXT, one[0].tap); assertEquals(Act.SELECT, one[0].hold); assertEquals(Act.MENU, one[0].longHold)
        val two = Controller.layout(listOf(1 to "a", 2 to "b"))
        assertEquals(listOf(Act.NEXT, Act.PREV), two.map { it.tap })
        assertEquals(listOf(Act.SELECT, Act.MENU), two.map { it.hold })
        val four = Controller.layout((1..6).map { it to "k" })
        assertEquals(4, four.size)
        assertEquals(listOf(Act.NEXT, Act.PREV, Act.SELECT, Act.BACK), four.map { it.tap })
        assertTrue(four[0].repeat && four[1].repeat)
    }

    @Test fun singleSwitchTapHoldLongHold() {
        val r = rec(1)
        r.press(1, 120); assertEquals(listOf(Act.NEXT), got)
        got.clear(); r.press(1, 700); assertEquals(listOf(Act.SELECT), got)
        got.clear(); r.press(1, 1500); assertEquals(listOf(Act.MENU), got)
    }

    @Test fun longHoldFiresWithoutWaitingForRelease() {
        val r = rec(1)
        r.down(1, now)
        now += ButtonRecognizer.LONG_MS; r.tick(now)
        assertEquals(listOf(Act.MENU), got)
        now += 2000; r.up(1, now)
        assertEquals(listOf(Act.MENU), got)          // nothing more on release
    }

    @Test fun twoButtonsHoldFiresAtThreshold() {
        val r = rec(2)
        r.down(2, now)
        now += ButtonRecognizer.HOLD_MS - 10; r.tick(now)
        assertTrue(got.isEmpty())
        now += 10; r.tick(now)
        assertEquals(listOf(Act.MENU), got)
        r.up(2, now + 50)
        r.press(1, 80)
        assertEquals(listOf(Act.MENU, Act.NEXT), got)
    }

    @Test fun threeButtonsArrowsFireOnDownAndRepeat() {
        val r = rec(3)
        r.down(1, now)
        assertEquals(listOf(Act.NEXT), got)            // instant, no wait for release
        now += ButtonRecognizer.REPEAT_DELAY_MS + 2 * ButtonRecognizer.REPEAT_EVERY_MS; r.tick(now)
        assertEquals(4, got.size)
        r.up(1, now)
        now += 1000; r.tick(now)
        assertEquals(4, got.size)
    }

    @Test fun osAutoRepeatDownsAreIgnored() {
        val r = rec(3)
        r.down(2, now); r.down(2, now + 30); r.down(2, now + 60)
        assertEquals(listOf(Act.PREV), got)
    }

    @Test fun unknownKeysPassThrough() {
        val r = rec(2)
        assertFalse(r.down(99, now)); assertFalse(r.up(99, now))
        assertTrue(got.isEmpty())
    }

    @Test fun nextWakeTracksDeadlines() {
        val r = rec(1)
        assertNull(r.nextWake())
        r.down(1, now)
        assertEquals(now + ButtonRecognizer.LONG_MS, r.nextWake())
    }

    @Test fun hubRoutesByDeviceThenAnyDevice() {
        val events = mutableListOf<DialEvent>()
        val hub = ControllerHub { events += it }
        hub.set(listOf(
            Controller("a", "Remote", "dev-remote", Controller.layout(listOf(24 to "Vol+"))),
            Controller("b", "Any keyboard", null, Controller.layout(listOf(24 to "Vol+", 25 to "Vol-"))),
        ))
        assertTrue(hub.onKey("dev-remote", 24, true, now)); hub.onKey("dev-remote", 24, false, now + 50)
        assertTrue(hub.onKey("dev-other", 24, true, now + 100)); hub.onKey("dev-other", 24, false, now + 150)
        assertFalse(hub.onKey("dev-other", 66, true, now))
        assertEquals(listOf(1, 1), events.map { it.delta })
        assertEquals(listOf("controller:Remote", "controller:Any keyboard"), events.map { it.source })
    }

    @Test fun disabledControllersDoNothing() {
        val hub = ControllerHub { }
        hub.set(listOf(Controller("a", "R", null, Controller.layout(listOf(24 to "v")), enabled = false)))
        assertFalse(hub.onKey(null, 24, true, now))
        assertTrue(hub.isEmpty())
    }

    @Test fun actsMapToDialEvents() {
        assertEquals(Kind.ROTATE, Act.NEXT.event("s", 0)!!.kind)
        assertEquals(-1, Act.PREV.event("s", 0)!!.delta)
        assertEquals(Kind.CLICK, Act.SELECT.event("s", 0)!!.kind)
        assertEquals(Kind.DOUBLE, Act.MENU.event("s", 0)!!.kind)
        assertNull(Act.NONE.event("s", 0))
    }

    private fun TapCounter.tap(ms: Long = 80, gap: Long = 120) {
        down(now); repeat((ms / 10).toInt()) { now += 10; tick(now) }; up(now)
        repeat((gap / 10).toInt()) { now += 10; tick(now) }
    }

    @Test fun headsetHookCountsTapsAndHolds() {
        val kinds = mutableListOf<Kind>()
        val t = TapCounter { kinds += it }
        t.tap(gap = 400); assertEquals(listOf(Kind.CLICK), kinds)
        kinds.clear(); t.tap(); t.tap(gap = 400); assertEquals(listOf(Kind.DOUBLE), kinds)
        kinds.clear(); t.tap(); t.tap(); t.tap(gap = 0); assertEquals(listOf(Kind.TRIPLE), kinds)   // no wait after the third
        kinds.clear(); t.tap(ms = 900, gap = 400); assertEquals(listOf(Kind.HOLD), kinds)
    }
}
