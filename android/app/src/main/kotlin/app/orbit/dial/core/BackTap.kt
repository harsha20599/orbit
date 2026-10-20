package app.orbit.dial.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Back taps from the accelerometer, on any phone (Pixel's Quick Tap and Samsung's
 * RegiStar only exist on those phones).
 *
 * A knock on the back is a short, sharp jolt along the screen's axis (z), toward the
 * front first; a tap on the screen jolts the other way first, and walking or turning
 * the phone is slow and spread over all axes. So a tap is:
 *   - gravity removed (a slow low-pass is subtracted)
 *   - |z| crosses [threshold] with z clearly dominant over x / y
 *   - the first crossing is positive (toward the front): the back, not the screen
 *   - the phone was still just before (no walking, shaking, handling)
 * Taps within [GAP_MS] are counted; 2 = "double", 3+ = "triple". A single knock never
 * counts: it happens too often by accident (setting the phone down).
 *
 * Feed it raw accelerometer samples (m/s², device axes) with timestamps in ms.
 */
class BackTapDetector(var threshold: Float = SENS_MEDIUM, private val emit: (Int) -> Unit) {
    companion object {
        const val SENS_LOW = 3.2f
        const val SENS_MEDIUM = 2.2f
        const val SENS_HIGH = 1.5f
        const val GAP_MS = 450L            // max time between taps of one gesture
        const val MIN_GAP_MS = 90L         // a tap's own rebound is not another tap
        const val QUIET_MS = 250L          // stillness needed before the first tap
        const val QUIET_LEVEL = 0.9f       // m/s², mean |a - gravity| that still counts as still
        const val DOMINANCE = 1.4f         // |z| over max(|x|, |y|)
    }

    private val g = FloatArray(3)
    private var primed = 0
    private var lastT = 0L
    private var lastTap = 0L
    private var taps = 0
    // stillness: an exponential mean of |hp| over ~QUIET_MS, frozen while a tap rings out
    private var energy = 0f
    private var ringing = 0L

    fun reset() { primed = 0; taps = 0; energy = 0f; lastTap = 0L }

    fun sample(x: Float, y: Float, z: Float, t: Long) {
        val dt = if (lastT == 0L) 5L else (t - lastT).coerceIn(1, 50)
        lastT = t
        if (primed < 20) {                                  // settle the gravity estimate
            if (primed == 0) { g[0] = x; g[1] = y; g[2] = z } else lowpass(x, y, z, 0.2f)
            primed++; return
        }
        val hx = x - g[0]; val hy = y - g[1]; val hz = z - g[2]
        val mag = sqrt(hx * hx + hy * hy + hz * hz)

        if (t >= ringing && abs(hz) > threshold) {
            val side = max(abs(hx), abs(hy))
            val still = energy < QUIET_LEVEL || (taps > 0 && t - lastTap < GAP_MS)
            if (abs(hz) > side * DOMINANCE && hz > 0 && still && t - lastTap >= MIN_GAP_MS) {
                taps++; lastTap = t
            }
            ringing = t + MIN_GAP_MS                        // ignore the rebound either way
        }
        if (t >= ringing) {
            val k = dt.toFloat() / QUIET_MS
            energy += (mag - energy) * k.coerceAtMost(1f)
        }
        lowpass(x, y, z, 0.02f * dt / 5f)
        flush(t)
    }

    /** Call now and then without samples too (sensor paused): ends a pending gesture. */
    fun flush(t: Long) {
        if (taps > 0 && t - lastTap >= GAP_MS) {
            if (taps >= 2) emit(minOf(taps, 3))
            taps = 0
        }
    }

    private fun lowpass(x: Float, y: Float, z: Float, a: Float) {
        val k = a.coerceIn(0f, 1f)
        g[0] += (x - g[0]) * k; g[1] += (y - g[1]) * k; g[2] += (z - g[2]) * k
    }
}
