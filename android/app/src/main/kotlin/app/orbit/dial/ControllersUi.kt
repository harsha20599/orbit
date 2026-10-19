package app.orbit.dial

import android.content.Intent
import android.provider.Settings
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
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
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.orbit.dial.core.Clock
import app.orbit.dial.core.Config
import app.orbit.dial.core.ConfigHub
import app.orbit.dial.core.Input
import app.orbit.dial.core.Kind
import app.orbit.dial.core.OrbitActions
import app.orbit.dial.core.Presets
import app.orbit.dial.core.Press
import app.orbit.dial.core.Trigger
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay

private val clear @Composable get() = ListItemDefaults.colors(containerColor = Color.Transparent)

@Composable
private fun Div() = HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

@Composable
private fun RowIcon(res: Int, tint: Color = MaterialTheme.colorScheme.onSurfaceVariant) =
    Icon(painterResource(res), null, Modifier.size(20.dp), tint = tint)

private fun iconFor(c: Config) = when {
    c.isHeadphones -> R.drawable.ic_volume
    c.device == Config.BACKTAP -> R.drawable.ic_bolt
    c.device == Config.BUILTIN -> R.drawable.ic_settings
    else -> R.drawable.ic_keyboard
}

/** "Double press" / "Volume − · hold": how a trigger reads to a person. */
private fun Config.describe(t: Trigger?): String {
    t ?: return "Not set"
    val i = input(t.input) ?: return "Not set"
    return if (i.counted) i.label else "${i.label} · ${t.press.label.lowercase()}"
}

private fun Config.summary(): String =
    if (isHeadphones) Presets.byId(preset).name
    else "Wheel: ${describe(triggerFor(OrbitActions.OPEN))} · Forward: ${describe(triggerFor(OrbitActions.FORWARD))}"

// =================================================================== home list

/** Home: one row per configuration, plus "Add a controller". */
fun LazyListScope.controllersSection(tick: Int, onOpen: (String) -> Unit, onAdd: () -> Unit, onChanged: () -> Unit) {
    item { Section("Controllers", "What drives Orbit, one setup per device: earbuds, remotes, keyboards, your phone's keys.") }
    item {
        val ctx = LocalContext.current
        val list = remember(tick) { ControllerStore.load(ctx) }
        Group {
            list.forEachIndexed { i, c ->
                if (i > 0) Div()
                ListItem(colors = clear,
                    modifier = Modifier.clickable { onOpen(c.id) },
                    leadingContent = { RowIcon(iconFor(c)) },
                    headlineContent = { Text(c.name, fontWeight = FontWeight.Medium) },
                    supportingContent = { Text(c.summary(), color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                        overflow = TextOverflow.Ellipsis) },
                    trailingContent = {
                        if (!c.isHeadphones) Switch(c.enabled, { ControllerStore.put(ctx, c.copy(enabled = it)); onChanged() })
                        else Icon(painterResource(R.drawable.ic_chevron_down), null, Modifier.size(18.dp).rotate(-90f),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    })
            }
            Div()
            ListItem(colors = clear,
                modifier = Modifier.clickable(onClick = onAdd),
                leadingContent = { RowIcon(R.drawable.ic_plus, MaterialTheme.colorScheme.primary) },
                headlineContent = { Text("Add a controller", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) })
        }
    }
}

// =================================================================== capture

/** Every button press while a controller screen is open: captured, nothing acts. */
@Composable
private fun CaptureButtons(onPress: (Orbit.Captured) -> Unit) {
    val cb by rememberUpdatedState(onPress)
    // only while this screen is in front: leave the app and every button works again at once
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val obs = androidx.lifecycle.LifecycleEventObserver { _, e ->
            if (e == androidx.lifecycle.Lifecycle.Event.ON_PAUSE) Orbit.captureUntil = 0L
        }
        lifecycle.addObserver(obs)
        onDispose { lifecycle.removeObserver(obs); Orbit.captureUntil = 0L }
    }
    LaunchedEffect(lifecycle) {
        lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.RESUMED) {
            try { while (true) { Orbit.captureUntil = Clock.now() + 1500; delay(500) } }
            finally { Orbit.captureUntil = 0L }
        }
    }
    LaunchedEffect(Unit) { Orbit.captured.collect { cb(it) } }
}

// =================================================================== add

/** Add a controller: press a button on it, or pick a ready-made setup. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddControllerScreen(a11yOn: Boolean, onSetUpA11y: () -> Unit, onOpen: (id: String, adding: Boolean) -> Unit, onClose: () -> Unit) {
    val ctx = LocalContext.current
    var opened by remember { mutableStateOf(false) }
    CaptureButtons { c ->
        if (opened || !c.down) return@CaptureButtons
        val existing = ControllerStore.load(ctx).firstOrNull { it.device == c.device }
        when {
            existing != null -> { opened = true; onOpen(existing.id, false) }
            c.device == Config.BACKTAP -> {}
            else -> {
                val cfg = Config.keys(java.util.UUID.randomUUID().toString(), c.deviceName, c.device, listOf(Input(c.input, c.label)))
                ControllerStore.put(ctx, cfg)
                Orbit.log("controller added: ${c.deviceName}")
                opened = true; onOpen(cfg.id, true)
            }
        }
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text("Add a controller", fontWeight = FontWeight.SemiBold) },
            navigationIcon = { IconButton(onClose) { Icon(painterResource(R.drawable.ic_x), "Cancel") } })
    }) { pad ->
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp,
            top = pad.calculateTopPadding() + 8.dp, bottom = pad.calculateBottomPadding() + 24.dp)) {
            if (!a11yOn) item { Banner("Orbit's accessibility service is off, so it can't hear buttons yet.", "Turn on", onSetUpA11y) }
            item { Listener("Press a button on it", "Any remote, selfie stick, keyboard, knob or game pad. Orbit finds the device; then you pick what each button does.") }
            item { Section("Or start from a ready-made setup", "Defaults you can change afterwards.") }
            item {
                Group {
                    PresetRow(R.drawable.ic_volume, "Earbuds & headphones", "CMF Buds Pro 2, AirPods, speakers, wired earphones") {
                        onOpen(Config.HEADPHONES, false)
                    }
                    Div()
                    PresetRow(R.drawable.ic_settings, "Phone volume keys", "Volume + and − drive Orbit while the screen is on") {
                        val cfg = ControllerStore.load(ctx).firstOrNull { it.device == Config.BUILTIN }
                            ?: Config.phoneVolumeKeys(java.util.UUID.randomUUID().toString()).also { ControllerStore.put(ctx, it) }
                        onOpen(cfg.id, false)
                    }
                    Div()
                    PresetRow(R.drawable.ic_bolt, "Back of the phone", "Tap the back of the phone (Pixel Quick Tap, Samsung RegiStar)") {
                        val cfg = ControllerStore.load(ctx).firstOrNull { it.device == Config.BACKTAP }
                            ?: Config.backTap(java.util.UUID.randomUUID().toString()).also { ControllerStore.put(ctx, it) }
                        BackTapActivity.setAvailable(ctx, true)
                        onOpen(cfg.id, false)
                    }
                }
            }
        }
    }
}

@Composable
private fun PresetRow(icon: Int, title: String, sub: String, onClick: () -> Unit) {
    ListItem(colors = clear, modifier = Modifier.clickable(onClick = onClick),
        leadingContent = { RowIcon(icon) },
        headlineContent = { Text(title, fontWeight = FontWeight.Medium) },
        supportingContent = { Text(sub, color = MaterialTheme.colorScheme.onSurfaceVariant) })
}

@Composable
private fun Listener(title: String, sub: String) {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val p by pulse.animateFloat(0f, 1f, infiniteRepeatable(tween(1600), RepeatMode.Restart), label = "p")
    val accent = MaterialTheme.colorScheme.primary
    Column(Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(116.dp), contentAlignment = Alignment.Center) {
            Canvas(Modifier.fillMaxSize()) {
                val r = size.minDimension / 2
                drawCircle(accent.copy(alpha = (1 - p) * 0.35f), r * (0.55f + 0.45f * p), style = Stroke(3.dp.toPx()))
                drawCircle(accent.copy(alpha = 0.14f), r * 0.5f)
                drawCircle(accent, r * 0.5f, style = Stroke(2.dp.toPx()))
            }
            Icon(painterResource(R.drawable.ic_keyboard), null, Modifier.size(30.dp), tint = accent)
        }
        Spacer(Modifier.height(12.dp))
        Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text(sub, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 460.dp))
    }
}

// =================================================================== edit

/**
 * One configuration: 1, its buttons (or, for earbuds, which preset); 2, what each of
 * Orbit's actions is set to. Every press while this screen is open is a test: the
 * action it would do lights up, and nothing else happens.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfigScreen(id: String, startAdding: Boolean, onClose: () -> Unit) {
    val ctx = LocalContext.current
    var cfg by remember { mutableStateOf(ControllerStore.get(ctx, id) ?: Config.headphones()) }
    var adding by remember { mutableStateOf(startAdding && !cfg.isHeadphones && cfg.device != Config.BACKTAP) }
    var customized by remember { mutableStateOf(!startAdding) }
    var lit by remember { mutableStateOf<String?>(null) }
    var litAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(Clock.now()) }
    var note by remember { mutableStateOf<String?>(null) }
    var typing by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<String?>(null) }      // the action whose button is being picked
    var pickingAction by remember { mutableStateOf(false) }
    var pickingApp by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var heard by remember { mutableStateOf<Pair<String, Long>?>(null) }   // last button pressed

    fun save(c: Config) { cfg = c; ControllerStore.put(ctx, c) }

    // a private hub on this setup: what would this press do?
    val preview = remember(cfg) {
        ConfigHub { ev ->
            lit = ev.action ?: when {
                ev.kind == Kind.ROTATE && ev.delta > 0 -> OrbitActions.FORWARD
                ev.kind == Kind.ROTATE -> OrbitActions.BACK
                else -> OrbitActions.SELECT
            }
            litAt = Clock.now()
        }.also { it.set(listOf(cfg.copy(enabled = true))) }
    }
    LaunchedEffect(preview) { while (true) { preview.tick(Clock.now()); now = Clock.now(); delay(20) } }

    CaptureButtons { c ->
        if (c.device != cfg.device) {
            if (c.down) note = "That was “${c.deviceName}”, not ${cfg.name}. Each device has its own setup."
            return@CaptureButtons
        }
        if (c.down) heard = c.input to Clock.now()
        val known = cfg.input(c.input) != null
        when {
            known && c.counted -> preview.pulse(cfg.device!!, c.input)
            known -> preview.onKey(cfg.device, c.input, c.down, Clock.now())
            adding && c.down && !c.counted -> {
                val ins = cfg.inputs + Input(c.input, c.label)
                save(if (customized) cfg.withInputs(ins) else cfg.copy(inputs = ins, bindings = Config.defaults(ins)))
                if (c.typing) typing = true
                note = null
            }
            c.down && cfg.isHeadphones -> note = "Your earbuds sent “${c.label}”, which this preset doesn't use. Try another one above."
            c.down -> note = "Tap “Add a button” first to add “${c.label}”."
        }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text(cfg.name, fontWeight = FontWeight.SemiBold) },
            navigationIcon = { IconButton(onClose) { Icon(painterResource(R.drawable.ic_arrow_left), "Back") } },
            actions = { if (!cfg.isHeadphones) TextButton({ confirmDelete = true }) { Text("Remove", color = MaterialTheme.colorScheme.error) } })
    }) { pad ->
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp,
            top = pad.calculateTopPadding(), bottom = pad.calculateBottomPadding() + 32.dp)) {

            // ---------------------------------------------------- 1: buttons
            if (cfg.isHeadphones) {
                item { Section("1  Your earbuds", "Pick what you have. Its buttons and gestures become Orbit's.") }
                item {
                    Group {
                        Presets.ALL.forEachIndexed { i, p ->
                            if (i > 0) Div()
                            ListItem(colors = clear,
                                modifier = Modifier.clickable { save(Config.headphones(p)); customized = false },
                                leadingContent = { RadioButton(cfg.preset == p.id, { save(Config.headphones(p)) }) },
                                headlineContent = { Text(p.name, fontWeight = FontWeight.Medium) },
                                supportingContent = { Text(p.about, color = MaterialTheme.colorScheme.onSurfaceVariant) })
                        }
                    }
                    if (cfg.preset == Presets.CMF.id) Hint("In Nothing X → Controls → Dial: press = Play/Pause, double = Next track, " +
                        "triple = Previous track, hold = Voice assistant. That's how the dial talks to Orbit.")
                }
            } else if (cfg.device == Config.BACKTAP) {
                item { Section("1  Set up the back tap", "Your phone senses the tap and opens “Orbit back tap”; Orbit does the rest.") }
                item {
                    Group {
                        ListItem(colors = clear,
                            headlineContent = { Text("Pixel", fontWeight = FontWeight.Medium) },
                            supportingContent = { Text("Settings → System → Gestures → Quick Tap → Open app → Orbit back tap.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant) })
                        Div()
                        ListItem(colors = clear,
                            headlineContent = { Text("Samsung", fontWeight = FontWeight.Medium) },
                            supportingContent = { Text("Good Lock → RegiStar → Back-Tap action. Double tap: Open app → Orbit back tap. " +
                                "Triple tap: Orbit back tap 2.", color = MaterialTheme.colorScheme.onSurfaceVariant) })
                        Div()
                        ListItem(colors = clear, modifier = Modifier.clickable { ctx.startActivity(Intent(Settings.ACTION_SETTINGS)) },
                            leadingContent = { RowIcon(R.drawable.ic_settings, MaterialTheme.colorScheme.primary) },
                            headlineContent = { Text("Open phone settings", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) })
                    }
                    Hint("Phones without back tap can't use this setup.")
                }
            } else {
                item { Section("1  Buttons", "The buttons of ${cfg.name} that Orbit uses. Its other buttons keep working as usual.") }
                item {
                    Group {
                        cfg.inputs.forEachIndexed { i, inp ->
                            if (i > 0) Div()
                            val on = heard?.first == inp.id && now - (heard?.second ?: 0) < 350
                            val bg by animateColorAsState(if (on) MaterialTheme.colorScheme.primary.copy(alpha = 0.14f) else Color.Transparent, label = "b")
                            ListItem(colors = ListItemDefaults.colors(containerColor = bg),
                                leadingContent = { Badge("ABCDEFGH"[i % 8].toString()) },
                                headlineContent = { Text(inp.label, fontWeight = FontWeight.Medium) },
                                trailingContent = {
                                    if (cfg.inputs.size > 1) IconButton({ save(cfg.withInputs(cfg.inputs - inp)) }) {
                                        Icon(painterResource(R.drawable.ic_x), "Remove ${inp.label}", Modifier.size(18.dp),
                                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                })
                        }
                        Div()
                        if (adding) {
                            val pulse = rememberInfiniteTransition(label = "a")
                            val a by pulse.animateFloat(0.35f, 1f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "a")
                            ListItem(colors = clear,
                                leadingContent = { Box(Modifier.size(30.dp).background(MaterialTheme.colorScheme.primary.copy(alpha = a * 0.3f), CircleShape)) },
                                headlineContent = { Text("Press another button on it…", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) },
                                trailingContent = { TextButton({ adding = false }) { Text("Done") } })
                        } else ListItem(colors = clear, modifier = Modifier.clickable { adding = true },
                            leadingContent = { RowIcon(R.drawable.ic_plus, MaterialTheme.colorScheme.primary) },
                            headlineContent = { Text("Add a button", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) })
                    }
                    if (typing) Hint("This is a typing keyboard: while Orbit is on, these keys drive Orbit instead of typing. " +
                        "Spare keys work best (F-keys, arrows, Page up / down).", warn = true)
                    if (cfg.device == Config.BUILTIN && cfg.inputs.any { it.id == "key:24" || it.id == "key:25" })
                        Hint("While the screen is on, the volume keys drive Orbit instead of the volume. " +
                            "To change the volume, pick the Volume tool, or switch this setup off.", warn = true)
                }
            }

            // ---------------------------------------------------- 2: controls
            item { Section("2  Controls", "What each button does. Tap a row to change it. Press your buttons to try: the action lights up.") }
            item {
                val extras = cfg.bindings.map { it.action }.filter { it !in OrbitActions.CORE }.distinct()
                Group {
                    (OrbitActions.CORE + extras).forEachIndexed { i, a ->
                        if (i > 0) Div()
                        val on = lit == a && now - litAt < 700
                        val bg by animateColorAsState(if (on) MaterialTheme.colorScheme.primary.copy(alpha = 0.18f) else Color.Transparent, label = "l")
                        val t = cfg.triggerFor(a)
                        ListItem(colors = ListItemDefaults.colors(containerColor = bg),
                            modifier = Modifier.clickable { editing = a },
                            headlineContent = { Text(actionName(ctx, a), fontWeight = FontWeight.Medium) },
                            supportingContent = { OrbitActions.hint(a).takeIf { it.isNotEmpty() }?.let {
                                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall) } },
                            trailingContent = {
                                Surface(color = if (t == null) MaterialTheme.colorScheme.surfaceContainerHighest else MaterialTheme.colorScheme.secondaryContainer,
                                    shape = RoundedCornerShape(50)) {
                                    Text(cfg.describe(t), Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                                        color = if (t == null) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSecondaryContainer,
                                        style = MaterialTheme.typography.labelLarge)
                                }
                            })
                    }
                    Div()
                    ListItem(colors = clear, modifier = Modifier.clickable { pickingAction = true },
                        leadingContent = { RowIcon(R.drawable.ic_plus, MaterialTheme.colorScheme.primary) },
                        headlineContent = { Text("Add an action", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) },
                        supportingContent = { Text("Previous tool, play / pause, home, screenshot, open an app…",
                            color = MaterialTheme.colorScheme.onSurfaceVariant) })
                }
                if (cfg.triggerFor(OrbitActions.OPEN) == null)
                    Hint("Nothing opens the wheel yet. Set “Open the wheel” to switch tools.", warn = true)
                note?.let { Hint(it, warn = true) }
            }
        }
    }

    editing?.let { a ->
        TriggerDialog(cfg, a, heard, onDismiss = { editing = null }) { t ->
            val (c, lost) = cfg.bind(a, t)
            save(c); customized = true; editing = null
            note = lost?.let { "“${actionName(ctx, it)}” was on that button, so it's not set now." }
        }
    }
    if (pickingAction) ActionPicker(onDismiss = { pickingAction = false }) { a ->
        pickingAction = false
        if (a == "launch:") pickingApp = true else editing = a
    }
    if (pickingApp) AppPicker(onDismiss = { pickingApp = false }) { pkg -> pickingApp = false; editing = "launch:$pkg" }
    if (confirmDelete) AlertDialog(onDismissRequest = { confirmDelete = false },
        title = { Text("Remove ${cfg.name}?") },
        text = { Text("Its buttons go back to what they did before Orbit.") },
        confirmButton = { TextButton({
            ControllerStore.remove(ctx, cfg.id)
            if (cfg.device == Config.BACKTAP) BackTapActivity.setAvailable(ctx, false)
            confirmDelete = false; onClose()
        }) { Text("Remove", color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton({ confirmDelete = false }) { Text("Cancel") } })
}

private fun actionName(ctx: android.content.Context, a: String): String {
    if (a.startsWith("launch:") && a.length > 7) {
        val pkg = a.removePrefix("launch:")
        val label = runCatching { ctx.packageManager.getApplicationLabel(ctx.packageManager.getApplicationInfo(pkg, 0)) }.getOrNull()
            ?: if (pkg == "com.anthropic.claude") "Claude" else pkg.substringAfterLast('.').replaceFirstChar { it.uppercase() }
        return "Open $label"
    }
    return OrbitActions.label(a)
}

/** Pick the button (and how it's pressed) for one action. Pressing a button picks it too. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TriggerDialog(cfg: Config, action: String, heard: Pair<String, Long>?, onDismiss: () -> Unit, onPick: (Trigger?) -> Unit) {
    val ctx = LocalContext.current
    val current = cfg.triggerFor(action)
    var input by remember { mutableStateOf(current?.input) }
    var press by remember { mutableStateOf(current?.press ?: Press.TAP) }
    val opened = remember { Clock.now() }
    LaunchedEffect(heard) { if (heard != null && heard.second > opened && cfg.input(heard.first) != null) input = heard.first }
    val sel = input?.let { cfg.input(it) }
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(actionName(ctx, action)) },
        text = {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                Text("Which button? Or just press it.", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(8.dp))
                cfg.inputs.forEach { i ->
                    Row(Modifier.fillMaxWidth().clickable { input = i.id }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(input == i.id, { input = i.id })
                        Text(i.label)
                    }
                }
                Row(Modifier.fillMaxWidth().clickable { input = null }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(input == null, { input = null })
                    Text("Not set", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (sel != null && !sel.counted) {
                    Spacer(Modifier.height(12.dp))
                    Text("How", style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Press.entries.forEach { p -> FilterChip(press == p, { press = p }, label = { Text(p.label) }) }
                    }
                    val other = cfg.actionFor(sel.id, press)?.takeIf { it != action }
                    if (other != null) Text("That's “${actionName(ctx, other)}” now. Choosing it moves it here.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.tertiary)
                    if (press == Press.DOUBLE || press == Press.TRIPLE)
                        Text("A single tap on this button then waits a moment to see if another tap follows.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else if (sel != null) {
                    val other = cfg.actionFor(sel.id, Press.TAP)?.takeIf { it != action }
                    if (other != null) Text("That's “${actionName(ctx, other)}” now. Choosing it moves it here.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.tertiary)
                }
            }
        },
        confirmButton = { Button({ onPick(sel?.let { Trigger(it.id, if (it.counted) Press.TAP else press) }) }) { Text("Done") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } })
}

@Composable
private fun ActionPicker(onDismiss: () -> Unit, onPick: (String) -> Unit) {
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text("Add an action") },
        text = {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                OrbitActions.EXTRA.forEach { a ->
                    Text(if (a == "launch:") "Open an app…" else OrbitActions.label(a),
                        Modifier.fillMaxWidth().clickable { onPick(a) }.padding(vertical = 12.dp),
                        style = MaterialTheme.typography.bodyLarge)
                }
            }
        },
        confirmButton = {}, dismissButton = { TextButton(onDismiss) { Text("Cancel") } })
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
            Text(text, Modifier.weight(1f), color = MaterialTheme.colorScheme.onTertiaryContainer, style = MaterialTheme.typography.bodyMedium)
            if (action != null) TextButton(onAction) { Text(action) }
        }
    }
}
