package app.orbit.dial.core

/**
 * Controls: which trigger does which function. One setup for everything:
 *
 *   Select        <- e.g. "Volume − · hold", "Earbuds: press"
 *   Open menu     <- e.g. "Back tap"
 *   Move left     <- e.g. "Volume − · tap"
 *   Move right    <- e.g. "Volume + · tap", "CMF dial: turn forward"
 *
 * A trigger is an input (a key, an earbud gesture, a dial turn, a back tap), how it's
 * pressed, and optionally the one device it must come from. Triggers from different
 * sources mix freely, and a function can have several.
 *
 * Snappy: a key whose only use is a plain tap fires on key down (and repeats while
 * held when it moves). Double / triple taps wait [PressRecognizer.GAP_MS] for the
 * next tap but never after the highest count in use; holds fire the moment they pass.
 */
enum class Press(val label: String) { TAP("Tap"), DOUBLE("Double tap"), TRIPLE("Triple tap"), HOLD("Hold") }

/**
 * [input]: "key:<code>[+ctrl][+alt][+shift][+meta]", "mouse:back|forward",
 * "media:play|next|prev|hold|hook", "vol:up|down", "backtap:1|2".
 * [device]: null = from any device; else the InputDevice it was recorded on.
 */
data class Trigger(val input: String, val press: Press = Press.TAP, val device: String? = null, val deviceName: String? = null) {
    /** The device counts presses itself (earbud gestures, dial turns, back taps): always a "tap". */
    val counted get() = Inputs.counted(input)
    fun normalized() = if (counted) copy(press = Press.TAP) else this
    fun label(): String {
        val base = Inputs.label(input)
        val how = if (counted) "" else " · ${press.label.lowercase()}"
        val on = deviceName?.let { " on $it" } ?: ""
        return base + how + on
    }
}

data class Binding(val action: String, val trigger: Trigger)

object Inputs {
    fun counted(input: String) = input.startsWith("vol:") || input.startsWith("backtap:") ||
        (input.startsWith("media:") && input != "media:hook")

    private val keyNames = mapOf(
        24 to "Volume +", 25 to "Volume −", 164 to "Mute", 27 to "Camera button", 80 to "Focus button",
        66 to "Enter", 160 to "Enter", 62 to "Space", 61 to "Tab", 111 to "Esc", 67 to "Backspace", 112 to "Delete",
        19 to "Up", 20 to "Down", 21 to "Left", 22 to "Right", 23 to "Centre", 92 to "Page up", 93 to "Page down",
        122 to "Home key", 123 to "End", 85 to "Play / pause key", 87 to "Next track key", 88 to "Previous track key",
        79 to "Headset button", 96 to "Game pad A", 97 to "Game pad B", 99 to "Game pad X", 100 to "Game pad Y",
        102 to "Game pad L1", 103 to "Game pad R1", 108 to "Game pad Start", 109 to "Game pad Select",
    ) + (131..142).associateWith { "F${it - 130}" } + (29..54).associateWith { ('A' + (it - 29)).toString() } +
        (7..16).associateWith { ((it - 7)).toString() }

    fun keyName(code: Int) = keyNames[code] ?: "Key $code"

    fun label(input: String): String {
        if (input.startsWith("key:")) {
            val parts = input.removePrefix("key:").split("+")
            val mods = parts.drop(1).map { it.replaceFirstChar { c -> c.uppercase() } }
            return (mods + keyName(parts[0].toIntOrNull() ?: -1)).joinToString("+")
        }
        return when (input) {
            "mouse:back" -> "Mouse back button"
            "mouse:forward" -> "Mouse forward button"
            "media:play" -> "Earbuds: press"
            "media:next" -> "Earbuds: double press"
            "media:prev" -> "Earbuds: triple press"
            "media:hold" -> "Earbuds: press and hold"
            "media:hook" -> "Cable button"
            "vol:up" -> "Dial forward / headphone volume +"
            "vol:down" -> "Dial back / headphone volume −"
            "backtap:1" -> "Back tap"
            "backtap:2" -> "Back tap 2"
            else -> input
        }
    }
}

object OrbitActions {
    const val SELECT = "select"
    const val OPEN = "open_wheel"
    const val BACK = "back"
    const val FORWARD = "forward"
    /** The functions every setup shows, in this order. */
    val CORE = listOf(SELECT, OPEN, BACK, FORWARD)
    /** Functions a user can add. */
    val EXTRA = listOf("last_tool", "media:play_pause", "media:next", "media:previous", "launch:",
        "global:back", "global:home", "global:recents", "global:notifications", "global:screenshot", "global:lock")

    fun label(a: String): String = when {
        a == SELECT -> "Select"
        a == OPEN -> "Open menu"
        a == BACK -> "Move left"
        a == FORWARD -> "Move right"
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
        SELECT -> "Picks the highlighted tool. In a tool: its press (shutter, play…)."
        OPEN -> "Shows the wheel of tools. Again closes it."
        BACK -> "Previous item. In a tool: back, quieter, previous slide…"
        FORWARD -> "Next item. In a tool: next reel, louder, next slide…"
        else -> ""
    }
}

data class Controls(val bindings: List<Binding>, val preset: String? = null) {
    fun triggers(action: String) = bindings.filter { it.action == action }.map { it.trigger }
    fun actionFor(t: Trigger) = bindings.firstOrNull { it.trigger == t }?.action
    val actions get() = (OrbitActions.CORE + bindings.map { it.action }.filter { it !in OrbitActions.CORE }).distinct()

    /** Add [t] to [action]; a trigger does one thing, so whoever had it loses it.
     *  Returns the new controls and the action that lost it. */
    fun add(action: String, t: Trigger): Pair<Controls, String?> {
        val n = t.normalized()
        val lost = bindings.firstOrNull { it.trigger == n && it.action != action }?.action
        return copy(bindings = bindings.filter { it.trigger != n } + Binding(action, n), preset = null) to lost
    }

    fun remove(action: String, t: Trigger) = copy(bindings = bindings.filterNot { it.action == action && it.trigger == t }, preset = null)
    fun clear(action: String) = copy(bindings = bindings.filterNot { it.action == action }, preset = null)

    fun uses(prefix: String) = bindings.any { it.trigger.input.startsWith(prefix) }
}

data class Preset(val id: String, val name: String, val about: String, val controls: Controls)

object Presets {
    private fun b(a: String, input: String, p: Press = Press.TAP) = Binding(a, Trigger(input, p))
    private fun p(id: String, name: String, about: String, vararg bs: Binding) = Preset(id, name, about, Controls(bs.toList(), id))

    val CMF = p("cmf", "CMF Buds Pro 2", "Turn the case dial to move; press, double, triple, hold.",
        b(OrbitActions.SELECT, "media:play"), b(OrbitActions.OPEN, "media:next"),
        b(OrbitActions.BACK, "vol:down"), b(OrbitActions.FORWARD, "vol:up"),
        b("last_tool", "media:prev"), b("launch:com.anthropic.claude", "media:hold"))
    val EARBUDS = p("earbuds", "AirPods & other earbuds", "Press or tap the earbud once, twice, three times.",
        b(OrbitActions.SELECT, "media:play"), b(OrbitActions.FORWARD, "media:next"), b(OrbitActions.OPEN, "media:prev"))
    val SPEAKER = p("speaker", "Speaker or headphones with buttons", "Play, next / previous and volume buttons.",
        b(OrbitActions.SELECT, "media:play"), b(OrbitActions.OPEN, "media:next"),
        b(OrbitActions.BACK, "vol:down"), b(OrbitActions.FORWARD, "vol:up"), b("last_tool", "media:prev"))
    val WIRED = p("wired", "Wired earphones", "The one button on the cable.",
        b(OrbitActions.FORWARD, "media:hook"), b(OrbitActions.SELECT, "media:hook", Press.DOUBLE), b(OrbitActions.OPEN, "media:hook", Press.HOLD))
    val VOLUME_KEYS = p("volume_keys", "Volume keys", "The phone's volume keys, or a selfie stick's.",
        b(OrbitActions.BACK, "key:25"), b(OrbitActions.FORWARD, "key:24"),
        b(OrbitActions.SELECT, "key:25", Press.HOLD), b(OrbitActions.OPEN, "key:24", Press.HOLD))
    val VOLUME_BACKTAP = p("volume_backtap", "Volume keys + back tap", "Volume keys move; tap the back to select or open.",
        b(OrbitActions.BACK, "key:25"), b(OrbitActions.FORWARD, "key:24"),
        b(OrbitActions.SELECT, "backtap:1"), b(OrbitActions.OPEN, "backtap:2"))

    val ALL = listOf(CMF, EARBUDS, SPEAKER, WIRED, VOLUME_KEYS, VOLUME_BACKTAP)
    fun byId(id: String?) = ALL.firstOrNull { it.id == id }
    val DEFAULT get() = CMF.controls
}

/** Turns one input's downs / ups into the presses in use. */
class PressRecognizer(presses: Set<Press>, private var repeat: Boolean, private val emit: (Press) -> Unit) {
    companion object {
        const val GAP_MS = 300L
        const val HOLD_MS = 500L
        const val REPEAT_DELAY_MS = 380L
        const val REPEAT_EVERY_MS = 110L
    }

    var presses = presses; private set
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

/** The DialEvent a function becomes (moves are turns, so every tool understands them). */
fun actionEvent(action: String, n: Int, source: String, t: Long): DialEvent = when (action) {
    OrbitActions.FORWARD -> DialEvent(Kind.ROTATE, n, source, t)
    OrbitActions.BACK -> DialEvent(Kind.ROTATE, -n, source, t)
    else -> DialEvent(Kind.CLICK, 0, source, t, action)
}

/** The live controls: inputs in, DialEvents out. */
class ControlsHub(private val emit: (DialEvent) -> Unit) {
    /** One trigger input (from one device, or any). Each physical device pressing it gets
     *  its own recognizer, so two remotes never mix their taps. */
    private class Slot(val device: String?, val input: String, val presses: Set<Press>, val repeat: Boolean,
                       val onPress: (Press) -> Unit) {
        val byDevice = HashMap<String?, PressRecognizer>()
        fun r(dev: String?) = byDevice.getOrPut(dev) { PressRecognizer(presses, repeat, onPress) }
    }
    private var slots: List<Slot> = emptyList()
    var controls = Controls(emptyList()); private set

    fun set(c: Controls) {
        slots.forEach { s -> s.byDevice.values.forEach { it.reset() } }
        controls = c
        slots = c.bindings.filterNot { it.trigger.counted }.map { it.trigger.device to it.trigger.input }.distinct().map { (dev, input) ->
            val mine = c.bindings.filter { it.trigger.device == dev && it.trigger.input == input }
            val presses = mine.map { it.trigger.press }.toSet()
            val moves = presses == setOf(Press.TAP) && mine.single().action in setOf(OrbitActions.FORWARD, OrbitActions.BACK)
            Slot(dev, input, presses, moves) { p -> mine.firstOrNull { it.trigger.press == p }?.let { emitAction(it.action, 1, null) } }
        }
    }

    // a trigger recorded on one device wins over the same key from any device
    private fun slot(device: String?, input: String) =
        slots.firstOrNull { it.device != null && it.device == device && it.input == input } ?: slots.firstOrNull { it.device == null && it.input == input }

    fun has(device: String?, input: String) = slot(device, input) != null

    /** A key down / up. True if a control uses it (the platform swallows it). */
    fun onKey(device: String?, input: String, down: Boolean, now: Long): Boolean {
        val s = slot(device, input) ?: return false
        if (down) s.r(device).down(now) else s.r(device).up(now)
        return true
    }

    /** [n] of an input the device counts itself (earbud gesture, dial turn, back tap). */
    fun pulse(input: String, n: Int = 1, source: String? = null): Boolean {
        val action = controls.bindings.firstOrNull { it.trigger.input == input }?.action ?: return false
        emitAction(action, n, source)
        return true
    }

    private fun emitAction(action: String, n: Int, source: String?) =
        emit(actionEvent(action, n, source ?: (CONTROLLER + "controls"), Clock.now()))

    fun tick(now: Long) = slots.forEach { s -> s.byDevice.values.forEach { it.tick(now) } }
    fun nextWake(): Long? = slots.flatMap { it.byDevice.values }.mapNotNull { it.nextWake() }.minOrNull()

    /** Headphone volume drives Orbit (else volume stays volume). */
    fun volumeIsDial() = controls.uses("vol:")
}
