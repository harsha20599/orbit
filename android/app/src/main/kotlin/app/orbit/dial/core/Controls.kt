package app.orbit.dial.core

/**
 * Any buttons as an Orbit dial. A "controller" is a device (selfie-stick remote,
 * keyboard, the phone's own volume keys, a game pad...) with 1-4 buttons the user
 * pressed in the Add-a-controller screen. Each button gets a role from how many there
 * are, and its presses become the same DialEvents the buds' dial makes, so the Engine
 * and every tool work unchanged:
 *
 *   1 button   tap = next          hold = select       long hold = open the wheel
 *   2 buttons  A: tap = next, hold = select     B: tap = back one, hold = open the wheel
 *   3 buttons  A = next, B = back one (both repeat while held)
 *              C: tap = select, hold = open the wheel
 *   4 buttons  as 3, plus D: tap = previous tool, hold = assistant
 *
 * Snappy by design: no multi-tap waits. A button with nothing on hold fires on key
 * down; one with a hold action fires its tap on release (<450 ms), its hold the
 * moment the threshold passes.
 */
enum class Act(val label: String) {
    NEXT("Next"), PREV("Back one"), SELECT("Select"), MENU("Open the wheel"),
    BACK("Previous tool"), ASSIST("Assistant"), NONE("");

    fun event(source: String, t: Long): DialEvent? = when (this) {
        NEXT -> DialEvent(Kind.ROTATE, 1, source, t)
        PREV -> DialEvent(Kind.ROTATE, -1, source, t)
        SELECT -> DialEvent(Kind.CLICK, 0, source, t)
        MENU -> DialEvent(Kind.DOUBLE, 0, source, t)
        BACK -> DialEvent(Kind.TRIPLE, 0, source, t)
        ASSIST -> DialEvent(Kind.HOLD, 0, source, t)
        NONE -> null
    }
}

data class Button(
    val key: Int,
    val label: String,
    val tap: Act,
    val hold: Act = Act.NONE,
    val longHold: Act = Act.NONE,
    /** Keep firing [tap] while held (scrolling, stepping through the wheel). */
    val repeat: Boolean = false,
) {
    fun summary(): String = buildList {
        add("tap: ${tap.label.lowercase()}")
        if (hold != Act.NONE) add("hold: ${hold.label.lowercase()}")
        if (longHold != Act.NONE) add("hold longer: ${longHold.label.lowercase()}")
        if (repeat) add("hold to repeat")
    }.joinToString(" · ")
}

data class Controller(
    val id: String,
    val name: String,
    /** Stable device id (Android InputDevice.descriptor); null = any device. */
    val device: String?,
    val buttons: List<Button>,
    val enabled: Boolean = true,
) {
    companion object {
        const val MAX_BUTTONS = 4

        /** Roles for buttons in the order the user pressed them. */
        fun layout(keys: List<Pair<Int, String>>): List<Button> {
            val k = keys.take(MAX_BUTTONS)
            return k.mapIndexed { i, (code, label) ->
                when (k.size) {
                    1 -> Button(code, label, Act.NEXT, Act.SELECT, Act.MENU)
                    2 -> if (i == 0) Button(code, label, Act.NEXT, Act.SELECT) else Button(code, label, Act.PREV, Act.MENU)
                    else -> when (i) {
                        0 -> Button(code, label, Act.NEXT, repeat = true)
                        1 -> Button(code, label, Act.PREV, repeat = true)
                        2 -> Button(code, label, Act.SELECT, Act.MENU)
                        else -> Button(code, label, Act.BACK, Act.ASSIST)
                    }
                }
            }
        }
    }
}

/**
 * Key downs / ups of one controller in, Actions out. Platform calls [down]/[up] per
 * key event and [tick] at [nextWake] (or every ~20 ms); everything is time-injected
 * so it's unit-testable.
 */
class ButtonRecognizer(
    private var buttons: List<Button>,
    private val emit: (Act, Button) -> Unit,
) {
    companion object {
        const val HOLD_MS = 450L
        const val LONG_MS = 1100L
        const val REPEAT_DELAY_MS = 380L
        const val REPEAT_EVERY_MS = 110L
    }

    private class Held(val b: Button, val at: Long) {
        var fired: Act? = null           // the hold / long hold already sent
        var nextRepeat = at + REPEAT_DELAY_MS
    }

    private val held = HashMap<Int, Held>()

    fun setButtons(b: List<Button>) { buttons = b; held.clear() }
    fun has(key: Int) = buttons.any { it.key == key }

    /** True if [key] is one of ours (the platform should swallow the event). */
    fun down(key: Int, now: Long): Boolean {
        val b = buttons.firstOrNull { it.key == key } ?: return false
        if (key in held) return true                     // OS auto-repeat: we do our own
        held[key] = Held(b, now)
        if (b.hold == Act.NONE && b.longHold == Act.NONE) emit(b.tap, b)
        return true
    }

    fun up(key: Int, now: Long): Boolean {
        val b = buttons.firstOrNull { it.key == key } ?: return false
        val h = held.remove(key) ?: return true
        if (h.fired != null) return true
        if (b.hold == Act.NONE && b.longHold == Act.NONE) return true      // tapped on down
        val dur = now - h.at
        when {
            dur < HOLD_MS -> emit(b.tap, b)
            b.hold != Act.NONE -> emit(b.hold, b)          // released between hold and long hold
            else -> emit(b.tap, b)
        }
        return true
    }

    fun tick(now: Long) {
        for (h in held.values.toList()) {
            val b = h.b
            if (h.fired == null) {
                if (b.longHold != Act.NONE && now - h.at >= LONG_MS) { h.fired = b.longHold; emit(b.longHold, b) }
                else if (b.longHold == Act.NONE && b.hold != Act.NONE && now - h.at >= HOLD_MS) { h.fired = b.hold; emit(b.hold, b) }
            }
            if (b.repeat) while (now >= h.nextRepeat) { emit(b.tap, b); h.nextRepeat += REPEAT_EVERY_MS }
        }
    }

    /** When [tick] next has something to do (null = nothing held). */
    fun nextWake(): Long? = held.values.mapNotNull { h ->
        val b = h.b
        listOfNotNull(
            if (h.fired == null && b.longHold != Act.NONE) h.at + LONG_MS else null,
            if (h.fired == null && b.longHold == Act.NONE && b.hold != Act.NONE) h.at + HOLD_MS else null,
            if (b.repeat) h.nextRepeat else null,
        ).minOrNull()
    }.minOrNull()

    fun releaseAll() = held.clear()
}

/** All of the user's controllers: routes a (device, key) to the right one. */
class ControllerHub(private val emit: (DialEvent) -> Unit) {
    private class Entry(val c: Controller, val r: ButtonRecognizer)
    private var entries: List<Entry> = emptyList()

    fun set(controllers: List<Controller>) {
        entries.forEach { it.r.releaseAll() }
        entries = controllers.filter { it.enabled && it.buttons.isNotEmpty() }.map { c ->
            Entry(c, ButtonRecognizer(c.buttons) { act, _ -> act.event("$CONTROLLER${c.name}", Clock.now())?.let(emit) })
        }
    }

    // a device-specific controller wins over an any-device one for the same key
    private fun find(device: String?, key: Int): Entry? =
        entries.firstOrNull { it.c.device != null && it.c.device == device && it.r.has(key) }
            ?: entries.firstOrNull { it.c.device == null && it.r.has(key) }

    fun onKey(device: String?, key: Int, down: Boolean, now: Long): Boolean {
        val e = find(device, key) ?: return false
        return if (down) e.r.down(key, now) else e.r.up(key, now)
    }

    fun tick(now: Long) = entries.forEach { it.r.tick(now) }
    fun nextWake(): Long? = entries.mapNotNull { it.r.nextWake() }.minOrNull()
    fun isEmpty() = entries.isEmpty()
}

/**
 * One physical button that has to do everything (a wired earphone remote's only
 * button: Android sends HEADSETHOOK for every press and leaves the counting to us).
 * Presses within [GAP_MS] of each other are one gesture: 1 = press, 2 = double,
 * 3+ = triple; held past [HOLD_MS] = hold, sent the moment it passes.
 */
class TapCounter(private val emit: (Kind) -> Unit) {
    companion object {
        const val GAP_MS = 320L
        const val HOLD_MS = 650L
    }

    private var taps = 0
    private var downAt: Long? = null
    private var lastUp = 0L
    private var held = false

    fun down(now: Long) {
        if (downAt != null) return                     // auto-repeat
        downAt = now; held = false
    }

    fun up(now: Long) {
        downAt ?: return
        downAt = null
        if (held) return
        taps++; lastUp = now
        if (taps >= 3) flush()
    }

    fun tick(now: Long) {
        val d = downAt
        if (d != null && !held && now - d >= HOLD_MS) { held = true; taps = 0; emit(Kind.HOLD); return }
        if (d == null && taps > 0 && now - lastUp >= GAP_MS) flush()
    }

    fun nextWake(): Long? = when {
        downAt != null && !held -> downAt!! + HOLD_MS
        downAt == null && taps > 0 -> lastUp + GAP_MS
        else -> null
    }

    private fun flush() {
        val k = when (taps) { 1 -> Kind.CLICK; 2 -> Kind.DOUBLE; else -> Kind.TRIPLE }
        taps = 0
        emit(k)
    }
}
