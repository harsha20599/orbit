package app.orbit.dial.core

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Chop twice (like Motorola's flashlight gesture): two hard chops of the phone, about
 * a quarter to three quarters of a second apart. Each chop is a jolt far bigger than
 * walking, tapping or putting the phone down ([CHOP] m/s² once gravity is removed).
 *
 * Feed it raw accelerometer samples (m/s², device axes), timestamps in ms.
 */
class ChopDetector(private val emit: () -> Unit) {
    companion object {
        const val CHOP = 14f
        const val MIN_GAP_MS = 180L        // one chop's own swing back is not a second chop
        const val MAX_GAP_MS = 800L
        const val COOLDOWN_MS = 1200L
    }

    private val g = FloatArray(3)
    private var primed = 0
    private var lastChop = 0L
    private var chops = 0
    private var quietUntil = 0L

    fun reset() { primed = 0; chops = 0 }

    fun sample(x: Float, y: Float, z: Float, t: Long) {
        if (primed < 20) {
            if (primed == 0) { g[0] = x; g[1] = y; g[2] = z } else { g[0] += (x - g[0]) * 0.2f; g[1] += (y - g[1]) * 0.2f; g[2] += (z - g[2]) * 0.2f }
            primed++; return
        }
        val hx = x - g[0]; val hy = y - g[1]; val hz = z - g[2]
        val mag = sqrt(hx * hx + hy * hy + hz * hz)
        if (chops > 0 && t - lastChop > MAX_GAP_MS) chops = 0
        if (t >= quietUntil && mag > CHOP && t - lastChop >= MIN_GAP_MS) {
            chops++; lastChop = t
            if (chops >= 2) { chops = 0; quietUntil = t + COOLDOWN_MS; emit() }
        }
        val k = 0.02f
        g[0] += (x - g[0]) * k; g[1] += (y - g[1]) * k; g[2] += (z - g[2]) * k
    }
}

/**
 * Twist twice (like Motorola's camera gesture): turn the wrist back and forth twice,
 * fast. From the gyroscope: rotation about the phone's long axis (y) swinging past
 * [SPIN] rad/s one way, then the other, at least three swings within [WINDOW_MS].
 * Turning the phone to read it is slow and one-way, so it never counts.
 */
class TwistDetector(private val emit: () -> Unit) {
    companion object {
        const val SPIN = 5f
        const val WINDOW_MS = 1100L
        const val SWINGS = 3
        const val COOLDOWN_MS = 1200L
    }

    private val swings = ArrayDeque<Pair<Long, Int>>()     // (time, direction)
    private var quietUntil = 0L

    fun reset() = swings.clear()

    fun sample(@Suppress("UNUSED_PARAMETER") x: Float, y: Float, @Suppress("UNUSED_PARAMETER") z: Float, t: Long) {
        while (swings.isNotEmpty() && t - swings.first().first > WINDOW_MS) swings.removeFirst()
        if (t < quietUntil || abs(y) < SPIN) return
        val dir = if (y > 0) 1 else -1
        if (swings.lastOrNull()?.second == dir) return            // still the same swing
        swings.addLast(t to dir)
        if (swings.size >= SWINGS) { swings.clear(); quietUntil = t + COOLDOWN_MS; emit() }
    }
}
