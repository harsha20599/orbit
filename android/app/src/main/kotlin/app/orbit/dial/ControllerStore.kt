package app.orbit.dial

import android.content.Context
import android.content.SharedPreferences
import android.view.InputDevice
import android.view.KeyEvent
import app.orbit.dial.core.Binding
import app.orbit.dial.core.Config
import app.orbit.dial.core.Input
import app.orbit.dial.core.Press
import app.orbit.dial.core.Trigger
import org.json.JSONArray
import org.json.JSONObject

/**
 * The user's configurations, as JSON in Orbit's prefs. There's always an "Earbuds &
 * headphones" one (from a preset); the rest are the user's own. The accessibility
 * service listens and reloads Orbit's hub.
 */
object ControllerStore {
    const val KEY = "configs"

    fun load(ctx: Context): List<Config> {
        val list = runCatching {
            val a = JSONArray(Orbit.prefs(ctx).getString(KEY, "[]"))
            (0 until a.length()).map { i -> fromJson(a.getJSONObject(i)) }
        }.getOrElse { Orbit.log("configurations unreadable, reset: ${it.message}"); emptyList() }
        return if (list.any { it.isHeadphones }) list.sortedBy { if (it.isHeadphones) 0 else 1 }
        else listOf(Config.headphones()) + list
    }

    fun save(ctx: Context, list: List<Config>) {
        val a = JSONArray()
        list.forEach { a.put(toJson(it)) }
        Orbit.prefs(ctx).edit().putString(KEY, a.toString()).apply()
    }

    fun get(ctx: Context, id: String) = load(ctx).firstOrNull { it.id == id }
    fun put(ctx: Context, c: Config) {
        val l = load(ctx)
        save(ctx, if (l.any { it.id == c.id }) l.map { if (it.id == c.id) c else it } else l + c)
    }
    fun remove(ctx: Context, id: String) = save(ctx, load(ctx).filterNot { it.id == id && !it.isHeadphones })

    fun listen(ctx: Context, onChange: () -> Unit): SharedPreferences.OnSharedPreferenceChangeListener {
        val l = SharedPreferences.OnSharedPreferenceChangeListener { _, k -> if (k == KEY || k == "enabled") onChange() }
        Orbit.prefs(ctx).registerOnSharedPreferenceChangeListener(l)
        return l
    }

    private fun toJson(c: Config) = JSONObject().apply {
        put("id", c.id); put("name", c.name); put("device", c.device ?: ""); put("enabled", c.enabled)
        put("preset", c.preset ?: "")
        put("inputs", JSONArray().apply { c.inputs.forEach { put(JSONObject().put("id", it.id).put("label", it.label).put("counted", it.counted)) } })
        put("bindings", JSONArray().apply {
            c.bindings.forEach { put(JSONObject().put("action", it.action).put("input", it.trigger.input).put("press", it.trigger.press.name)) }
        })
    }

    private fun fromJson(o: JSONObject): Config {
        val ins = o.getJSONArray("inputs")
        val bs = o.getJSONArray("bindings")
        return Config(
            id = o.getString("id"), name = o.getString("name"),
            device = o.optString("device").ifEmpty { null }, enabled = o.optBoolean("enabled", true),
            preset = o.optString("preset").ifEmpty { null },
            inputs = (0 until ins.length()).map { ins.getJSONObject(it).let { j -> Input(j.getString("id"), j.getString("label"), j.optBoolean("counted")) } },
            bindings = (0 until bs.length()).mapNotNull { i ->
                val j = bs.getJSONObject(i)
                runCatching { Binding(j.getString("action"), Trigger(j.getString("input"), Press.valueOf(j.getString("press")))) }.getOrNull()
            },
        )
    }

    // ---------------------------------------------------------------- naming
    /** Keys a controller may never take: they'd lock the user out of the phone. */
    val RESERVED = setOf(KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_HOME, KeyEvent.KEYCODE_APP_SWITCH,
        KeyEvent.KEYCODE_POWER, KeyEvent.KEYCODE_SLEEP, KeyEvent.KEYCODE_WAKEUP, KeyEvent.KEYCODE_UNKNOWN)

    fun keyLabel(code: Int): String = when (code) {
        KeyEvent.KEYCODE_VOLUME_UP -> "Volume +"
        KeyEvent.KEYCODE_VOLUME_DOWN -> "Volume −"
        KeyEvent.KEYCODE_VOLUME_MUTE -> "Mute"
        KeyEvent.KEYCODE_CAMERA -> "Camera"
        KeyEvent.KEYCODE_FOCUS -> "Focus"
        KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER -> "Enter"
        KeyEvent.KEYCODE_SPACE -> "Space"
        KeyEvent.KEYCODE_DPAD_UP -> "Up"
        KeyEvent.KEYCODE_DPAD_DOWN -> "Down"
        KeyEvent.KEYCODE_DPAD_LEFT -> "Left"
        KeyEvent.KEYCODE_DPAD_RIGHT -> "Right"
        KeyEvent.KEYCODE_DPAD_CENTER -> "Centre"
        KeyEvent.KEYCODE_PAGE_UP -> "Page up"
        KeyEvent.KEYCODE_PAGE_DOWN -> "Page down"
        KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> "Play / pause"
        KeyEvent.KEYCODE_MEDIA_NEXT -> "Next track"
        KeyEvent.KEYCODE_MEDIA_PREVIOUS -> "Previous track"
        KeyEvent.KEYCODE_HEADSETHOOK -> "Headset button"
        else -> KeyEvent.keyCodeToString(code).removePrefix("KEYCODE_").replace('_', ' ').lowercase()
            .replaceFirstChar { it.uppercase() }
    }

    fun deviceName(d: InputDevice?): String = when {
        d == null || d.id < 0 || d.isVirtual -> "Test keyboard"
        !isExternal(d) -> "This phone's buttons"
        else -> d.name.ifBlank { "Bluetooth remote" }
    }

    fun deviceId(d: InputDevice?): String = when {
        d == null || d.id < 0 || d.isVirtual -> "virtual"
        !isExternal(d) -> Config.BUILTIN
        else -> d.descriptor
    }

    private fun isExternal(d: InputDevice) =
        if (android.os.Build.VERSION.SDK_INT >= 29) d.isExternal else !d.name.contains("gpio", true)
}
