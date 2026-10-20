package app.orbit.dial

import android.content.Context
import app.orbit.dial.core.Clock
import app.orbit.dial.core.DialEvent
import app.orbit.dial.core.RotationControl
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * In-process hub. One process, so services talk through this object:
 *  - every dial event (media service, hold trampoline, test buttons) -> [events]
 *  - the accessibility service owns the Engine and collects [events]
 *  - the media service owns the VolumeDial and plugs it in as [rotation]
 */
object Orbit {
    private val _events = MutableSharedFlow<DialEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<DialEvent> = _events

    /** When the last dial press arrived (0 = none yet): the setup screen's press test. */
    @Volatile var lastPress = 0L

    fun emit(ev: DialEvent) {
        log("in  ${ev.action ?: ev.kind}${if (ev.delta != 0) " ${ev.delta}" else ""} <${ev.source}>")
        _events.tryEmit(ev)
    }

    @Volatile var a11y: OrbitAccessibilityService? = null
    @Volatile var media: OrbitMediaService? = null

    /** Engine-facing rotation control; remembers the request until the media service attaches. */
    val rotation = RotationProxy()

    class RotationProxy : RotationControl {
        private var passthrough = true
        private var duck: Float? = null
        override fun setPassthrough(on: Boolean) { passthrough = on; media?.dial?.setPassthrough(on) }
        override fun setDuck(factor: Float?) { duck = factor; media?.dial?.setDuck(factor) }
        override fun level(): Float? = media?.dial?.level()
        fun replayInto(svc: OrbitMediaService) { svc.dial.setPassthrough(passthrough); svc.dial.setDuck(duck) }
    }

    // ---- controls: every trigger (keys, earbud gestures, dial turns, back taps) goes
    // through the hub, which turns it into the function the user picked.
    val hub = app.orbit.dial.core.ControlsHub { ev -> emit(ev) }
    @Volatile var volumeIsDial = true
    private val main = android.os.Handler(android.os.Looper.getMainLooper())
    private val hubTick = Runnable { hub.tick(Clock.now()); scheduleHub() }
    private fun scheduleHub() {
        main.removeCallbacks(hubTick)
        hub.nextWake()?.let { main.postDelayed(hubTick, (it - Clock.now()).coerceIn(0, 2000)) }
    }
    fun reloadControls(ctx: Context) {
        val c = ControllerStore.load(ctx)
        hub.set(c)
        volumeIsDial = hub.volumeIsDial()
        onBackTapNeed?.invoke()
        log("controls: ${c.bindings.joinToString { "${it.action}<-${it.trigger.label()}" }}")
    }

    /** A key down / up; true if a control uses it (swallow it). Main thread. */
    fun key(device: String, input: String, down: Boolean): Boolean {
        val r = hub.onKey(device, input, down, Clock.now())
        scheduleHub()
        return r
    }

    // ---- back taps: Orbit's own detector (any phone) and the phone's (Pixel / Samsung)
    // can both fire for one gesture; the second within a moment is the same tap.
    @Volatile var backTapTesting = false
        set(v) { field = v; onBackTapNeed?.invoke() }
    var onBackTapNeed: (() -> Unit)? = null
    private val lastBackTap = HashMap<String, Long>()
    fun backTapDetect(ctx: Context) = prefs(ctx).getBoolean("backtap_detect", true)
    fun backTapSensitivity(ctx: Context) = prefs(ctx).getString("backtap_sens", "medium") ?: "medium"

    /** An input the device counts itself (earbud gesture, dial turn, back tap). Main thread. */
    fun pulse(input: String, n: Int = 1, source: String? = null): Boolean {
        if (input.startsWith("backtap:")) {
            val t = Clock.now()
            if (t - (lastBackTap[input] ?: 0L) < 700) return true
            lastBackTap[input] = t
        }
        if (input.startsWith("media:")) lastPress = Clock.now()
        if (capturing()) { capture(Captured(input, true, null, null, counted = true)); return true }
        log("in  $input${if (n > 1) " x$n" else ""}")
        return hub.pulse(input, n, source)
    }

    // ---- while a controls screen is open, every button comes here instead of
    // acting. Kept alive by the screen's heartbeat, so it can never stick on.
    class Captured(val input: String, val down: Boolean, val device: String?, val deviceName: String?,
                   val counted: Boolean = false, val typing: Boolean = false)
    @Volatile var captureUntil = 0L
    fun capturing() = Clock.now() < captureUntil
    private val _captured = MutableSharedFlow<Captured>(extraBufferCapacity = 64)
    val captured: SharedFlow<Captured> = _captured
    fun capture(c: Captured) { _captured.tryEmit(c) }

    /** Phone volume keys pressed recently: those volume changes are not the dial. */
    @Volatile var lastPhoneVolumeKey = 0L
    fun phoneKeyRecently() = Clock.now() - lastPhoneVolumeKey < 600

    // ---- small diagnostic log for the setup screen
    val logLines = MutableStateFlow<List<String>>(emptyList())
    private val fmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
    fun log(line: String) {
        android.util.Log.d("Orbit", line)
        logLines.value = (logLines.value + "${fmt.format(Date())}  $line").takeLast(60)
    }

    // ---- settings
    private const val PREFS = "orbit"
    fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    /** Always on in release; the debug intent extra turns it off for emulator testing. */
    fun requireBluetooth(ctx: Context) = !BuildConfig.DEBUG || prefs(ctx).getBoolean("require_bt", true)

    /** Orbit on/off. Off: no media session, no volume watching, so the buds behave
     *  exactly as without Orbit (presses control music, the dial changes volume). */
    fun enabled(ctx: Context) = prefs(ctx).getBoolean("enabled", true)
    fun setEnabled(ctx: Context, on: Boolean) {
        prefs(ctx).edit().putBoolean("enabled", on).apply()
        if (on) OrbitMediaService.start(ctx) else OrbitMediaService.stop(ctx)
        log(if (on) "Orbit turned on" else "Orbit turned off")
        runCatching {
            android.service.quicksettings.TileService.requestListeningState(ctx,
                android.content.ComponentName(ctx, OrbitTileService::class.java))
        }
    }
    fun setRequireBluetooth(ctx: Context, on: Boolean) = prefs(ctx).edit().putBoolean("require_bt", on).apply()
}
