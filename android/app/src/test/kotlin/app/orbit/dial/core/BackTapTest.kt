package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin

/** Synthetic 200 Hz accelerometer traces: still phone, knocks, screen taps, walking. */
class BackTapTest {
    private val got = mutableListOf<Int>()
    private val d = BackTapDetector { got += it }
    private var t = 0L

    private fun still(ms: Long, wobble: (Long) -> Triple<Float, Float, Float> = { Triple(0f, 0f, 0f) }) {
        repeat((ms / 5).toInt()) { val (x, y, z) = wobble(t); d.sample(0.3f + x, 0.5f + y, 9.7f + z, t); t += 5 }
    }

    /** A knock: a sharp jolt along z ([sign] +1 = toward the front, i.e. on the back). */
    private fun knock(sign: Int = 1, size: Float = 6f) {
        for (v in listOf(0.6f, 1f, 0.5f, -0.7f, -0.4f, 0.2f)) {
            d.sample(0.3f + 0.3f * v, 0.5f - 0.2f * v, 9.7f + sign * size * v, t); t += 5
        }
    }

    @Test fun doubleKnockOnTheBack() {
        still(600); knock(); still(180); knock(); still(600)
        assertEquals(listOf(2), got)
    }

    @Test fun tripleKnock() {
        still(600); knock(); still(150); knock(); still(150); knock(); still(600)
        assertEquals(listOf(3), got)
    }

    @Test fun singleKnockIsIgnored() {
        still(600); knock(); still(800)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun tapsOnTheScreenAreIgnored() {
        still(600); knock(-1); still(180); knock(-1); still(600)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun softTouchesAreIgnored() {
        still(600); knock(size = 1.2f); still(180); knock(size = 1.2f); still(600)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun walkingIsNotATap() {
        val walk = { ms: Long -> val s = sin(2 * PI * 2.0 * ms / 1000).toFloat()
            Triple(1.8f * s, 2.5f * s, 3f * s) }
        still(1200, walk); knock(); still(180, walk); knock(); still(600, walk)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun tooSlowIsTwoSingles() {
        still(600); knock(); still(900); knock(); still(800)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun phoneHeldUprightWorksToo() {
        // gravity along y (portrait in hand): z is still the screen axis
        repeat(120) { d.sample(0.2f, 9.6f, 0.8f, t); t += 5 }
        for (n in 0 until 2) {
            for (v in listOf(0.6f, 1f, 0.5f, -0.7f, -0.4f, 0.2f)) { d.sample(0.2f, 9.6f + 0.3f * v, 0.8f + 6f * v, t); t += 5 }
            repeat(36) { d.sample(0.2f, 9.6f, 0.8f, t); t += 5 }
        }
        repeat(120) { d.sample(0.2f, 9.6f, 0.8f, t); t += 5 }
        assertEquals(listOf(2), got)
    }
}
