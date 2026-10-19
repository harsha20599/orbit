package app.orbit.dial.core

/**
 * Configurations: which button does what. One per device (a remote, a keyboard, the
 * phone's volume keys) plus one for earbuds / headphones (their music buttons and
 * volume), which comes from a preset (CMF Buds Pro 2, AirPods...).
 *
 * A configuration has buttons ([Input]) and bindings: action <- (button, press).
 * Actions are Orbit's own: move forward / back, open the wheel, select, plus any of
 * the press-action strings (core/Settings.kt): last_tool, media:play_pause,
 * launch:<pkg>, global:home ...
 *
 * Snappy: a button that only has a Tap fires on key down (and repeats while held when
 * it moves). Double / triple taps wait [PressRecognizer.GAP_MS] for the next tap,
 * but never after the highest count that button uses; a hold fires the moment it passes.
 */
enum class Press(val label: String) { TAP("Tap"), DOUBLE("Double tap"), TRIPLE("Triple tap"), HOLD("Hold") }

/** A button. [counted]: the device itself counts presses (earbud gestures, the
 *  dial's turns): it only ever "taps". */
data class Input(val id: String, val label: String, val counted: Boolean = false)

data class Trigger(val input: String, val press: Press = Press.TAP)

data class Binding(val action: String, val trigger: Trigger)

object OrbitActions {
    const val FORWARD = "forward"
    const val BACK = "back"
    const val OPEN = "open_wheel"
    const val SELECT = "select"
    /** Always listed, in this order. */
    val CORE = listOf(OPEN, FORWARD, BACK, SELECT)
    /** Extra actions a user can add. */
    val EXTRA = listOf("last_tool", "media:play_pause", "media:next", "media:previous", "launch:",
        "global:back", "global:home", "global:recents", "global:notifications", "global:screenshot", "global:lock")

    fun label(a: String): String = when {
        a == OPEN -> "Open the wheel"
        a == FORWARD -> "Move forward"
        a == BACK -> "Move back"
        a == SELECT -> "Select"
        a == "last_tool" -> "Previous tool"
        a == "media:play_pause" -> "Play / pause"
        a == "media:next" -> "Next track"
        a == "media:previous" -> "Previous track"
        a.startsWith("launch:") -> "Open an app"
        a == "global:back" -> "Back"
        a == "global:home" -> "Home"
        a == "global:recents" -> "Recent apps"
        a == "global:notifications" -> "Notifications"
        a == "global:screenshot" -> "Screenshot"
        a == "global:lock" -> "Lock screen"
        a.startsWith("tool:") -> "Switch tool"
        else -> a
    }

    fun hint(a: String): String = when (a) {
        OPEN -> "Shows the wheel of tools. Again closes it."
        FORWARD -> "Next item in the wheel. In a tool: next reel, next slide, louder…"
        BACK -> "Previous item. In a tool: the other way."
        SELECT -> "Picks the highlighted tool. In a tool: its press (shutter, play…)."
        else -> ""
    }
}

data class Config(
    val id: String,
    val name: String,
    /** Where its buttons come from: an Android InputDevice descriptor, [BUILTIN] (the
     *  phone's own keys), or [HEADPHONES] (music buttons and volume of any headphones). */
    val device: String?,
    val inputs: List<Input>,
    val bindings: List<Binding>,
    val enabled: Boolean = true,
    /** Headphones: which preset its buttons come from. */
    val preset: String? = null,
) {
    val isHeadphones get() = device == HEADPHONES

    fun triggerFor(action: String): Trigger? = bindings.firstOrNull { it.action == action }?.trigger
    fun actionFor(input: String, press: Press): String? =
        bindings.firstOrNull { it.trigger.input == input && it.trigger.press == press }?.action
    fun pressesOf(input: String): Set<Press> = bindings.filter { it.trigger.input == input }.map { it.trigger.press }.toSet()
    fun input(id: String) = inputs.firstOrNull { it.id == id }

    /** Bind [action] to [trigger] (null = not set). A trigger does one thing: whatever
     *  had it before loses it. Returns the new config and the action that lost it. */
    fun bind(action: String, trigger: Trigger?): Pair<Config, String?> {
        val taken = trigger?.let { t -> bindings.firstOrNull { it.trigger == t && it.action != action }?.action }
        val rest = bindings.filter { it.action != action && it.trigger != trigger }
        return copy(bindings = if (trigger == null) rest else rest + Binding(action, trigger)) to taken
    }

    fun withInputs(list: List<Input>) = copy(inputs = list, bindings = bindings.filter { b -> list.any { it.id == b.trigger.input } })

    companion object {
        const val HEADPHONES = "headphones"
        const val BUILTIN = "builtin"

        /** Sensible defaults for buttons in the order they were pressed. */
        fun defaults(inputs: List<Input>): List<Binding> {
            val ids = inputs.map { it.id }
            fun b(a: String, i: Int, p: Press = Press.TAP) = Binding(a, Trigger(ids[i], p))
            return when (ids.size) {
                0 -> emptyList()
                1 -> listOf(b(OrbitActions.FORWARD, 0), b(OrbitActions.SELECT, 0, Press.DOUBLE), b(OrbitActions.OPEN, 0, Press.HOLD))
                2 -> listOf(b(OrbitActions.FORWARD, 0), b(OrbitActions.BACK, 1),
                    b(OrbitActions.SELECT, 0, Press.HOLD), b(OrbitActions.OPEN, 1, Press.HOLD))
                3 -> listOf(b(OrbitActions.FORWARD, 0), b(OrbitActions.BACK, 1), b(OrbitActions.SELECT, 2),
                    b(OrbitActions.OPEN, 2, Press.HOLD))
                else -> listOf(b(OrbitActions.FORWARD, 0), b(OrbitActions.BACK, 1), b(OrbitActions.SELECT, 2),
                    b(OrbitActions.OPEN, 3), b("last_tool", 2, Press.HOLD))
            }
        }

        fun keys(id: String, name: String, device: String, inputs: List<Input>) =
            Config(id, name, device, inputs, defaults(inputs))

        fun phoneVolumeKeys(id: String) = keys(id, "Phone volume keys", BUILTIN,
            listOf(Input("key:24", "Volume +"), Input("key:25", "Volume −")))

        const val BACKTAP = "backtap"

        /** Pixel Quick Tap / Samsung RegiStar back tap, through Orbit's two app entries. */
        fun backTap(id: String) = Config(id, "Back of the phone", BACKTAP,
            listOf(Input("backtap:1", "Back tap", true), Input("backtap:2", "Back tap 2", true)),
            listOf(Binding(OrbitActions.SELECT, Trigger("backtap:1")), Binding(OrbitActions.OPEN, Trigger("backtap:2"))))

        fun headphones(preset: Preset = Presets.CMF) =
            Config(HEADPHONES, "Earbuds & headphones", HEADPHONES, preset.inputs, preset.bindings, preset = preset.id)
    }
}

data class Preset(val id: String, val name: String, val about: String, val inputs: List<Input>, val bindings: List<Binding>)

object Presets {
    private fun t(a: String, input: String, p: Press = Press.TAP) = Binding(a, Trigger(input, p))
    const val PLAY = "media:play"
    const val NEXT = "media:next"
    const val PREV = "media:prev"
    const val HOLD = "media:hold"
    const val UP = "vol:up"
    const val DOWN = "vol:down"
    const val HOOK = "media:hook"

    val CMF = Preset("cmf", "CMF Buds Pro 2", "The case dial: turn it, press, double, triple, hold.",
        listOf(Input(UP, "Turn forward", true), Input(DOWN, "Turn back", true), Input(PLAY, "Press", true),
            Input(NEXT, "Double press", true), Input(PREV, "Triple press", true), Input(HOLD, "Press and hold", true)),
        listOf(t(OrbitActions.OPEN, NEXT), t(OrbitActions.FORWARD, UP), t(OrbitActions.BACK, DOWN), t(OrbitActions.SELECT, PLAY),
            t("last_tool", PREV), t("launch:com.anthropic.claude", HOLD)))

    val EARBUDS = Preset("earbuds", "AirPods & other earbuds", "Their press or tap gestures: once, twice, three times.",
        listOf(Input(PLAY, "Press", true), Input(NEXT, "Double press", true), Input(PREV, "Triple press", true)),
        listOf(t(OrbitActions.OPEN, PREV), t(OrbitActions.FORWARD, NEXT), t(OrbitActions.SELECT, PLAY)))

    val SPEAKER = Preset("speaker", "Speaker or headphones with buttons", "Play, next, previous and volume buttons.",
        listOf(Input(UP, "Volume +", true), Input(DOWN, "Volume −", true), Input(PLAY, "Play / pause", true),
            Input(NEXT, "Next track", true), Input(PREV, "Previous track", true)),
        listOf(t(OrbitActions.OPEN, NEXT), t(OrbitActions.FORWARD, UP), t(OrbitActions.BACK, DOWN), t(OrbitActions.SELECT, PLAY),
            t("last_tool", PREV)))

    val WIRED = Preset("wired", "Wired earphones", "The one button on the cable.",
        listOf(Input(HOOK, "Cable button")), Config.defaults(listOf(Input(HOOK, "Cable button"))))

    val ALL = listOf(CMF, EARBUDS, SPEAKER, WIRED)
    fun byId(id: String?) = ALL.firstOrNull { it.id == id } ?: CMF
}

/** Turns one button's downs / ups into the presses its configuration uses. */
class PressRecognizer(presses: Set<Press>, repeat: Boolean, private val emit: (Press) -> Unit) {
    companion object {
        const val GAP_MS = 300L
        const val HOLD_MS = 500L
        const val REPEAT_DELAY_MS = 380L
        const val REPEAT_EVERY_MS = 110L
    }

    var presses = presses; private set
    private var repeat = repeat
    private var downAt: Long? = null
    private var firedOnDown = false
    private var holdFired = false
    private var nextRepeat = 0L
    private var taps = 0
    private var lastUp = 0L

    fun configure(p: Set<Press>, r: Boolean) { presses = p; repeat = r; reset() }
    fun reset() { downAt = null; taps = 0; firedOnDown = false; holdFired = false }

    private val instant get() = presses.none { it != Press.TAP }
    private val maxTaps get() = when { Press.TRIPLE in presses -> 3; Press.DOUBLE in presses -> 2; else -> 1 }

    fun down(now: Long) {
        if (downAt != null) return                        // the OS's own key repeat
        downAt = now; holdFired = false
        firedOnDown = instant
        if (instant) { if (Press.TAP in presses) emit(Press.TAP); nextRepeat = now + REPEAT_DELAY_MS }
    }

    fun up(now: Long) {
        downAt ?: return
        downAt = null
        if (firedOnDown || holdFired) return
        taps++; lastUp = now
        if (taps >= maxTaps) flush()
    }

    fun tick(now: Long) {
        val d = downAt
        if (d != null) {
            if (firedOnDown) { if (repeat) while (now >= nextRepeat) { emit(Press.TAP); nextRepeat += REPEAT_EVERY_MS } }
            else if (Press.HOLD in presses && !holdFired && now - d >= HOLD_MS) { holdFired = true; taps = 0; emit(Press.HOLD) }
        } else if (taps > 0 && now - lastUp >= GAP_MS) flush()
    }

    fun nextWake(): Long? {
        val d = downAt
        return when {
            d != null && firedOnDown -> if (repeat) nextRepeat else null
            d != null && Press.HOLD in presses && !holdFired -> d + HOLD_MS
            d == null && taps > 0 -> lastUp + GAP_MS
            else -> null
        }
    }

    private fun flush() {
        val p = when (taps) { 1 -> Press.TAP; 2 -> Press.DOUBLE; else -> Press.TRIPLE }
        taps = 0
        if (p in presses) emit(p)
    }
}

/** The DialEvent an action becomes (moves are turns, so every tool understands them). */
fun actionEvent(action: String, n: Int, source: String, t: Long): DialEvent = when (action) {
    OrbitActions.FORWARD -> DialEvent(Kind.ROTATE, n, source, t)
    OrbitActions.BACK -> DialEvent(Kind.ROTATE, -n, source, t)
    else -> DialEvent(Kind.CLICK, 0, source, t, action)
}

/** All enabled configurations: (device, button) in, DialEvents out. */
class ConfigHub(private val emit: (DialEvent) -> Unit) {
    private class Slot(val cfg: Config, val input: Input) { lateinit var r: PressRecognizer }
    private var slots: List<Slot> = emptyList()
    var configs: List<Config> = emptyList(); private set

    fun set(list: List<Config>) {
        slots.forEach { it.r.reset() }
        configs = list.filter { it.enabled }
        slots = configs.flatMap { c ->
            c.inputs.map { i ->
                val presses = c.pressesOf(i.id)
                val moves = presses == setOf(Press.TAP) &&
                    c.actionFor(i.id, Press.TAP) in setOf(OrbitActions.FORWARD, OrbitActions.BACK)
                Slot(c, i).also { s -> s.r = PressRecognizer(presses, moves) { p -> c.actionFor(i.id, p)?.let { emitAction(c, it, 1, null) } } }
            }
        }
    }

    private fun slot(device: String?, input: String) = slots.firstOrNull { it.cfg.device == device && it.input.id == input }

    fun has(device: String?, input: String) = slot(device, input) != null

    /** A key down / up. True if it belongs to a configuration (the platform swallows it). */
    fun onKey(device: String?, input: String, down: Boolean, now: Long): Boolean {
        val s = slot(device, input) ?: return false
        if (down) s.r.down(now) else s.r.up(now)
        return true
    }

    /** [n] taps of a button the device counts itself (earbud gesture, dial turn). */
    fun pulse(device: String, input: String, n: Int = 1, source: String? = null): Boolean {
        val s = slot(device, input) ?: return false
        val action = s.cfg.actionFor(input, Press.TAP) ?: return true
        emitAction(s.cfg, action, n, source)
        return true
    }

    private fun emitAction(c: Config, action: String, n: Int, source: String?) {
        emit(actionEvent(action, n, source ?: (CONTROLLER + c.name), Clock.now()))
    }

    fun tick(now: Long) = slots.forEach { it.r.tick(now) }
    fun nextWake(): Long? = slots.mapNotNull { it.r.nextWake() }.minOrNull()

    /** The headphones configuration uses the volume as a dial (else volume stays volume). */
    fun volumeIsDial(): Boolean = configs.any { c -> c.isHeadphones && c.bindings.any { it.trigger.input.startsWith("vol:") } }
}
