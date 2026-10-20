package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin

class MotionTest {
    private var t = 0L

    // ---------------------------------------------------------------- chop

    private fun ChopDetector.still(ms: Long, wobble: (Long) -> Float = { 0f }) {
        repeat((ms / 5).toInt()) { sample(0.2f + wobble(t), 9.7f + wobble(t), 0.5f, t); t += 5 }
    }

    /** One chop: a hard swing down the long axis and back, ~120 ms. */
    private fun ChopDetector.chop(size: Float = 22f) {
        for (i in 0 until 24) { val v = sin(2 * PI * i / 24).toFloat(); sample(0.2f + 2f * v, 9.7f - size * v, 0.5f + 3f * v, t); t += 5 }
    }

    @Test fun twoChopsFire() {
        var n = 0
        val d = ChopDetector { n++ }
        d.still(500); d.chop(); d.still(250); d.chop(); d.still(1500)
        assertEquals(1, n)
    }

    @Test fun oneChopDoesNot() {
        var n = 0
        val d = ChopDetector { n++ }
        d.still(500); d.chop(); d.still(1500)
        assertEquals(0, n)
    }

    @Test fun chopsTooFarApartDoNot() {
        var n = 0
        val d = ChopDetector { n++ }
        d.still(500); d.chop(); d.still(1200); d.chop(); d.still(1500)
        assertEquals(0, n)
    }

    @Test fun runningIsNotAChop() {
        var n = 0
        val d = ChopDetector { n++ }
        d.still(4000) { ms -> 7f * sin(2 * PI * 2.8 * ms / 1000).toFloat() }
        assertEquals(0, n)
    }

    @Test fun backTapsAreNotChops() {
        var n = 0
        val d = ChopDetector { n++ }
        d.still(500)
        repeat(2) { for (v in listOf(0.6f, 1f, 0.5f, -0.7f)) { d.sample(0.2f, 9.7f, 0.5f + 6f * v, t); t += 5 }; d.still(180) }
        d.still(1000)
        assertEquals(0, n)
    }

    // ---------------------------------------------------------------- twist

    private fun TwistDetector.gyro(ms: Long, wy: (Long) -> Float) {
        repeat((ms / 5).toInt()) { sample(0f, wy(t), 0f, t); t += 5 }
    }

    @Test fun twistTwiceFires() {
        var n = 0
        val d = TwistDetector { n++ }
        d.gyro(300) { 0f }
        val start = t
        d.gyro(800) { ms -> 9f * sin(2 * PI * 2.5 * (ms - start) / 1000).toFloat() }   // two back-and-forth twists
        d.gyro(1500) { 0f }
        assertEquals(1, n)
    }

    @Test fun turningThePhoneOnceDoesNot() {
        var n = 0
        val d = TwistDetector { n++ }
        d.gyro(300) { 0f }; d.gyro(400) { 6f }; d.gyro(1500) { 0f }
        assertEquals(0, n)
    }

    @Test fun slowRockingDoesNot() {
        var n = 0
        val d = TwistDetector { n++ }
        d.gyro(5000) { ms -> 2.5f * sin(2 * PI * 1.0 * ms / 1000).toFloat() }
        assertEquals(0, n)
    }
}
