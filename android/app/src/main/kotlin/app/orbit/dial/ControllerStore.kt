package app.orbit.dial

import android.content.Context
import android.content.SharedPreferences
import android.view.InputDevice
import android.view.KeyEvent
import app.orbit.dial.core.Act
import app.orbit.dial.core.Button
import app.orbit.dial.core.Controller
import org.json.JSONArray
import org.json.JSONObject

/** The user's controllers, as JSON in Orbit's prefs. The accessibility service listens. */
object ControllerStore {
    const val KEY = "controllers"

    fun load(ctx: Context): List<Controller> = runCatching {
        val a = JSONArray(Orbit.prefs(ctx).getString(KEY, "[]"))
        (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            val bs = o.getJSONArray("buttons")
            Controller(
                id = o.getString("id"),
                name = o.getString("name"),
                device = o.optString("device").ifEmpty { null },
                enabled = o.optBoolean("enabled", true),
                buttons = (0 until bs.length()).map { j ->
                    val b = bs.getJSONObject(j)
                    Button(b.getInt("key"), b.getString("label"), Act.valueOf(b.getString("tap")),
                        Act.valueOf(b.optString("hold", "NONE")), Act.valueOf(b.optString("long", "NONE")),
                        b.optBoolean("repeat"))
                },
            )
        }
    }.getOrElse { Orbit.log("controllers unreadable, ignored: ${it.message}"); emptyList() }

    fun save(ctx: Context, list: List<Controller>) {
        val a = JSONArray()
        list.forEach { c ->
            a.put(JSONObject().apply {
                put("id", c.id); put("name", c.name); put("device", c.device ?: ""); put("enabled", c.enabled)
                put("buttons", JSONArray().apply {
                    c.buttons.forEach { b ->
                        put(JSONObject().apply {
                            put("key", b.key); put("label", b.label); put("tap", b.tap.name)
                            put("hold", b.hold.name); put("long", b.longHold.name); put("repeat", b.repeat)
                        })
                    }
                })
            })
        }
        Orbit.prefs(ctx).edit().putString(KEY, a.toString()).apply()
    }

    fun upsert(ctx: Context, c: Controller) {
        val l = load(ctx).filterNot { it.id == c.id || (c.device != null && it.device == c.device) }
        save(ctx, l + c)
    }

    fun remove(ctx: Context, id: String) = save(ctx, load(ctx).filterNot { it.id == id })
    fun setEnabled(ctx: Context, id: String, on: Boolean) =
        save(ctx, load(ctx).map { if (it.id == id) it.copy(enabled = on) else it })

    fun listen(ctx: Context, onChange: () -> Unit): SharedPreferences.OnSharedPreferenceChangeListener {
        val l = SharedPreferences.OnSharedPreferenceChangeListener { _, k -> if (k == KEY || k == "enabled") onChange() }
        Orbit.prefs(ctx).registerOnSharedPreferenceChangeListener(l)
        return l
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

    fun deviceId(d: InputDevice?): String? = if (d == null || d.id < 0 || d.isVirtual) "virtual" else d.descriptor

    private fun isExternal(d: InputDevice) =
        if (android.os.Build.VERSION.SDK_INT >= 29) d.isExternal else !d.name.contains("gpio", true)
}
