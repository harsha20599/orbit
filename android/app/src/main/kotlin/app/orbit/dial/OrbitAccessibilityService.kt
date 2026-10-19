package app.orbit.dial

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ComponentName
import android.content.Intent
import android.graphics.Path
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import app.orbit.dial.core.Actions
import app.orbit.dial.core.App
import app.orbit.dial.core.Clock
import app.orbit.dial.core.Engine
import app.orbit.dial.core.defaultTools
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlin.math.sqrt

/**
 * Centre of the Android app: started (and restarted after reboot) by the system
 * once the user enables it. Owns the Engine and the overlay, and performs every
 * action: scroll gestures, magnification, global actions, app launches.
 */
class OrbitAccessibilityService : AccessibilityService(), Actions {
    companion object {
        const val SWIPE_MS = 130L
        const val SWIPE_GAP_MS = 140L
        const val MAX_QUEUED_SWIPES = 3
    }

    private val main = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var overlay: OverlayController
    lateinit var engine: Engine
        private set
    private val recent = ArrayDeque<String>()       // most recent first

    private var prefsListener: android.content.SharedPreferences.OnSharedPreferenceChangeListener? = null
    private val rebuild = Runnable {
        engine.shutdown()
        engine = buildEngine()
        Orbit.log("settings applied: wheel ${engine.wheel.map { it.id }}, start ${engine.tool.id}")
    }

    private fun buildEngine(): Engine {
        val s = SettingsStore.load(this)
        overlay.state.appearance = s.appearance
        return s.buildEngine(this, overlay, Orbit.rotation, defaultTools())
    }

    private val ticker = object : Runnable {
        override fun run() { engine.tick(); main.postDelayed(this, 50) }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        Orbit.a11y = this
        overlay = OverlayController(this)
        engine = buildEngine()
        prefsListener = SettingsStore.listen(this) {
            main.removeCallbacks(rebuild); main.postDelayed(rebuild, 150)          // one rebuild per save
        }
        loadControls()
        controlsListener = ControllerStore.listen(this) { main.post { loadControls() } }
        scope.launch { Orbit.events.collect { ev -> engine.handle(ev) } }
        main.post(ticker)
        if (BuildConfig.DEBUG) registerDebugInjector()
        OrbitMediaService.start(this)
        Orbit.log("accessibility service connected")
    }

    /** Debug builds only: inject dial events without bringing any Orbit UI forward.
     *  adb shell am broadcast -a app.orbit.dial.DEBUG_EMIT --es e rotate:2 */
    private var debugRx: android.content.BroadcastReceiver? = null
    private fun registerDebugInjector() {
        debugRx = object : android.content.BroadcastReceiver() {
            override fun onReceive(c: android.content.Context, i: Intent) {
                val spec = i.getStringExtra("e") ?: return
                val parts = spec.split(":")
                runCatching {
                    Orbit.emit(app.orbit.dial.core.DialEvent(app.orbit.dial.core.Kind.valueOf(parts[0].uppercase()),
                        parts.getOrNull(1)?.toIntOrNull() ?: 0, "debug"))
                }
            }
        }
        androidx.core.content.ContextCompat.registerReceiver(this, debugRx, android.content.IntentFilter("app.orbit.dial.DEBUG_EMIT"),
            androidx.core.content.ContextCompat.RECEIVER_EXPORTED)
    }

    override fun onDestroy() {
        prefsListener?.let { Orbit.prefs(this).unregisterOnSharedPreferenceChangeListener(it) }
        controlsListener?.let { Orbit.prefs(this).unregisterOnSharedPreferenceChangeListener(it) }
        main.removeCallbacks(controlsTick)
        main.removeCallbacks(rebuild)
        debugRx?.let { runCatching { unregisterReceiver(it) } }
        main.removeCallbacks(ticker)
        scope.cancel()
        if (::overlay.isInitialized) overlay.destroy()
        if (Orbit.a11y === this) Orbit.a11y = null
        super.onDestroy()
    }

    override fun onInterrupt() {}

    override fun onAccessibilityEvent(e: AccessibilityEvent) {
        if (e.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val pkg = e.packageName?.toString() ?: return
        if (pkg == packageName || pkg == "com.android.systemui" || packageManager.getLaunchIntentForPackage(pkg) == null) return
        recent.remove(pkg); recent.addFirst(pkg)
        while (recent.size > 12) recent.removeLast()
    }

    /**
     * Every hardware key passes here first. Add-a-controller open: capture it. A key of
     * one of the user's controllers: swallow it (no volume change, no shutter, no typing)
     * and drive Orbit. Anything else goes on as normal.
     */
    override fun onKeyEvent(event: KeyEvent): Boolean {
        val code = event.keyCode
        val down = event.action == KeyEvent.ACTION_DOWN
        if (event.action != KeyEvent.ACTION_DOWN && event.action != KeyEvent.ACTION_UP) return false
        if (code in ControllerStore.RESERVED) return false
        val dev = event.device
        if (Orbit.capturing()) {
            if (!down || event.repeatCount == 0)
                Orbit.capture(Orbit.Captured(code, down, ControllerStore.deviceId(dev), ControllerStore.deviceName(dev),
                    ControllerStore.keyLabel(code), typing = dev?.keyboardType == android.view.InputDevice.KEYBOARD_TYPE_ALPHABETIC))
            return true
        }
        if (Orbit.enabled(this) && controls.onKey(ControllerStore.deviceId(dev), code, down, Clock.now())) {
            scheduleControls()
            return true
        }
        if (code == KeyEvent.KEYCODE_VOLUME_UP || code == KeyEvent.KEYCODE_VOLUME_DOWN) {
            Orbit.lastPhoneVolumeKey = Clock.now()      // not the dial: don't read that volume change as a turn
        }
        return false
    }

    // ---- controllers: holds and repeats are timed by one runnable at the next deadline
    private val controls = app.orbit.dial.core.ControllerHub { ev -> Orbit.emit(ev) }
    private var controlsListener: android.content.SharedPreferences.OnSharedPreferenceChangeListener? = null
    private val controlsTick = Runnable { controls.tick(Clock.now()); scheduleControls() }
    private fun scheduleControls() {
        main.removeCallbacks(controlsTick)
        val at = controls.nextWake() ?: return
        main.postDelayed(controlsTick, (at - Clock.now()).coerceIn(0, 2000))
    }
    private fun loadControls() {
        val list = ControllerStore.load(this)
        controls.set(list)
        Orbit.log("controllers: ${list.filter { it.enabled }.joinToString { "${it.name} (${it.buttons.size})" }.ifEmpty { "none" }}")
    }


    // ================================================================ Actions
    // ---- swipe: one quick thumb flick per click, queued so flicks never overlap.
    // Reels / Shorts / TikTok need ~25% of the screen at flick speed to page; this
    // travels 40% in 130 ms. A short gap between flicks lets the pager settle.
    private val swipes = ArrayDeque<Pair<Int, Boolean>>()       // (direction, sideways)
    private var swiping = false

    override fun swipe(direction: Int, sideways: Boolean) {
        if (swipes.size < MAX_QUEUED_SWIPES) swipes.addLast(direction to sideways)
        if (!swiping) nextSwipe()
    }

    private fun nextSwipe() {
        val (dir, sideways) = swipes.removeFirstOrNull() ?: run { swiping = false; return }
        swiping = true
        val dm = resources.displayMetrics
        val path = Path()
        if (sideways) {                    // next = finger right-to-left across the middle
            val y = dm.heightPixels / 2f
            val right = dm.widthPixels * 0.80f
            val left = dm.widthPixels * 0.20f
            if (dir > 0) { path.moveTo(right, y); path.lineTo(left, y) } else { path.moveTo(left, y); path.lineTo(right, y) }
        } else {
            val x = dm.widthPixels / 2f
            val low = dm.heightPixels * 0.70f
            val high = dm.heightPixels * 0.30f
            if (dir > 0) { path.moveTo(x, low); path.lineTo(x, high) } else { path.moveTo(x, high); path.lineTo(x, low) }
        }
        val done = object : GestureResultCallback() {
            override fun onCompleted(g: GestureDescription?) { main.postDelayed({ nextSwipe() }, SWIPE_GAP_MS) }
            override fun onCancelled(g: GestureDescription?) { main.postDelayed({ nextSwipe() }, SWIPE_GAP_MS) }
        }
        val gesture = GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, SWIPE_MS)).build()
        if (!dispatchGesture(gesture, done, main)) { swipes.clear(); swiping = false }
    }

    // ---- teleprompter: slow nudges, play / pause by label
    private val playWords = Regex("^(play|pause|start|stop|resume)\\b|play/pause|play_pause", RegexOption.IGNORE_CASE)

    override fun nudge(direction: Int) {
        val dm = resources.displayMetrics
        val x = dm.widthPixels / 2f
        val mid = dm.heightPixels * 0.55f
        val d = dm.heightPixels * 0.09f
        val path = Path().apply { moveTo(x, mid + d / 2 * direction); lineTo(x, mid - d / 2 * direction) }
        // 350 ms for ~9% of the screen: slow enough that the app scrolls without a fling
        dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 350)).build(), null, main)
    }

    override fun tapPlayPause() {
        val root = rootInActiveWindow
        var hit: android.view.accessibility.AccessibilityNodeInfo? = null
        if (root != null) {
            val queue = ArrayDeque(listOf(root))
            var seen = 0
            while (queue.isNotEmpty() && seen < 600 && hit == null) {
                val n = queue.removeFirst(); seen++
                val label = "${n.contentDescription ?: ""} ${n.text ?: ""} ${n.viewIdResourceName ?: ""}".trim()
                if (label.isNotEmpty() && playWords.containsMatchIn(label)) {
                    hit = if (n.isClickable) n else n.parent?.takeIf { it.isClickable }
                }
                for (i in 0 until n.childCount) n.getChild(i)?.let(queue::addLast)
            }
        }
        if (hit != null && hit.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)) {
            Orbit.log("teleprompter: pressed '${hit.contentDescription ?: hit.text ?: hit.viewIdResourceName}'")
        } else {
            val dm = resources.displayMetrics
            val p = Path().apply { moveTo(dm.widthPixels / 2f, dm.heightPixels / 2f) }
            dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(p, 0, 60)).build(), null, main)
            Orbit.log("teleprompter: no play/pause button found, tapped the centre")
        }
        haptic()
    }

    // ---- camera shutter
    private val shutterWords = Regex("shutter|take (a )?(photo|picture)|capture|photo button", RegexOption.IGNORE_CASE)

    override fun shutter() {
        val root = rootInActiveWindow
        val pkg = root?.packageName?.toString()
        if (root == null || pkg == null || !isCameraApp(pkg)) {
            Orbit.log("shutter: no camera in front, opening it")
            runCatching {
                startActivity(Intent(android.provider.MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            return
        }
        val node = findShutter(root)
        if (node != null && node.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)) {
            Orbit.log("shutter: pressed '${node.contentDescription ?: node.viewIdResourceName}' in $pkg")
            haptic()
            return
        }
        // no labelled button: tap where camera apps put the shutter (bottom centre)
        val dm = resources.displayMetrics
        val p = Path().apply { moveTo(dm.widthPixels / 2f, dm.heightPixels * 0.87f) }
        dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(p, 0, 60)).build(), null, main)
        Orbit.log("shutter: no labelled button in $pkg, tapped bottom centre")
        haptic()
    }

    private fun isCameraApp(pkg: String): Boolean {
        if ("camera" in pkg.lowercase()) return true
        val handlers = packageManager.queryIntentActivities(Intent(android.provider.MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA), 0)
        return handlers.any { it.activityInfo.packageName == pkg }
    }

    /** The best shutter candidate: id says "shutter", or its label does; clickable (or its parent). */
    private fun findShutter(root: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
        var best: android.view.accessibility.AccessibilityNodeInfo? = null
        var bestScore = 0
        val queue = ArrayDeque(listOf(root))
        var seen = 0
        while (queue.isNotEmpty() && seen < 600) {
            val n = queue.removeFirst(); seen++
            var score = 0
            if ("shutter" in (n.viewIdResourceName ?: "").lowercase()) score += 3
            if (shutterWords.containsMatchIn("${n.contentDescription ?: ""} ${n.text ?: ""}")) score += 2
            if (score > bestScore) {
                val target = if (n.isClickable) n else n.parent?.takeIf { it.isClickable }
                if (target != null) { best = target; bestScore = score }
            }
            for (i in 0 until n.childCount) n.getChild(i)?.let(queue::addLast)
        }
        return best
    }

    // ---- zoom
    override fun zoom(scale: Float): Float {
        val mc = magnificationController
        val dm = resources.displayMetrics
        if (scale <= 1.001f) mc.reset(true) else {
            mc.setScale(scale, true)
            mc.setCenter(dm.widthPixels / 2f, dm.heightPixels / 2f, true)
        }
        return scale
    }
    override fun zoomScale(): Float = magnificationController.scale

    // ---- brightness (perceptual: slider position = sqrt of the 0..255 value)
    override fun brightness(): Float? {
        if (!Settings.System.canWrite(this)) return null
        val v = Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS, 128)
        return sqrt(v / 255f)
    }
    override fun setBrightness(v: Float) {
        if (!Settings.System.canWrite(this)) return
        Settings.System.putInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE, Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL)
        Settings.System.putInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS, (v * v * 255).toInt().coerceIn(1, 255))
    }

    // ---- torch
    private val cams by lazy { getSystemService(CameraManager::class.java) }
    private val flashId by lazy {
        runCatching {
            cams.cameraIdList.firstOrNull { cams.getCameraCharacteristics(it).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true }
        }.getOrNull()
    }
    override fun torchAvailable() = flashId != null
    override fun torch(on: Boolean, level: Float) {
        val id = flashId ?: return
        runCatching {
            if (on && Build.VERSION.SDK_INT >= 33) {
                val max = cams.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_STRENGTH_MAXIMUM_LEVEL) ?: 1
                if (max > 1) { cams.turnOnTorchWithStrengthLevel(id, (level * max).toInt().coerceIn(1, max)); return }
            }
            cams.setTorchMode(id, on)
        }
    }

    // ---- apps
    override fun recentApps(): List<App> = recent.drop(1).ifEmpty { recent.toList() }.map { pkg ->
        App(pkg, runCatching { packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString() }.getOrDefault(pkg))
    }
    override fun openApp(pkg: String) {
        packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }
    override fun launch(pkg: String) {
        val i = packageManager.getLaunchIntentForPackage(pkg)
            ?: Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$pkg"))
        runCatching { startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }

    override fun global(action: String) {
        val id = when (action) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents" -> GLOBAL_ACTION_RECENTS
            "notifications" -> GLOBAL_ACTION_NOTIFICATIONS
            "quick_settings" -> GLOBAL_ACTION_QUICK_SETTINGS
            "screenshot" -> if (Build.VERSION.SDK_INT >= 28) GLOBAL_ACTION_TAKE_SCREENSHOT else return
            "lock" -> if (Build.VERSION.SDK_INT >= 28) GLOBAL_ACTION_LOCK_SCREEN else return
            else -> return
        }
        // let the wheel's close animation clear the screen before a screenshot
        main.postDelayed({ performGlobalAction(id) }, if (action == "screenshot") 450 else 0)
    }

    // ---- media: to the real player (we own the media buttons, so we can't just dispatch keys)
    override fun media(command: String) {
        val c = realPlayer() ?: run { Orbit.log("media:$command - no player (enable notification access)"); return }
        val tc = c.transportControls
        when (command) {
            "play_pause" -> if (c.playbackState?.state == PlaybackState.STATE_PLAYING) tc.pause() else tc.play()
            "next" -> tc.skipToNext()
            "previous" -> tc.skipToPrevious()
        }
        Orbit.log("media:$command -> ${c.packageName}")
        main.postDelayed({ Orbit.media?.reassert() }, 700)    // the player takes the buttons when it starts
    }

    private fun realPlayer(): MediaController? = runCatching {
        val msm = getSystemService(MediaSessionManager::class.java)
        val list = msm.getActiveSessions(ComponentName(this, OrbitNotificationListener::class.java))
            .filter { it.packageName != packageName }
        list.firstOrNull { it.playbackState?.state == PlaybackState.STATE_PLAYING } ?: list.firstOrNull()
    }.getOrNull()

    override fun volume(): Float? = Orbit.rotation.level() ?: getSystemService(AudioManager::class.java).let {
        it.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat() / it.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
    }

    override fun stepVolume(steps: Int) {
        val am = getSystemService(AudioManager::class.java)
        Orbit.lastPhoneVolumeKey = Clock.now()          // ours, not a dial turn
        repeat(kotlin.math.abs(steps)) {
            am.adjustStreamVolume(AudioManager.STREAM_MUSIC,
                if (steps > 0) AudioManager.ADJUST_RAISE else AudioManager.ADJUST_LOWER, 0)
        }
    }

    private val vibrator by lazy { getSystemService(Vibrator::class.java) }
    override fun haptic() {
        runCatching {
            if (Build.VERSION.SDK_INT >= 29) vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK))
            else vibrator.vibrate(VibrationEffect.createOneShot(8, 60))
        }
    }

}
