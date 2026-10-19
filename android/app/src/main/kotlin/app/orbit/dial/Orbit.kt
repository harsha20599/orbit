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
        if (ev.kind != app.orbit.dial.core.Kind.ROTATE && ev.source == "media-session") lastPress = Clock.now()
        log("in  ${ev.kind}${if (ev.delta != 0) " ${ev.delta}" else ""} <${ev.source}>")
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

    // ---- Add-a-controller: while the screen is open, every key and music press comes here
    // instead of acting. Kept alive by the screen's heartbeat, so it can never stick on.
    class Captured(val key: Int, val down: Boolean, val device: String?, val deviceName: String,
                   val label: String, val media: Boolean = false, val typing: Boolean = false)
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
