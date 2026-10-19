package app.orbit.dial.core

/**
 * Gesture engine: same model as the desktop app (orbit/core/engine.py).
 *
 *  TOOL   dial drives the active tool
 *  WHEEL  wheel open: rotate moves the highlight, press selects
 *
 *  double press      -> open wheel (and close it again, no change)
 *  in wheel: rotate  -> move highlight (wraps)   press -> select
 *            triple / hold -> close, no change    5 s idle -> keep highlighted tool
 *  tool mode: press/double/triple/hold -> the tool's own action, else the global one
 */
class Engine(
    val actions: Actions,
    private val ui: Ui,
    private val rotation: RotationControl?,
    val tools: List<Tool>,
    defaultTool: String = "volume",
    private val globalGestures: Map<Kind, Gesture> = mapOf(
        Kind.CLICK to Gesture.Media("play_pause"),
        Kind.TRIPLE to Gesture.LastTool,
        Kind.HOLD to Gesture.Launch("com.anthropic.claude"),
    ),
    private val openWith: Set<Kind> = setOf(Kind.DOUBLE),
    private val dismissAfterMs: Long = 5000,
    private val duck: Float = 0.5f,
    /** Items per report when spinning fast. Off (1): two deliberate clicks ~0.45 s apart
     *  look the same as a spin with dropped clicks, and 2 skipped items in real use. */
    private val wheelAccel: Int = 1,
    /** Tools on the wheel, in order (the rest stay usable as default / gesture targets). */
    wheelIds: List<String> = tools.map { it.id },
) {
    val wheel: List<Tool> = wheelIds.mapNotNull { id -> tools.firstOrNull { it.id == id } }.ifEmpty { tools }

    enum class State { TOOL, WHEEL }

    var state = State.TOOL
        private set
    var tool: Tool = tools.first { it.id == defaultTool }
        private set
    var index = 0
        private set
    private var prevTool: Tool? = null
    private var wheelLast = 0L
    private var wheelSpin = SpinTracker()

    init { sync() }

    fun handle(ev: DialEvent) {
        if (state == State.WHEEL) wheelEvent(ev) else toolEvent(ev)
    }

    fun tick(now: Long = Clock.now()) {
        tool.tick(actions, now)?.let(ui::hud)
        if (state == State.WHEEL && now - wheelLast > dismissAfterMs) {
            if (wheel[index].sticky) commit() else cancel()
        }
    }

    /** Before this engine is replaced (settings changed): close the wheel, release the tool. */
    fun shutdown() {
        if (state == State.WHEEL) ui.wheelCancel()
        tool.leave(actions)
    }

    fun openWheel() {
        if (state == State.WHEEL) return
        tool.leave(actions)
        state = State.WHEEL
        index = wheel.indexOf(tool).coerceAtLeast(0)
        wheelLast = Clock.now()
        wheelSpin = SpinTracker()
        sync()
        ui.wheelOpen(wheel, index)
    }

    fun setTool(id: String) {
        val t = tools.firstOrNull { it.id == id } ?: return
        tool.leave(actions)
        switchTo(t)
        tool.enter(actions)
        sync()
        ui.hud(tool.hud(actions, 0))
    }

    private fun lastTool() { prevTool?.let { setTool(it.id) } }

    private fun switchTo(t: Tool) { if (t !== tool) { prevTool = tool; tool = t } }

    private fun toolEvent(ev: DialEvent) {
        if (ev.kind == Kind.ROTATE) {
            // the buds change the volume themselves; a controller's buttons don't
            if (tool.rotationPassthrough && ev.source.startsWith(CONTROLLER)) actions.stepVolume(ev.delta)
            tool.rotate(actions, ev.delta)?.let(ui::hud)
            return
        }
        if (ev.kind in openWith) { openWheel(); return }
        if (tool.gesture(actions, ev.kind)) { if (!tool.quietHud) ui.hud(tool.hud(actions, 0)); return }
        when (val g = globalGestures[ev.kind]) {
            is Gesture.Media -> actions.media(g.command)
            is Gesture.Launch -> actions.launch(g.pkg)
            is Gesture.Global -> actions.global(g.action)
            Gesture.LastTool -> lastTool()
            is Gesture.SwitchTo -> setTool(g.toolId)
            Gesture.OpenWheel -> openWheel()
            null -> {}
        }
    }

    private fun wheelEvent(ev: DialEvent) {
        wheelLast = Clock.now()
        when (ev.kind) {
            Kind.ROTATE -> {
                val n = wheel.size
                index = ((index + wheelSteps(ev.delta)) % n + n) % n
                actions.haptic()
                ui.wheelMove(index, if (ev.delta > 0) 1 else -1)
            }
            Kind.CLICK -> commit()
            else -> cancel()            // double, triple, hold: close without change
        }
    }

    /** Careful clicks move one item; reports at the buds' max rate move [wheelAccel].
     *  Turn-backs stay exact; no catch-up (overshooting a menu is worse). */
    private fun wheelSteps(delta: Int): Int {
        wheelSpin.update(delta, Clock.now())
        return if (wheelAccel == 1 || wheelSpin.intensity < 0.75f) delta else delta * wheelAccel
    }

    private fun commit() {
        val item = wheel[index]
        ui.wheelCommit(index)
        state = State.TOOL
        if (item.sticky) {
            switchTo(item)
            item.enter(actions)
            sync()
            ui.hud(item.hud(actions, 0))
        } else {
            sync()
            tool.enter(actions)
            item.fire(actions)
            ui.hud(Hud(item.icon, item.label, "done"))
        }
    }

    private fun cancel() {
        state = State.TOOL
        ui.wheelCancel()
        tool.enter(actions)
        sync()
    }

    /** Wheel: consume rotation and duck the volume. Tool mode: restore, then per-tool. */
    private fun sync() {
        val r = rotation ?: return
        if (state == State.WHEEL) {
            r.setPassthrough(false); r.setDuck(duck)
        } else {
            r.setDuck(null); r.setPassthrough(tool.rotationPassthrough)
        }
    }
}

sealed interface Gesture {
    data class Media(val command: String) : Gesture
    data class Launch(val pkg: String) : Gesture
    data class Global(val action: String) : Gesture
    data object LastTool : Gesture
    data object OpenWheel : Gesture
    data class SwitchTo(val toolId: String) : Gesture
}

data class Hud(val icon: String, val title: String, val detail: String = "",
               val progress: Float? = null, val direction: Int = 0,
               /** App switcher strip instead of the pill. */
               val strip: AppStrip? = null)

/** Recent apps with one highlighted. [commitInMs] > 0: it opens after that much quiet;
 *  [opened]: it just opened (last frame before the strip leaves). */
data class AppStrip(val apps: List<App>, val index: Int, val commitInMs: Long, val opened: Boolean = false)

interface Ui {
    fun wheelOpen(items: List<Tool>, index: Int)
    fun wheelMove(index: Int, direction: Int)
    fun wheelCommit(index: Int)
    fun wheelCancel()
    fun hud(h: Hud)
}

interface RotationControl {
    fun setPassthrough(on: Boolean)
    fun setDuck(factor: Float?)
    fun level(): Float?
}

/** Everything a tool can do to the phone. Implemented by the accessibility service. */
interface Actions {
    /** One full swipe: +1 = next (finger up, or right-to-left when [sideways]), -1 = back. */
    fun swipe(direction: Int, sideways: Boolean = false)
    fun zoom(scale: Float): Float          // returns the applied scale
    fun zoomScale(): Float
    fun brightness(): Float?               // 0..1, null if not permitted
    fun setBrightness(v: Float)
    fun torchAvailable(): Boolean
    fun torch(on: Boolean, level: Float = 1f)
    fun recentApps(): List<App>
    fun openApp(pkg: String)
    fun global(action: String)             // back, home, recents, notifications, quick_settings, screenshot, lock
    fun media(command: String)             // play_pause, next, previous
    fun launch(pkg: String)
    fun volume(): Float?
    fun haptic()
    /** Take a photo: press the camera app's shutter, or open the camera if it isn't in front. */
    fun shutter()
    /** A short slow drag (no fling): +1 moves content up (forward), -1 back. */
    fun nudge(direction: Int)
    /** Press the front app's play / pause control (by label), else tap the screen centre. */
    fun tapPlayPause()
    /** Media volume up / down by [steps] (controllers in the Volume tool). */
    fun stepVolume(steps: Int) {}
}

/** DialEvent.source prefix for events from a user's controller (core/Controls.kt). */
const val CONTROLLER = "controller:"

data class App(val pkg: String, val label: String)
