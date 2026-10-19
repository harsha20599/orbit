package app.orbit.dial

import android.view.KeyEvent
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.orbit.dial.core.Act
import app.orbit.dial.core.ButtonRecognizer
import app.orbit.dial.core.Clock
import app.orbit.dial.core.Controller
import kotlinx.coroutines.delay

private val transparentItem @Composable get() = ListItemDefaults.colors(containerColor = Color.Transparent)

/** Home: what drives Orbit. The buds / headphones are always there; added controllers below. */
fun LazyListScope.controllersSection(tick: Int, onAdd: () -> Unit, onChanged: () -> Unit) {
    item { Section("Controllers", "What drives Orbit. Add a remote, keyboard, selfie-stick button, game pad or your phone's volume keys.") }
    item {
        val ctx = LocalContext.current
        val list = remember(tick) { ControllerStore.load(ctx) }
        var removing by remember { mutableStateOf<Controller?>(null) }
        Group {
            ListItem(colors = transparentItem,
                leadingContent = { RowIcon(R.drawable.ic_volume) },
                headlineContent = { Text("Earbuds, headphones & speakers", fontWeight = FontWeight.Medium) },
                supportingContent = { Text("Their music buttons and volume, Bluetooth or wired. Always on.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant) })
            list.forEach { c ->
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                ListItem(colors = transparentItem,
                    modifier = Modifier.clickable { removing = c },
                    leadingContent = { RowIcon(if (c.device == null || c.name == "This phone's buttons") R.drawable.ic_settings else R.drawable.ic_keyboard) },
                    headlineContent = { Text(c.name, fontWeight = FontWeight.Medium) },
                    supportingContent = { Text("${c.buttons.size} button${if (c.buttons.size == 1) "" else "s"}: " +
                        c.buttons.joinToString(", ") { it.label }, color = MaterialTheme.colorScheme.onSurfaceVariant) },
                    trailingContent = { Switch(c.enabled, { ControllerStore.setEnabled(ctx, c.id, it); onChanged() }) })
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            ListItem(colors = transparentItem,
                modifier = Modifier.clickable(onClick = onAdd),
                leadingContent = { RowIcon(R.drawable.ic_plus, MaterialTheme.colorScheme.primary) },
                headlineContent = { Text("Add a controller", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) })
        }
        removing?.let { c ->
            AlertDialog(onDismissRequest = { removing = null },
                title = { Text(c.name) },
                text = { Text(c.buttons.joinToString("\n") { "${it.label}: ${it.summary()}" }) },
                confirmButton = { TextButton({ removing = null }) { Text("Done") } },
                dismissButton = { TextButton({ ControllerStore.remove(ctx, c.id); removing = null; onChanged() }) {
                    Text("Remove", color = MaterialTheme.colorScheme.error) } })
        }
    }
}

@Composable
private fun RowIcon(res: Int, tint: Color = MaterialTheme.colorScheme.onSurfaceVariant) {
    Icon(painterResource(res), null, Modifier.size(20.dp), tint = tint)
}

/**
 * Add a controller: press any button and it's in. Everything pressed here is
 * captured (nothing happens on the phone), the roles update as buttons are added, and
 * the buttons can be tried right away before saving.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddControllerScreen(a11yOn: Boolean, orbitOn: Boolean, onSetUpA11y: () -> Unit, onClose: (saved: Boolean) -> Unit) {
    val ctx = LocalContext.current
    var device by remember { mutableStateOf<String?>(null) }
    var deviceName by remember { mutableStateOf("") }
    val keys = remember { mutableStateListOf<Pair<Int, String>>() }
    var flash by remember { mutableIntStateOf(-1) }           // key last pressed, for the row highlight
    var flashAt by remember { mutableLongStateOf(0L) }
    var lastAct by remember { mutableStateOf<Act?>(null) }
    var actAt by remember { mutableLongStateOf(0L) }
    var note by remember { mutableStateOf<String?>(null) }
    var uiNow by remember { mutableLongStateOf(Clock.now()) }
    var media by remember { mutableStateOf(false) }
    var typing by remember { mutableStateOf(false) }
    val preview = remember { ButtonRecognizer(emptyList()) { a, _ -> lastAct = a; actAt = Clock.now() } }

    // capture while open; the heartbeat lets it lapse by itself if this screen dies
    DisposableEffect(Unit) { onDispose { Orbit.captureUntil = 0L } }
    LaunchedEffect(Unit) {
        while (true) {
            Orbit.captureUntil = Clock.now() + 1500
            preview.tick(Clock.now())
            uiNow = Clock.now()
            delay(20)
        }
    }
    LaunchedEffect(Unit) {
        Orbit.captured.collect { c ->
            val now = Clock.now()
            if (c.media) { media = true; return@collect }
            if (device != null && c.device != device) {
                if (c.down) note = "That was “${c.deviceName}”. Add one controller at a time: save this one first."
                return@collect
            }
            val known = keys.any { it.first == c.key }
            if (c.down) { flash = c.key; flashAt = now }
            when {
                known -> if (c.down) preview.down(c.key, now) else preview.up(c.key, now)
                c.down && keys.size < Controller.MAX_BUTTONS -> {
                    if (device == null) { device = c.device; deviceName = c.deviceName; typing = c.typing }
                    keys += c.key to c.label
                    preview.setButtons(Controller.layout(keys.toList()))
                    note = null
                }
                c.down -> note = "Up to ${Controller.MAX_BUTTONS} buttons per controller."
            }
        }
    }

    val buttons = Controller.layout(keys.toList())
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Add a controller", fontWeight = FontWeight.SemiBold) },
                navigationIcon = { IconButton({ onClose(false) }) { Icon(painterResource(R.drawable.ic_x), "Cancel") } })
        },
        bottomBar = {
            Surface(color = MaterialTheme.colorScheme.surface) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End), verticalAlignment = Alignment.CenterVertically) {
                    if (keys.isNotEmpty()) TextButton({
                        keys.clear(); device = null; typing = false; preview.setButtons(emptyList()); note = null; lastAct = null
                    }) { Text("Start over") }
                    Button(enabled = keys.isNotEmpty(), onClick = {
                        ControllerStore.upsert(ctx, Controller(java.util.UUID.randomUUID().toString(), deviceName, device, buttons))
                        Orbit.log("controller added: $deviceName ${keys.map { it.second }}")
                        onClose(true)
                    }) { Text("Save") }
                }
            }
        },
    ) { pad ->
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp,
            top = pad.calculateTopPadding() + 8.dp, bottom = pad.calculateBottomPadding() + 24.dp)) {
            if (!a11yOn) item {
                Banner("Orbit's accessibility service is off, so it can't hear buttons yet.", "Turn on", onSetUpA11y)
            } else if (!orbitOn) item { Banner("Orbit is off. It saves the controller, but it works once Orbit is on.") }

            item {
                if (keys.isEmpty()) Listener()
                else DeviceCard(deviceName, keys.size, lastAct, actAt, uiNow)
            }

            if (media) item {
                Banner("That came through your headphones' music controls. Orbit already uses those, nothing to add: " +
                    "press = select, double press = open the wheel, triple = previous tool.")
            }

            if (keys.isNotEmpty()) {
                item { Spacer(Modifier.height(12.dp)) }
                item {
                    Group {
                        buttons.forEachIndexed { i, b ->
                            if (i > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                            val lit = flash == b.key && uiNow - flashAt < 400
                            val bg by animateColorAsState(if (lit) MaterialTheme.colorScheme.primary.copy(alpha = 0.16f) else Color.Transparent, label = "lit")
                            ListItem(colors = ListItemDefaults.colors(containerColor = bg),
                                leadingContent = { Badge("ABCD"[i].toString()) },
                                headlineContent = { Text(b.label, fontWeight = FontWeight.Medium) },
                                supportingContent = { Text(b.summary().replaceFirstChar { it.uppercase() },
                                    color = MaterialTheme.colorScheme.onSurfaceVariant) })
                        }
                    }
                }
                if (keys.any { it.first == KeyEvent.KEYCODE_VOLUME_UP || it.first == KeyEvent.KEYCODE_VOLUME_DOWN } &&
                    deviceName == "This phone's buttons") item {
                    Hint("Your volume keys will drive Orbit instead of the volume while the screen is on. " +
                        "To change the volume, pick the Volume tool, or turn Orbit off.", warn = true)
                }
            }
            if (typing && keys.isNotEmpty()) item {
                Hint("This is a typing keyboard: while Orbit is on, these keys drive Orbit instead of typing on it. " +
                    "Spare keys work best (F1–F12, arrows, Page up / down).", warn = true)
            }
            note?.let { item { Hint(it, warn = true) } }
            item {
                Hint("Works with anything that has buttons: Bluetooth remotes and selfie sticks, keyboards and knobs, " +
                    "game pads, presenters, and the phone's own volume keys. Earbud and AirPods gestures already work through their music controls.")
            }
        }
    }
}

@Composable
private fun Listener() {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val p by pulse.animateFloat(0f, 1f, infiniteRepeatable(tween(1600), RepeatMode.Restart), label = "p")
    val accent = MaterialTheme.colorScheme.primary
    Column(Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(132.dp), contentAlignment = Alignment.Center) {
            Canvas(Modifier.fillMaxSize()) {
                val r = size.minDimension / 2
                drawCircle(accent.copy(alpha = (1 - p) * 0.35f), r * (0.55f + 0.45f * p), style = Stroke(3.dp.toPx()))
                drawCircle(accent.copy(alpha = 0.14f), r * 0.5f)
                drawCircle(accent, r * 0.5f, style = Stroke(2.dp.toPx()))
            }
            Icon(painterResource(R.drawable.ic_keyboard), null, Modifier.size(34.dp), tint = accent)
        }
        Spacer(Modifier.height(14.dp))
        Text("Press any button", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text("on the remote, keyboard, selfie stick or game pad you want to use. Start with the one for “next”; your phone's volume keys work too.",
            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 420.dp))
    }
}

/** Once a device is heard: its name, how to add more, and a live "what that did" pill. */
@Composable
private fun DeviceCard(name: String, count: Int, act: Act?, at: Long, now: Long) {
    val fresh = act != null && now - at < 1200
    Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(20.dp),
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Row(Modifier.padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(painterResource(R.drawable.ic_keyboard), null, Modifier.size(26.dp), tint = MaterialTheme.colorScheme.onPrimaryContainer)
            Spacer(Modifier.size(14.dp))
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer)
                Text(when (count) {
                        1 -> "One button does it all. Want more? Press the one for “back” next."
                        2 -> "Add a third for “select”, or try these out and save."
                        3 -> "A fourth can go back to the previous tool. Or try them out and save."
                        else -> "That's ${Controller.MAX_BUTTONS} buttons. Try them out, then save."
                    },
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f))
            }
            Box(Modifier.widthIn(min = 120.dp), contentAlignment = Alignment.CenterEnd) {
                AnimatedContent(if (fresh) act!!.label else "", transitionSpec = { fadeIn(tween(80)) togetherWith fadeOut(tween(250)) }, label = "act") { l ->
                    if (l.isNotEmpty()) Surface(color = MaterialTheme.colorScheme.primary, shape = RoundedCornerShape(50)) {
                        Text(l, Modifier.padding(horizontal = 14.dp, vertical = 6.dp), color = MaterialTheme.colorScheme.onPrimary,
                            fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun Badge(text: String) {
    Box(Modifier.size(30.dp).background(MaterialTheme.colorScheme.secondaryContainer, CircleShape), contentAlignment = Alignment.Center) {
        Text(text, color = MaterialTheme.colorScheme.onSecondaryContainer, fontWeight = FontWeight.Bold, fontSize = 13.sp)
    }
}

@Composable
private fun Banner(text: String, action: String? = null, onAction: () -> Unit = {}) {
    Surface(color = MaterialTheme.colorScheme.tertiaryContainer, shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(text, Modifier.weight(1f), color = MaterialTheme.colorScheme.onTertiaryContainer,
                style = MaterialTheme.typography.bodyMedium)
            if (action != null) TextButton(onAction) { Text(action) }
        }
    }
}
