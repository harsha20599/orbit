package app.orbit.dial

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.asImageBitmap
import androidx.core.graphics.drawable.toBitmap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import app.orbit.dial.core.Kind
import app.orbit.dial.core.OrbitSettings
import app.orbit.dial.core.Tool
import app.orbit.dial.core.defaultTools
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

private val GESTURE_NAMES = mapOf(Kind.CLICK to "Press", Kind.DOUBLE to "Double press",
    Kind.TRIPLE to "Triple press", Kind.HOLD to "Press and hold")

private val PRESETS = listOf(
    "Open the wheel" to OrbitSettings.OPEN_WHEEL,
    "Play / pause" to "media:play_pause",
    "Next track" to "media:next",
    "Previous track" to "media:previous",
    "Back to previous tool" to "last_tool",
    "Open an app…" to OPEN_APP,
    "Open Claude" to "launch:com.anthropic.claude",
    "Screenshot" to "global:screenshot",
    "Home" to "global:home",
    "Back" to "global:back",
    "Recent apps" to "global:recents",
    "Notifications" to "global:notifications",
    "Nothing" to "none",
)
private const val MAX_ITEMS = 12
private const val OPEN_APP = "launch:"
private val APPEARANCES = listOf("Match system" to "system", "Dark" to "dark", "Light" to "light")

/** Wheel items (Yes/No + order), the tool to start with, and what each press does.
 *  Every change is saved at once; the accessibility service rebuilds its engine. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CustomizeScreen(
    onBack: (() -> Unit)? = null,
    title: String = "Customize",
    top: androidx.compose.foundation.lazy.LazyListScope.() -> Unit = {},
    bottom: androidx.compose.foundation.lazy.LazyListScope.() -> Unit = {},
) {
    val ctx = LocalContext.current
    val all = remember { defaultTools() }
    val byId = remember { all.associateBy { it.id } }
    var s by remember { mutableStateOf(SettingsStore.load(ctx)) }
    fun update(n: OrbitSettings) { s = n; SettingsStore.save(ctx, n) }
    val options = PRESETS + all.filter { it.sticky }.map { "Switch to ${it.label}" to "tool:${it.id}" }
    var pickingFor by remember { mutableStateOf<Kind?>(null) }
    fun nameOf(v: String): String {
        options.firstOrNull { it.second == v }?.let { return it.first }
        if (v.startsWith(OPEN_APP)) {
            val pkg = v.removePrefix(OPEN_APP)
            val label = runCatching { ctx.packageManager.getApplicationLabel(ctx.packageManager.getApplicationInfo(pkg, 0)) }
                .getOrNull()?.toString() ?: pkg
            return "Open $label"
        }
        return v
    }
    val wheel = s.wheel(all)
    val opens = OrbitSettings.GESTURES.filter { s.gestures[it] == OrbitSettings.OPEN_WHEEL }

    pickingFor?.let { k ->
        AppPicker(onDismiss = { pickingFor = null }) { pkg ->
            update(s.copy(gestures = s.gestures + (k to OPEN_APP + pkg)))
            pickingFor = null
        }
    }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopAppBar(
                title = { Text(title, fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    if (onBack != null) IconButton(onBack) { Icon(painterResource(R.drawable.ic_arrow_left), "Back") }
                },
                actions = {
                    var menu by remember { mutableStateOf(false) }
                    Box {
                        IconButton({ menu = true }) { Icon(painterResource(R.drawable.ic_rotate_ccw), "Reset", Modifier.size(20.dp)) }
                        DropdownMenu(menu, { menu = false }) {
                            DropdownMenuItem(text = { Text("Reset wheel and gestures") },
                                onClick = { menu = false; SettingsStore.reset(ctx); s = SettingsStore.load(ctx) })
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { pad ->
        LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = pad.calculateTopPadding(),
            bottom = pad.calculateBottomPadding() + 24.dp)) {
            top()
            item {
                WheelPreview(wheel, s.defaultTool, rememberOverlayLook(s.appearance))
                Text(
                    "Open it, move to a tool, select it. Which buttons do that is up to you: see Controllers.",
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 4.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
            item { Section("Wheel items", "Switch on what the wheel shows. The order runs clockwise from the top.") }
            item {
                Group {
                    s.order.forEachIndexed { i, id ->
                        val t = byId[id] ?: return@forEachIndexed
                        if (i > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        ToolRow(t, id in s.enabled, first = i == 0, last = i == s.order.lastIndex,
                            onToggle = { on ->
                                val en = if (on) s.enabled + id else s.enabled - id
                                if (en.isNotEmpty() && en.size <= MAX_ITEMS) update(s.copy(enabled = en))
                            },
                            onMove = { d ->
                                val j = i + d
                                if (j in s.order.indices) update(s.copy(order = s.order.toMutableList().also {
                                    it[i] = it[j]; it[j] = id
                                }))
                            })
                    }
                }
                if (s.enabled.size == 1) Hint("The wheel needs at least one item.")
            }
            item { Section("Look", "The highlighted item lights up the wheel around it.") }
            item {
                Group {
                    PickerRow({ Icon(painterResource(R.drawable.ic_brightness), null, Modifier.size(20.dp)) },
                        "Appearance", APPEARANCES.first { it.second == s.appearance }.first, APPEARANCES, s.appearance) {
                        update(s.copy(appearance = it))
                    }
                }
            }
            item { Section("Start", "The tool Orbit starts on, before you pick one from the wheel.") }
            item {
                Group {
                    PickerRow({ Icon(painterResource(R.drawable.ic_star), null, Modifier.size(20.dp)) },
                        "Start with", byId[s.defaultTool]?.label ?: s.defaultTool,
                        all.filter { it.sticky }.map { it.label to it.id }, s.defaultTool) { update(s.copy(defaultTool = it)) }
                }
            }
            bottom()
        }
    }
}

// ---------------------------------------------------------------- pieces
@Composable
internal fun Section(title: String, sub: String) {
    Column(Modifier.padding(start = 4.dp, end = 4.dp, top = 28.dp, bottom = 12.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurface)
        Spacer(Modifier.height(4.dp))
        Text(sub, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
internal fun Group(content: @Composable () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surfaceContainer, shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth()) { Column { content() } }
}

@Composable
internal fun Hint(text: String, warn: Boolean = false) {
    Text(text, style = MaterialTheme.typography.bodySmall,
        color = if (warn) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(start = 4.dp, top = 8.dp))
}

@Composable
private fun ToolRow(t: Tool, on: Boolean, first: Boolean, last: Boolean,
                    onToggle: (Boolean) -> Unit, onMove: (Int) -> Unit) {
    val ink by animateColorAsState(
        if (on) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
        label = "rowInk")
    ListItem(
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        leadingContent = { Icon(painterResource(orbitIcon(t.icon)), null, Modifier.size(22.dp), tint = ink) },
        headlineContent = { Text(t.label, color = ink, fontWeight = FontWeight.Medium) },
        supportingContent = {
            Text((if (on) "Yes" else "No") + if (t.sticky) "" else " · runs once",
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        },
        trailingContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton({ onMove(-1) }, enabled = !first) {
                    Icon(painterResource(R.drawable.ic_chevron_up), "Move ${t.label} up", Modifier.size(20.dp))
                }
                IconButton({ onMove(1) }, enabled = !last) {
                    Icon(painterResource(R.drawable.ic_chevron_down), "Move ${t.label} down", Modifier.size(20.dp))
                }
                Spacer(Modifier.width(4.dp))
                Switch(on, onToggle, Modifier.semantics { contentDescription = "Show ${t.label} on the wheel" })
            }
        },
    )
}

@Composable
private fun PickerRow(lead: @Composable () -> Unit, label: String, value: String,
                      options: List<Pair<String, String>>, current: String, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        ListItem(
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
            modifier = Modifier.fillMaxWidth().clickable { open = true },
            leadingContent = { Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) { lead() } },
            headlineContent = { Text(label, fontWeight = FontWeight.Medium) },
            supportingContent = { Text(value, color = MaterialTheme.colorScheme.primary) },
            trailingContent = {
                Icon(painterResource(R.drawable.ic_chevron_down), null, Modifier.size(20.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            },
        )
        DropdownMenu(open, { open = false }, offset = androidx.compose.ui.unit.DpOffset(56.dp, 0.dp)) {
            options.forEachIndexed { i, (l, v) ->
                if (i > 0 && v.startsWith("tool:") && !options[i - 1].second.startsWith("tool:")) {
                    HorizontalDivider(Modifier.padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)
                }
                DropdownMenuItem(
                    text = { Text(l, color = if (v == current) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface) },
                    onClick = { open = false; onPick(v) })
            }
        }
    }
}

/** One, two or three taps, or one long press: how the gesture feels on the dial. */
@Composable
private fun Pips(k: Kind) {
    val c = MaterialTheme.colorScheme.onSurfaceVariant
    Canvas(Modifier.size(28.dp, 16.dp)) {
        val cy = size.height / 2
        if (k == Kind.HOLD) {
            drawLine(c, Offset(3.dp.toPx(), cy), Offset(size.width - 3.dp.toPx(), cy), 6.dp.toPx(), StrokeCap.Round)
        } else {
            val n = when (k) { Kind.CLICK -> 1; Kind.DOUBLE -> 2; else -> 3 }
            for (i in 0 until n) drawCircle(c, 3.dp.toPx(), Offset((5 + i * 8).dp.toPx(), cy))
        }
    }
}

/** The wheel as the overlay draws it: enabled items around the ring, the start tool
 *  lighting the wheel around it. Items and light glide when switched or reordered. */
@Composable
private fun WheelPreview(items: List<Tool>, start: String, look: OverlayLook) {
    val n = items.size.coerceAtLeast(1)
    val dia = 236.dp
    val orbit = 80.dp
    val startIdx = items.indexOfFirst { it.id == start }
    val lit by animateFloatAsState(if (startIdx < 0) 0f else startIdx * 360f / n,
        spring(0.7f, Spring.StiffnessMediumLow), label = "lit")
    Box(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 12.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(dia + 60.dp)) {
            val c = Offset(size.width / 2, size.height / 2)
            val R = dia.toPx() / 2
            val a = Math.toRadians(lit.toDouble())
            val lp = Offset(c.x + orbit.toPx() * sin(a).toFloat(), c.y - orbit.toPx() * cos(a).toFloat())
            val k = look.light
            if (startIdx >= 0) drawCircle(
                Brush.radialGradient(0f to look.accent.copy(alpha = 0.30f * k), 0.18f to look.accent.copy(alpha = 0.20f * k),
                    0.40f to look.accent.copy(alpha = 0.07f * k), 0.70f to look.accent.copy(alpha = 0.015f * k),
                    1f to Color.Transparent, center = lp, radius = R * 0.84f),
                radius = R + 15.dp.toPx(), center = c, style = Stroke(30.dp.toPx()))
            drawCircle(Color.Black.copy(alpha = if (look.dark) 0.35f else 0.14f), R, c + Offset(0f, 6.dp.toPx()))
            drawCircle(look.surface, R, c)
            drawCircle(look.edge, R, c, style = Stroke(1.dp.toPx()))
            if (startIdx >= 0) {
                drawCircle(
                    Brush.radialGradient(0f to look.accent.copy(alpha = 0.34f * k), 0.08f to look.accent.copy(alpha = 0.24f * k),
                        0.20f to look.accent.copy(alpha = 0.12f * k), 0.38f to look.accent.copy(alpha = 0.05f * k),
                        0.60f to look.accent.copy(alpha = 0.015f * k), 1f to Color.Transparent,
                        center = lp, radius = dia.toPx() * 0.62f),
                    radius = R - 1f, center = c)
                val sw = minOf(360f / n * 1.1f, 96f)
                for ((span, al) in listOf(2f to 0.10f, 1.1f to 0.25f, 0.5f to 0.55f)) {
                    drawArc(look.accent.copy(alpha = al * k), lit - 90f - sw * span / 2, sw * span, false,
                        Offset(c.x - R + 1f, c.y - R + 1f), Size(2 * R - 2f, 2 * R - 2f),
                        style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Butt))
                }
            }
            drawCircle(look.fg(0.06f), R - 12.dp.toPx(), c, style = Stroke(1.dp.toPx()))
        }
        items.forEachIndexed { i, t ->
            val ang by animateFloatAsState(i * 360f / n, spring(0.75f, Spring.StiffnessLow), label = "a_${t.id}")
            val rad = Math.toRadians(ang.toDouble())
            val on = t.id == start
            Icon(painterResource(orbitIcon(t.icon)), t.label,
                Modifier.offset { IntOffset((orbit.toPx() * sin(rad)).roundToInt(), (-orbit.toPx() * cos(rad)).roundToInt()) }.size(20.dp),
                tint = if (on) (if (look.dark) Color.White else look.accent) else look.inkDim)
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(items.firstOrNull { it.id == start }?.label ?: "-", color = look.ink, style = MaterialTheme.typography.titleMedium)
            Text("${items.size} item${if (items.size == 1) "" else "s"}", color = look.inkDim, style = MaterialTheme.typography.labelMedium)
        }
    }
}


/** Every app with a launcher icon, A to Z. */
@Composable
internal fun AppPicker(onDismiss: () -> Unit, onPick: (String) -> Unit) {
    val ctx = LocalContext.current
    val apps = remember {
        val pm = ctx.packageManager
        pm.queryIntentActivities(android.content.Intent(android.content.Intent.ACTION_MAIN)
            .addCategory(android.content.Intent.CATEGORY_LAUNCHER), 0)
            .map { it.activityInfo.packageName to it.loadLabel(pm).toString() }
            .filter { it.first != ctx.packageName }
            .distinctBy { it.first }
            .sortedBy { it.second.lowercase() }
    }
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Open which app?") },
        text = {
            LazyColumn(Modifier.height(420.dp)) {
                items(apps.size) { i ->
                    val (pkg, label) = apps[i]
                    val icon = remember(pkg) {
                        runCatching { ctx.packageManager.getApplicationIcon(pkg).toBitmap(72, 72).asImageBitmap() }.getOrNull()
                    }
                    ListItem(
                        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                        modifier = Modifier.clickable { onPick(pkg) },
                        leadingContent = { if (icon != null) androidx.compose.foundation.Image(icon, null, Modifier.size(32.dp)) },
                        headlineContent = { Text(label) },
                    )
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } },
    )
}
