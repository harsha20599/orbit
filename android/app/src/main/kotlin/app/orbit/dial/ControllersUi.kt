package app.orbit.dial

import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.BackHandler
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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
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
import androidx.lifecycle.repeatOnLifecycle
import app.orbit.dial.core.Clock
import app.orbit.dial.core.Controls
import app.orbit.dial.core.ControlsHub
import app.orbit.dial.core.Inputs
import app.orbit.dial.core.Kind
import app.orbit.dial.core.OrbitActions
import app.orbit.dial.core.Press
import app.orbit.dial.core.PressRecognizer
import app.orbit.dial.core.Presets
import app.orbit.dial.core.Trigger
import kotlinx.coroutines.delay

internal val clear @Composable get() = ListItemDefaults.colors(containerColor = Color.Transparent)
internal val SetGreen = Color(0xFF3DDC97)

@Composable internal fun Div() = HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

@Composable
internal fun RowIcon(res: Int, tint: Color = MaterialTheme.colorScheme.onSurfaceVariant) =
    Icon(painterResource(res), null, Modifier.size(20.dp), tint = tint)

internal fun actionName(ctx: android.content.Context, a: String): String {
    if (a.startsWith("launch:") && a.length > 7) {
        val pkg = a.removePrefix("launch:")
        val label = runCatching { ctx.packageManager.getApplicationLabel(ctx.packageManager.getApplicationInfo(pkg, 0)) }.getOrNull()
            ?: if (pkg == "com.anthropic.claude") "Claude" else pkg.substringAfterLast('.').replaceFirstChar { it.uppercase() }
        return "Open $label"
    }
    return OrbitActions.label(a)
}

/** Green check when set, an empty ring when not (the wireframe's circles). */
@Composable
internal fun SetMark(set: Boolean) {
    val ring = MaterialTheme.colorScheme.outline
    Box(Modifier.size(26.dp).background(if (set) SetGreen else Color.Transparent, CircleShape), contentAlignment = Alignment.Center) {
        if (set) Text("✓", color = Color(0xFF0B1A12), fontWeight = FontWeight.Bold, fontSize = 14.sp)
        else Canvas(Modifier.fillMaxSize()) { drawCircle(ring, size.minDimension / 2 - 2.dp.toPx(), style = Stroke(2.dp.toPx())) }
    }
}

@Composable
internal fun TriggersText(ts: List<Trigger>) {
    if (ts.isEmpty()) Text("Not set", color = MaterialTheme.colorScheme.onSurfaceVariant)
    else Text(ts.joinToString("  or  ") { it.label() }, color = SetGreen, maxLines = 2, overflow = TextOverflow.Ellipsis)
}

// =================================================================== home section

/** Home: the functions and what drives them; tap to set up. */
fun LazyListScope.controlsSection(tick: Int, onOpen: () -> Unit) {
    item { Section("Controls", "What opens the menu, moves and selects: any mix of earbuds, keys, remotes and back taps.") }
    item {
        val ctx = LocalContext.current
        val c = remember(tick) { ControllerStore.load(ctx) }
        Group {
            c.actions.forEachIndexed { i, a ->
                if (i > 0) Div()
                ListItem(colors = clear, modifier = Modifier.clickable(onClick = onOpen),
                    leadingContent = { SetMark(c.triggers(a).isNotEmpty()) },
                    headlineContent = { Text(actionName(ctx, a), fontWeight = FontWeight.Medium) },
                    supportingContent = { TriggersText(c.triggers(a)) })
            }
            Div()
            ListItem(colors = clear, modifier = Modifier.clickable(onClick = onOpen),
                leadingContent = { RowIcon(R.drawable.ic_edit, MaterialTheme.colorScheme.primary) },
                headlineContent = { Text("Set up controls", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) },
                supportingContent = { Text(Presets.byId(c.preset)?.let { "Preset: ${it.name}" } ?: "Custom",
                    color = MaterialTheme.colorScheme.onSurfaceVariant) })
        }
    }
}

// =================================================================== capture

/** Every press while a controls screen is in front: captured, nothing acts. */
@Composable
internal fun CaptureButtons(onPress: (Orbit.Captured) -> Unit) {
    val cb by rememberUpdatedState(onPress)
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val obs = androidx.lifecycle.LifecycleEventObserver { _, e ->
            if (e == androidx.lifecycle.Lifecycle.Event.ON_STOP) Orbit.captureUntil = 0L
        }
        lifecycle.addObserver(obs)
        onDispose { lifecycle.removeObserver(obs); Orbit.captureUntil = 0L }
    }
    LaunchedEffect(lifecycle) {
        // STARTED, not RESUMED: a back tap opens Orbit's invisible entry on top for a
        // moment, which pauses this screen; leaving the app stops it
        lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) {
            try { while (true) { Orbit.captureUntil = Clock.now() + 1500; delay(500) } } finally { Orbit.captureUntil = 0L }
        }
    }
    LaunchedEffect(Unit) { Orbit.captured.collect { cb(it) } }
}

/** Captured press -> the trigger it would be (keys of a typing keyboard: only that keyboard). */
private fun Orbit.Captured.trigger(p: Press) =
    Trigger(input, if (counted) Press.TAP else p, if (typing) device else null, if (typing) deviceName else null)

// =================================================================== setup controls

/** Wireframes 1 and 3: the functions with their triggers, Load presets, Save. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ControlsScreen(a11yOn: Boolean, onSetUpA11y: () -> Unit, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val saved = remember { ControllerStore.load(ctx) }
    var draft by remember { mutableStateOf(saved) }
    var editing by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf<String?>(null) }
    var presets by remember { mutableStateOf(false) }
    var addFn by remember { mutableStateOf(false) }
    var discard by remember { mutableStateOf(false) }
    var confirmPreset by remember { mutableStateOf<app.orbit.dial.core.Preset?>(null) }
    var confirmReset by remember { mutableStateOf(false) }
    var lit by remember { mutableStateOf<String?>(null) }
    var litAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(Clock.now()) }
    val changed = draft != saved

    fun close() { if (changed) discard = true else onClose() }

    val fn = editing
    if (fn != null) {
        FunctionScreen(fn, draft) { c, lost ->
            draft = c; editing = null
            note = lost?.let { "That trigger was on “${actionName(ctx, it)}”; it's moved to “${actionName(ctx, fn)}”." }
        }
        return
    }

    // live test on the draft: press anything, its function lights up
    val preview = remember(draft) {
        ControlsHub { ev ->
            lit = ev.action ?: when {
                ev.kind == Kind.ROTATE && ev.delta > 0 -> OrbitActions.FORWARD
                ev.kind == Kind.ROTATE -> OrbitActions.BACK
                else -> OrbitActions.SELECT
            }
            litAt = Clock.now()
        }.also { it.set(draft) }
    }
    LaunchedEffect(preview) { while (true) { preview.tick(Clock.now()); now = Clock.now(); delay(20) } }
    var heard by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    CaptureButtons { c ->
        if (c.down) heard = Trigger(c.input).label().substringBefore(" · ") to (preview.has(c.device, c.input) || draft.uses(c.input))
        if (c.counted) preview.pulse(c.input) else preview.onKey(c.device, c.input, c.down, Clock.now())
    }
    BackHandler { close() }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Setup controls", fontWeight = FontWeight.SemiBold) },
                navigationIcon = { IconButton(::close) { Icon(painterResource(R.drawable.ic_arrow_left), "Back") } })
        },
        bottomBar = {
            Surface(color = MaterialTheme.colorScheme.surface) {
                Button(onClick = { ControllerStore.save(ctx, draft); Orbit.log("controls saved"); onClose() },
                    enabled = changed, modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp).height(52.dp)) {
                    Text(if (changed) "Save" else "Saved", fontSize = 16.sp)
                }
            }
        },
    ) { pad ->
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp,
            top = pad.calculateTopPadding(), bottom = pad.calculateBottomPadding() + 16.dp)) {
            if (!a11yOn) item { Banner("Orbit's accessibility service is off, so it can't hear keys yet.", "Turn on", onSetUpA11y) }
            item {
                Row(Modifier.fillMaxWidth().padding(start = 4.dp, top = 20.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Functions", style = MaterialTheme.typography.titleLarge)
                        Text("Press any of your buttons to test: its function lights up.", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    TextButton({ if (draft.bindings.isNotEmpty()) confirmReset = true }) { Text("Reset") }
                    Box {
                        OutlinedButton({ presets = true }) {
                            Text("Load presets"); Spacer(Modifier.size(6.dp))
                            Icon(painterResource(R.drawable.ic_chevron_down), null, Modifier.size(16.dp))
                        }
                        DropdownMenu(presets, { presets = false }) {
                            Presets.ALL.forEach { p ->
                                DropdownMenuItem(
                                    text = {
                                        Column(Modifier.padding(vertical = 4.dp)) {
                                            Text(p.name, fontWeight = FontWeight.Medium)
                                            Text(p.about, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        }
                                    },
                                    onClick = {
                                        presets = false
                                        if (draft.bindings.isNotEmpty() && draft != p.controls) confirmPreset = p
                                        else { draft = p.controls; note = "Loaded “${p.name}”. Change anything, then Save." }
                                    })
                            }
                        }
                    }
                }
            }
            item {
                Group {
                    draft.actions.forEachIndexed { i, a ->
                        if (i > 0) Div()
                        val on = lit == a && now - litAt < 700
                        val bg by animateColorAsState(if (on) MaterialTheme.colorScheme.primary.copy(alpha = 0.18f) else Color.Transparent, label = "l")
                        ListItem(colors = ListItemDefaults.colors(containerColor = bg),
                            modifier = Modifier.clickable { editing = a },
                            leadingContent = { SetMark(draft.triggers(a).isNotEmpty()) },
                            headlineContent = { Text(actionName(ctx, a), fontWeight = FontWeight.Medium) },
                            supportingContent = { TriggersText(draft.triggers(a)) },
                            trailingContent = { Icon(painterResource(R.drawable.ic_arrow_left), null, Modifier.size(20.dp).rotate(180f),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant) })
                    }
                    Div()
                    ListItem(colors = clear, modifier = Modifier.clickable { addFn = true },
                        leadingContent = { RowIcon(R.drawable.ic_plus, MaterialTheme.colorScheme.primary) },
                        headlineContent = { Text("Add a function", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) },
                        supportingContent = { Text("Previous tool, custom command",
                            color = MaterialTheme.colorScheme.onSurfaceVariant) })
                }
                HeardLine(heard)
                if (draft.triggers(OrbitActions.OPEN).isEmpty()) Hint("Nothing opens the menu yet, so you can't switch tools.", warn = true)
                note?.let { Hint(it) }
                if (draft.uses("key:24") || draft.uses("key:25"))
                    Hint("While the screen is on, these volume keys drive Orbit instead of the volume. " +
                        "To change the volume, pick the Volume tool, or turn Orbit off.", warn = true)
            }
        }
    }

    if (addFn) AlertDialog(onDismissRequest = { addFn = false },
        title = { Text("Add a function") },
        text = {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                OrbitActions.EXTRA.filter { it !in draft.actions }.forEach { a ->
                    val desktop = a in OrbitActions.DESKTOP_ONLY
                    ListItem(colors = clear,
                        modifier = Modifier.fillMaxWidth().clickable(enabled = !desktop) { addFn = false; editing = a },
                        headlineContent = { Text(OrbitActions.label(a), fontWeight = FontWeight.Medium,
                            color = if (desktop) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface) },
                        supportingContent = { Text(if (desktop) "Coming on Windows and Mac" else OrbitActions.hint(a),
                            color = MaterialTheme.colorScheme.onSurfaceVariant) })
                }
                if (OrbitActions.EXTRA.none { it !in draft.actions }) Text("All added.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }, confirmButton = {}, dismissButton = { TextButton({ addFn = false }) { Text("Cancel") } })
    confirmPreset?.let { p ->
        AlertDialog(onDismissRequest = { confirmPreset = null },
            title = { Text("Load “${p.name}”?") }, text = { Text("It replaces the controls you've set.") },
            confirmButton = { TextButton({ draft = p.controls; confirmPreset = null
                note = "Loaded “${p.name}”. Change anything, then Save." }) { Text("Replace") } },
            dismissButton = { TextButton({ confirmPreset = null }) { Text("Cancel") } })
    }
    if (confirmReset) AlertDialog(onDismissRequest = { confirmReset = false },
        title = { Text("Reset controls?") }, text = { Text("Removes every trigger from every function. Then Save.") },
        confirmButton = { TextButton({ draft = Controls(emptyList()); confirmReset = false
            note = "Everything cleared. Pick triggers, or load a preset, then Save." }) {
            Text("Remove all", color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton({ confirmReset = false }) { Text("Cancel") } })
    if (discard) AlertDialog(onDismissRequest = { discard = false },
        title = { Text("Discard changes?") }, text = { Text("Your changes to the controls aren't saved.") },
        confirmButton = { TextButton({ discard = false; onClose() }) { Text("Discard", color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton({ discard = false }) { Text("Keep editing") } })
}

/** Every press Orbit hears, used or not: "is it even reaching Orbit?" at a glance. */
@Composable
internal fun HeardLine(heard: Pair<String, Boolean>?) {
    val (text, warn) = when {
        heard == null -> "Nothing heard yet. Press a button on your earbuds, phone or remote." to false
        heard.second -> "Last heard: ${heard.first}" to false
        else -> "Last heard: ${heard.first}. Not used here: add it to a function, or load a preset that uses it." to true
    }
    Hint(text, warn = warn)
}

// =================================================================== one function

private enum class Category(val title: String, val about: String, val icon: Int) {
    BACK("Tapping on back", "Double or triple tap the back of the phone", R.drawable.ic_bolt),
    VOLUME("Volume keys", "The phone's, a selfie stick's or a remote's", R.drawable.ic_volume),
    MEDIA("Media buttons", "Earbuds, AirPods, the CMF dial, speakers, wired earphones", R.drawable.ic_play),
    MOTION("Motion gestures", "Chop or twist the phone", R.drawable.ic_scroll),
    MOUSE("Mouse keys", "The side buttons of a mouse", R.drawable.ic_app),
    KEYBOARD("Keyboard shortcut", "Any key or combination on a keyboard, knob or game pad", R.drawable.ic_keyboard),
}

private val CATALOG: Map<Category, List<String>> = mapOf(
    Category.BACK to listOf("backtap:1", "backtap:2"),
    Category.VOLUME to listOf("key:24", "key:25", "key:164"),
    Category.MEDIA to listOf("media:play", "media:next", "media:prev", "media:hold", "vol:up", "vol:down", "media:hook"),
    Category.MOTION to listOf("motion:chop", "motion:twist"),
    Category.MOUSE to listOf("mouse:back", "mouse:forward"),
    Category.KEYBOARD to listOf("key:62", "key:66", "key:19", "key:20", "key:21", "key:22", "key:92", "key:93") + (131..142).map { "key:$it" },
)

/** Wireframe 2: one function. Choose (search or browse) or Record. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FunctionScreen(action: String, controls: Controls, onDone: (Controls, String?) -> Unit) {
    val ctx = LocalContext.current
    var c by remember { mutableStateOf(controls) }
    var tab by remember { mutableIntStateOf(0) }
    var query by remember { mutableStateOf("") }
    var cat by remember { mutableStateOf<Category?>(null) }
    var asking by remember { mutableStateOf<String?>(null) }      // the key whose press is being picked

    fun add(t: Trigger) { val (n, lost) = c.add(action, t); onDone(n, lost) }
    fun back() { if (cat != null) cat = null else onDone(c, null) }
    BackHandler { back() }

    Scaffold(topBar = {
        TopAppBar(title = { Text(cat?.title ?: actionName(ctx, action), fontWeight = FontWeight.SemiBold) },
            navigationIcon = { IconButton(::back) { Icon(painterResource(R.drawable.ic_arrow_left), "Back") } })
    }) { pad ->
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp,
            top = pad.calculateTopPadding() + 4.dp, bottom = pad.calculateBottomPadding() + 24.dp)) {
            val mine = c.triggers(action)
            if (cat == null && mine.isNotEmpty()) item {
                Text("Set to", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
                Group {
                    mine.forEachIndexed { i, t ->
                        if (i > 0) Div()
                        ListItem(colors = clear, leadingContent = { SetMark(true) },
                            headlineContent = { Text(t.label(), fontWeight = FontWeight.Medium) },
                            trailingContent = { IconButton({ c = c.remove(action, t) }) {
                                Icon(painterResource(R.drawable.ic_x), "Remove", Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant) } })
                    }
                }
                Hint(if (mine.size == 1) "Add another trigger below to use either one." else "Any of these works.")
                Spacer(Modifier.height(14.dp))
            }
            if (cat == null) item {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf("Choose", "Record").forEachIndexed { i, l ->
                        SegmentedButton(tab == i, { tab = i }, SegmentedButtonDefaults.itemShape(i, 2)) { Text(l) }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }

            val cc = cat
            when {
                tab == 1 && cc == null -> item { Recorder(onUse = ::add) }
                cc != null -> {
                    if (cc == Category.BACK) item { BackTapSetup() }
                    if (cc == Category.MOTION) item { MotionTest() }
                    if (cc == Category.KEYBOARD) item {
                        Hint("Common keys below. For any other key or a combination like Ctrl+Space, use Record.")
                        Spacer(Modifier.height(8.dp))
                    }
                    item { InputList(CATALOG.getValue(cc), c, action) { asking = it } }
                    if (cc == Category.BACK) item { Spacer(Modifier.height(18.dp)); BackTapHelp() }
                }
                else -> {
                    item {
                        OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth(), singleLine = true,
                            placeholder = { Text("Search a trigger") },
                            leadingIcon = { Icon(painterResource(R.drawable.ic_search), null, Modifier.size(20.dp)) },
                            shape = RoundedCornerShape(16.dp))
                        Spacer(Modifier.height(12.dp))
                    }
                    if (query.isBlank()) item {
                        Group {
                            Category.entries.forEachIndexed { i, k ->
                                if (i > 0) Div()
                                ListItem(colors = clear, modifier = Modifier.clickable { cat = k },
                                    leadingContent = { RowIcon(k.icon) },
                                    headlineContent = { Text(k.title, fontWeight = FontWeight.Medium) },
                                    supportingContent = { Text(k.about, color = MaterialTheme.colorScheme.onSurfaceVariant) },
                                    trailingContent = { Icon(painterResource(R.drawable.ic_arrow_left), null, Modifier.size(18.dp).rotate(180f),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant) })
                            }
                        }
                    } else item {
                        val q = query.trim().lowercase()
                        val hits = CATALOG.entries.flatMap { (k, ins) -> ins.filter { Inputs.label(it).lowercase().contains(q) ||
                            k.title.lowercase().contains(q) || k.about.lowercase().contains(q) } }.distinct()
                        if (hits.isEmpty()) Hint("Nothing found. Try Record: press the button and Orbit finds it.")
                        else InputList(hits, c, action) { asking = it }
                    }
                }
            }
        }
    }

    asking?.let { input ->
        if (Inputs.counted(input)) { asking = null; add(Trigger(input)) }
        else PressDialog(input, c, action, onDismiss = { asking = null }) { p -> asking = null; add(Trigger(input, p)) }
    }
}

@Composable
private fun InputList(inputs: List<String>, c: Controls, action: String, onPick: (String) -> Unit) {
    val ctx = LocalContext.current
    Group {
        inputs.forEachIndexed { i, input ->
            if (i > 0) Div()
            val users = c.bindings.filter { it.trigger.input == input && it.trigger.device == null && it.action != action }.map {
                if (Inputs.counted(input)) actionName(ctx, it.action) else "${it.trigger.press.label.lowercase()}: ${actionName(ctx, it.action)}"
            }
            ListItem(colors = clear, modifier = Modifier.clickable { onPick(input) },
                headlineContent = { Text(Inputs.label(input), fontWeight = FontWeight.Medium) },
                supportingContent = { if (users.isNotEmpty()) Text("Now: " + users.joinToString(", "), color = MaterialTheme.colorScheme.onSurfaceVariant) })
        }
    }
}

/** Tap / double tap / triple tap / hold for a key. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PressDialog(input: String, c: Controls, action: String, onDismiss: () -> Unit, onPick: (Press) -> Unit) {
    val ctx = LocalContext.current
    var p by remember { mutableStateOf(Press.TAP) }
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(Inputs.label(input)) },
        text = {
            Column {
                Text("How do you press it?", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(10.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Press.entries.forEach { x -> FilterChip(p == x, { p = x }, label = { Text(x.label) }) }
                }
                c.actionFor(Trigger(input, p))?.takeIf { it != action }?.let {
                    Spacer(Modifier.height(8.dp))
                    Text("That's “${actionName(ctx, it)}” now; it moves here.", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.tertiary)
                }
                if (p == Press.DOUBLE || p == Press.TRIPLE) {
                    Spacer(Modifier.height(8.dp))
                    Text("A single tap of this key then waits a moment to see if another follows.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        },
        confirmButton = { Button({ onPick(p) }) { Text("Use it") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } })
}

/** Record: press it the way you'll use it (tap, double tap, triple tap or hold). */
@Composable
private fun Recorder(onUse: (Trigger) -> Unit) {
    var got by remember { mutableStateOf<Trigger?>(null) }
    var input by remember { mutableStateOf<Orbit.Captured?>(null) }
    val rec = remember { mutableStateOf<PressRecognizer?>(null) }
    LaunchedEffect(Unit) { while (true) { rec.value?.tick(Clock.now()); delay(15) } }
    CaptureButtons { c ->
        if (got != null) return@CaptureButtons
        val first = input
        when {
            c.counted -> if (c.down) got = c.trigger(Press.TAP)
            first == null || first.input != c.input -> if (c.down) {
                input = c
                rec.value = PressRecognizer(Press.entries.toSet(), false) { p -> got = c.trigger(p) }.also { it.down(Clock.now()) }
            }
            c.down -> rec.value?.down(Clock.now())
            else -> rec.value?.up(Clock.now())
        }
    }
    val pulse = rememberInfiniteTransition(label = "pulse")
    val k by pulse.animateFloat(0f, 1f, infiniteRepeatable(tween(1600), RepeatMode.Restart), label = "p")
    val accent = MaterialTheme.colorScheme.primary
    val g = got
    Column(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(120.dp), contentAlignment = Alignment.Center) {
            Canvas(Modifier.fillMaxSize()) {
                val r = size.minDimension / 2
                if (g == null) drawCircle(accent.copy(alpha = (1 - k) * 0.35f), r * (0.55f + 0.45f * k), style = Stroke(3.dp.toPx()))
                drawCircle((if (g != null) SetGreen else accent).copy(alpha = 0.16f), r * 0.5f)
                drawCircle(if (g != null) SetGreen else accent, r * 0.5f, style = Stroke(2.dp.toPx()))
            }
            if (g != null) Text("✓", color = SetGreen, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            else Icon(painterResource(R.drawable.ic_keyboard), null, Modifier.size(32.dp), tint = accent)
        }
        Spacer(Modifier.height(12.dp))
        Text(g?.label() ?: if (input != null) "Keep going…" else "Press it now",
            style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text(if (g != null) "Use this, or try again." else
            "The way you'll use it: tap, double tap, triple tap or hold. Earbuds, volume keys, remotes, keyboards and game pads all work.",
            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 440.dp))
        if (g != null) {
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                TextButton({ got = null; input = null; rec.value = null }) { Text("Try again") }
                Button({ onUse(g) }) { Text("Use this") }
            }
        }
    }
}

/** Orbit's own detection: on / off, sensitivity, and a live test. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BackTapSetup() {
    val ctx = LocalContext.current
    var detect by remember { mutableStateOf(Orbit.backTapDetect(ctx)) }
    var sens by remember { mutableStateOf(Orbit.backTapSensitivity(ctx)) }
    var heard by remember { mutableStateOf<String?>(null) }
    var heardAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(Clock.now()) }
    DisposableEffect(Unit) {
        BackTapActivity.setAvailable(ctx, true)          // so the phone's own setting can list it now
        Orbit.motionTesting = true
        onDispose { Orbit.motionTesting = false }
    }
    LaunchedEffect(Unit) { while (true) { now = Clock.now(); delay(100) } }
    CaptureButtons { c -> if (c.input.startsWith("backtap:")) { heard = c.input; heardAt = Clock.now() } }

    Group {
        ListItem(colors = clear,
            headlineContent = { Text("Orbit detects back taps", fontWeight = FontWeight.Medium) },
            supportingContent = { Text("Works on any phone, using its motion sensor while the screen is on.",
                color = MaterialTheme.colorScheme.onSurfaceVariant) },
            trailingContent = { androidx.compose.material3.Switch(detect, {
                detect = it; Orbit.prefs(ctx).edit().putBoolean("backtap_detect", it).apply(); Orbit.motionTesting = true
            }) })
        if (detect) {
            Div()
            Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                Text("Sensitivity", style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.height(6.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("low" to "Firm taps", "medium" to "Normal", "high" to "Light taps").forEach { (k, l) ->
                        FilterChip(sens == k, {
                            sens = k; Orbit.prefs(ctx).edit().putString("backtap_sens", k).apply(); Orbit.motionTesting = true
                        }, label = { Text(l) })
                    }
                }
            }
        }
        Div()
        val fresh = heard != null && now - heardAt < 2500
        ListItem(colors = ListItemDefaults.colors(containerColor = if (fresh) SetGreen.copy(alpha = 0.16f) else Color.Transparent),
            leadingContent = { SetMark(fresh) },
            headlineContent = { Text(if (fresh) "Heard: ${Inputs.label(heard!!).lowercase()}" else "Try it: tap the back twice, quickly",
                fontWeight = FontWeight.Medium) },
            supportingContent = { Text(if (fresh) "Pick it below to use it." else
                "Tap with a fingertip near the camera. Three taps is a triple tap.",
                color = MaterialTheme.colorScheme.onSurfaceVariant) })
    }
    Spacer(Modifier.height(12.dp))
}

/** Chop / twist: a live test, so people find the right force before choosing. */
@Composable
private fun MotionTest() {
    var heard by remember { mutableStateOf<String?>(null) }
    var heardAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(Clock.now()) }
    DisposableEffect(Unit) { Orbit.motionTesting = true; onDispose { Orbit.motionTesting = false } }
    LaunchedEffect(Unit) { while (true) { now = Clock.now(); delay(100) } }
    CaptureButtons { c -> if (c.input.startsWith("motion:")) { heard = c.input; heardAt = Clock.now() } }
    val fresh = heard != null && now - heardAt < 2500
    Group {
        ListItem(colors = ListItemDefaults.colors(containerColor = if (fresh) SetGreen.copy(alpha = 0.16f) else Color.Transparent),
            leadingContent = { SetMark(fresh) },
            headlineContent = { Text(if (fresh) "Heard: ${Inputs.label(heard!!).lowercase()}" else "Try it", fontWeight = FontWeight.Medium) },
            supportingContent = { Text(if (fresh) "Pick it below to use it." else
                "Chop: hold the phone firmly and chop down twice, like a knife. Twist: turn your wrist back and forth twice, fast.",
                color = MaterialTheme.colorScheme.onSurfaceVariant) })
    }
    Hint("Works while the screen is on.")
    Spacer(Modifier.height(12.dp))
}

@Composable
private fun BackTapHelp() {
    val ctx = LocalContext.current
    Text("Or use your phone's own back tap", style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(start = 4.dp, bottom = 8.dp))
    Group {
        ListItem(colors = clear, headlineContent = { Text("Pixel", fontWeight = FontWeight.Medium) },
            supportingContent = { Text("Settings → System → Gestures → Quick Tap → Open app → Orbit back tap.",
                color = MaterialTheme.colorScheme.onSurfaceVariant) })
        Div()
        ListItem(colors = clear, headlineContent = { Text("Samsung", fontWeight = FontWeight.Medium) },
            supportingContent = { Text("Good Lock → RegiStar → Back-Tap action → Open app → Orbit back tap (double tap) " +
                "and Orbit back tap 2 (triple tap).", color = MaterialTheme.colorScheme.onSurfaceVariant) })
        Div()
        ListItem(colors = clear, modifier = Modifier.clickable { ctx.startActivity(Intent(Settings.ACTION_SETTINGS)) },
            leadingContent = { RowIcon(R.drawable.ic_settings, MaterialTheme.colorScheme.primary) },
            headlineContent = { Text("Open phone settings", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) })
    }
    Hint("Usually more reliable on those phones. If you use it, you can switch Orbit's detection off above.")
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
