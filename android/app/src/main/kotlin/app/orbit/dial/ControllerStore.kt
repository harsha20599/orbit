package app.orbit.dial

import android.content.Context
import android.content.SharedPreferences
import android.view.InputDevice
import android.view.KeyEvent
import app.orbit.dial.core.Binding
import app.orbit.dial.core.Controls
import app.orbit.dial.core.Press
import app.orbit.dial.core.Presets
import app.orbit.dial.core.Trigger
import org.json.JSONArray
import org.json.JSONObject

/** The controls, as JSON in Orbit's prefs (CMF Buds Pro 2 until the user changes them).
 *  The accessibility service listens and reloads Orbit's hub. */
object ControllerStore {
    const val KEY = "controls"

    fun load(ctx: Context): Controls = runCatching {
        val raw = Orbit.prefs(ctx).getString(KEY, null) ?: return Presets.DEFAULT
        val o = JSONObject(raw)
        val a = o.getJSONArray("bindings")
        Controls((0 until a.length()).mapNotNull { i ->
            val j = a.getJSONObject(i)
            runCatching {
                Binding(j.getString("action").let { if (it == "launch:com.anthropic.claude") "assistant" else it }, Trigger(j.getString("input"), Press.valueOf(j.getString("press")),
                    j.optString("device").ifEmpty { null }, j.optString("deviceName").ifEmpty { null }))
            }.getOrNull()
        }, o.optString("preset").ifEmpty { null })
    }.getOrElse { Orbit.log("controls unreadable, using the default: ${it.message}"); Presets.DEFAULT }

    fun save(ctx: Context, c: Controls) {
        val a = JSONArray()
        c.bindings.forEach { b ->
            a.put(JSONObject().put("action", b.action).put("input", b.trigger.input).put("press", b.trigger.press.name)
                .put("device", b.trigger.device ?: "").put("deviceName", b.trigger.deviceName ?: ""))
        }
        Orbit.prefs(ctx).edit().putString(KEY, JSONObject().put("bindings", a).put("preset", c.preset ?: "").toString()).apply()
        BackTapActivity.setAvailable(ctx, c.uses("backtap:"))   // the phone's back-tap setting lists them only while used
    }

    fun listen(ctx: Context, onChange: () -> Unit): SharedPreferences.OnSharedPreferenceChangeListener {
        val l = SharedPreferences.OnSharedPreferenceChangeListener { _, k -> if (k == KEY || k == "enabled") onChange() }
        Orbit.prefs(ctx).registerOnSharedPreferenceChangeListener(l)
        return l
    }

    // ---------------------------------------------------------------- naming
    /** Keys a control may never take: they'd lock the user out of the phone. */
    val RESERVED = setOf(KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_HOME, KeyEvent.KEYCODE_APP_SWITCH,
        KeyEvent.KEYCODE_POWER, KeyEvent.KEYCODE_SLEEP, KeyEvent.KEYCODE_WAKEUP, KeyEvent.KEYCODE_UNKNOWN)

    private val MODIFIERS = setOf(KeyEvent.KEYCODE_CTRL_LEFT, KeyEvent.KEYCODE_CTRL_RIGHT, KeyEvent.KEYCODE_ALT_LEFT,
        KeyEvent.KEYCODE_ALT_RIGHT, KeyEvent.KEYCODE_SHIFT_LEFT, KeyEvent.KEYCODE_SHIFT_RIGHT,
        KeyEvent.KEYCODE_META_LEFT, KeyEvent.KEYCODE_META_RIGHT)

    fun isModifier(code: Int) = code in MODIFIERS

    /** "key:62+ctrl+shift": the key with the modifiers held, or a mouse side button. */
    fun inputOf(e: KeyEvent): String? {
        val code = e.keyCode
        if (e.isFromSource(InputDevice.SOURCE_MOUSE)) {
            if (code == KeyEvent.KEYCODE_BACK) return "mouse:back"
            if (code == KeyEvent.KEYCODE_FORWARD) return "mouse:forward"
        }
        if (code in RESERVED || isModifier(code)) return null
        val mods = buildList {
            if (e.isCtrlPressed) add("ctrl"); if (e.isAltPressed) add("alt")
            if (e.isShiftPressed) add("shift"); if (e.isMetaPressed) add("meta")
        }
        return (listOf("key:$code") + mods).joinToString("+")
    }

    fun deviceName(d: InputDevice?): String = when {
        d == null || d.id < 0 || d.isVirtual -> "Test keyboard"
        !isExternal(d) -> "this phone"
        else -> d.name.ifBlank { "Bluetooth remote" }
    }

    fun deviceId(d: InputDevice?): String = when {
        d == null || d.id < 0 || d.isVirtual -> "virtual"
        !isExternal(d) -> "builtin"
        else -> d.descriptor
    }

    private fun isExternal(d: InputDevice) =
        if (android.os.Build.VERSION.SDK_INT >= 29) d.isExternal else !d.name.contains("gpio", true)
}
