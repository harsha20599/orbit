package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Where triggers break in real life: ups that never come, modifiers let go first, the OS
 * repeating a held key, settings saved mid-press, two remotes at once, presses right on
 * the timing edges. Each test is one of those.
 */
class TriggerEdgeTest {
    private var now = 1_000L
    private val events = mutableListOf<DialEvent>()
    private val hub = ControlsHub { events += it }
    private val pairing = KeyPairing()

    @Before fun clock() { Clock.now = { now } }

    private fun bind(vararg b: Pair<String, Trigger>) =
        hub.set(Controls(b.map { (action, t) -> Binding(action, t) }))

    /** One key event the way the accessibility service passes it on. True = swallowed. */
    private fun key(code: Int, input: String?, down: Boolean, device: String = "kbd") =
        pairing.onKey(device, code, input, down) { inp, d -> hub.onKey(device, inp, d, now) }

    private fun pass(ms: Long) { val end = now + ms; while (now < end) { now += 10; hub.tick(now) } }
    private fun moves() = events.filter { it.kind == Kind.ROTATE }.sumOf { it.delta }
    private fun actions() = events.mapNotNull { it.action }

    // ---------------------------------------------------------------- ups that go astray

    @Test fun modifierLetGoFirstStillPairsTheUp() {
        bind(OrbitActions.FORWARD to Trigger("key:30+ctrl"))
        assertTrue(key(30, "key:30+ctrl", true))
        assertTrue(key(30, "key:30", false))                 // ctrl already up: the up reads without it
        pass(3_000)
        assertEquals(1, moves())                             // one tap, no endless repeat
    }

    @Test fun unboundKeyPassesBothWays() {
        bind(OrbitActions.FORWARD to Trigger("key:22"))
        assertFalse(key(21, "key:21", true))
        assertFalse(key(21, "key:21", false))
        assertTrue(events.isEmpty())
    }

    @Test fun osRepeatOfAHeldKeyIsSwallowedAndCountedOnce() {
        bind(OrbitActions.SELECT to Trigger("key:66"))
        assertTrue(key(66, "key:66", true))
        repeat(5) { assertTrue(key(66, "key:66", true)) }     // KeyEvent repeats while held
        key(66, "key:66", false)
        assertEquals(listOf(OrbitActions.SELECT), actions())
    }

    @Test fun controlsSavedMidPressStillSwallowTheUp() {
        bind(OrbitActions.FORWARD to Trigger("key:22"))
        assertTrue(key(22, "key:22", true))
        bind(OrbitActions.BACK to Trigger("key:21"))         // key:22 no longer used
        assertTrue(key(22, "key:22", false))                 // the app never sees a lone up
        pass(2_000)
        assertEquals(1, moves())
    }

    @Test fun screenOffLetsEveryKeyGo() {
        bind(OrbitActions.FORWARD to Trigger("key:24"))
        key(24, "key:24", true)
        pass(PressRecognizer.REPEAT_DELAY_MS + 3 * PressRecognizer.REPEAT_EVERY_MS)
        val before = moves()
        pairing.clear(); hub.releaseAll()                    // what Orbit.releaseKeys does
        pass(3_000)
        assertEquals(before, moves())
        assertFalse(key(24, "key:24", false))                // the late up, if it ever comes, passes
    }

    @Test fun aLostUpStopsRepeatingAfterTheLimit() {
        bind(OrbitActions.FORWARD to Trigger("key:24"))
        key(24, "key:24", true)
        pass(PressRecognizer.MAX_HOLD_MS + 500)
        val after = moves()
        pass(5_000)
        assertEquals(after, moves())
    }

    @Test fun aLostUpDuringAHoldDoesNotFireAgain() {
        bind(OrbitActions.OPEN to Trigger("key:24", Press.HOLD))
        key(24, "key:24", true)
        pass(PressRecognizer.MAX_HOLD_MS + 500)
        assertEquals(listOf(OrbitActions.OPEN), actions())
        key(24, "key:24", true)                               // still paired: the OS repeat
        assertEquals(listOf(OrbitActions.OPEN), actions())
    }

    // ---------------------------------------------------------------- devices

    @Test fun twoRemotesNeverMixTheirTaps() {
        bind(OrbitActions.SELECT to Trigger("key:66"), OrbitActions.OPEN to Trigger("key:66", Press.DOUBLE))
        key(66, "key:66", true, "a"); key(66, "key:66", false, "a")
        now += 50
        key(66, "key:66", true, "b"); key(66, "key:66", false, "b")
        pass(400)
        assertEquals(listOf(OrbitActions.SELECT, OrbitActions.SELECT), actions())
    }

    @Test fun aKeyRecordedOnOneDeviceWinsOverAnyDevice() {
        hub.set(Controls(listOf(Binding(OrbitActions.FORWARD, Trigger("key:24")),
            Binding(OrbitActions.BACK, Trigger("key:24", device = "remote")))))
        key(24, "key:24", true, "remote"); key(24, "key:24", false, "remote")
        key(24, "key:24", true, "phone"); key(24, "key:24", false, "phone")
        assertEquals(listOf(-1, 1), events.map { it.delta })
    }

    // ---------------------------------------------------------------- timing edges

    @Test fun doubleTapJustInsideTheGap() {
        bind(OrbitActions.SELECT to Trigger("key:66"), OrbitActions.OPEN to Trigger("key:66", Press.DOUBLE))
        key(66, "key:66", true); now += 60; key(66, "key:66", false)
        now += PressRecognizer.GAP_MS - 10
        key(66, "key:66", true); now += 60; key(66, "key:66", false)
        pass(400)
        assertEquals(listOf(OrbitActions.OPEN), actions())
    }

    @Test fun twoTapsJustOutsideTheGapAreTwoTaps() {
        bind(OrbitActions.SELECT to Trigger("key:66"), OrbitActions.OPEN to Trigger("key:66", Press.DOUBLE))
        key(66, "key:66", true); now += 60; key(66, "key:66", false)
        pass(PressRecognizer.GAP_MS + 10)
        key(66, "key:66", true); now += 60; key(66, "key:66", false)
        pass(400)
        assertEquals(listOf(OrbitActions.SELECT, OrbitActions.SELECT), actions())
    }

    @Test fun aCountNobodyUsesIsThatManyTaps() {
        bind(OrbitActions.SELECT to Trigger("key:66"), OrbitActions.OPEN to Trigger("key:66", Press.TRIPLE))
        repeat(2) { key(66, "key:66", true); now += 60; key(66, "key:66", false); now += 100 }
        pass(400)
        assertEquals(listOf(OrbitActions.SELECT, OrbitActions.SELECT), actions())
    }

    @Test fun holdIsNotATapAndATapAfterItIsFresh() {
        bind(OrbitActions.SELECT to Trigger("key:66"), OrbitActions.OPEN to Trigger("key:66", Press.HOLD))
        key(66, "key:66", true); pass(PressRecognizer.HOLD_MS + 50); key(66, "key:66", false)
        pass(400)
        key(66, "key:66", true); now += 60; key(66, "key:66", false)
        pass(400)
        assertEquals(listOf(OrbitActions.OPEN, OrbitActions.SELECT), actions())
    }

    @Test fun releasedJustBeforeHoldIsATap() {
        bind(OrbitActions.SELECT to Trigger("key:66"), OrbitActions.OPEN to Trigger("key:66", Press.HOLD))
        key(66, "key:66", true); pass(PressRecognizer.HOLD_MS - 20); key(66, "key:66", false)
        pass(400)
        assertEquals(listOf(OrbitActions.SELECT), actions())
    }

    @Test fun fastKnobClicksAreEveryOneAMove() {
        // a keyboard knob: volume key taps ~40 ms apart, each a full down / up
        bind(OrbitActions.FORWARD to Trigger("key:24"), OrbitActions.BACK to Trigger("key:25"))
        repeat(12) { key(24, "key:24", true); now += 15; key(24, "key:24", false); now += 25 }
        repeat(5) { key(25, "key:25", true); now += 15; key(25, "key:25", false); now += 25 }
        assertEquals(12 - 5, moves())
    }

    // ---------------------------------------------------------------- the key's own job

    private val replayed = mutableListOf<Pair<String, Int>>()
    private fun withReplay() { hub.replay = { inp, n -> replayed += inp to n } }

    @Test fun aKeyBoundOnlyToHoldStillDoesItsJobOnATap() {
        withReplay()
        bind(OrbitActions.OPEN to Trigger("key:24", Press.HOLD))
        key(24, "key:24", true); now += 80; key(24, "key:24", false)
        pass(400)
        assertEquals(listOf("key:24" to 1), replayed)       // volume still goes up
        assertTrue(events.isEmpty())
    }

    @Test fun aKeyBoundOnlyToDoubleGivesBackASingleTap() {
        withReplay()
        bind(OrbitActions.OPEN to Trigger("key:24", Press.DOUBLE))
        key(24, "key:24", true); now += 60; key(24, "key:24", false)
        pass(PressRecognizer.GAP_MS + 50)
        assertEquals(listOf("key:24" to 1), replayed)
        key(24, "key:24", true); now += 60; key(24, "key:24", false); now += 100
        key(24, "key:24", true); now += 60; key(24, "key:24", false)
        pass(400)
        assertEquals(listOf(OrbitActions.OPEN), actions())
        assertEquals(1, replayed.size)                        // the double was ours, not re-sent
    }

    @Test fun nothingIsReSentWhenATapIsInUse() {
        withReplay()
        bind(OrbitActions.SELECT to Trigger("key:24"), OrbitActions.OPEN to Trigger("key:24", Press.HOLD))
        key(24, "key:24", true); now += 60; key(24, "key:24", false)
        pass(400)
        assertTrue(replayed.isEmpty())
        assertEquals(listOf(OrbitActions.SELECT), actions())
    }

    @Test fun aHoldIsNeverReSent() {
        withReplay()
        bind(OrbitActions.OPEN to Trigger("key:24", Press.HOLD))
        key(24, "key:24", true); pass(PressRecognizer.HOLD_MS + 100); key(24, "key:24", false)
        pass(400)
        assertTrue(replayed.isEmpty())
    }

    @Test fun countedInputsPulseWithoutPresses() {
        bind(OrbitActions.SELECT to Trigger("backtap:1"), OrbitActions.FORWARD to Trigger("vol:up"))
        assertTrue(hub.pulse("backtap:1"))
        assertTrue(hub.pulse("vol:up", 3))
        assertFalse(hub.pulse("motion:chop"))
        assertEquals(3, moves()); assertEquals(listOf(OrbitActions.SELECT), actions())
    }
}
