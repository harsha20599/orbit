package app.orbit.dial

import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.orbit.dial.core.Clock
import app.orbit.dial.core.Controls
import app.orbit.dial.core.ControlsHub
import app.orbit.dial.core.Kind
import app.orbit.dial.core.OrbitActions
import app.orbit.dial.core.Preset
import app.orbit.dial.core.Presets
import kotlinx.coroutines.delay

/** One thing to switch on, as the setup checklist and onboarding show it. */
class SetupItem(val title: String, val sub: String, val done: Boolean, val optional: Boolean = false, val action: () -> Unit)

private enum class Page { BUDS, PHONE, PERMISSIONS, DIAL, TRY }

/** What the person picked on the phone page. */
private enum class PhoneChoice(val title: String, val sub: String) {
    NONE("Not now", "Just the earbuds."),
    VOLUME("Volume keys", "Volume + / − move through the menu; hold to select or open it."),
    VOLUME_BACKTAP("Volume keys and back tap", "Keys to move; tap the back of the phone to select or open."),
    BACKTAP("Back tap", "Tap the back of the phone twice to select, three times to open."),
    OTHER("A remote, keyboard or game pad", "You'll pick its buttons next."),
}

/**
 * First run: what will you control Orbit with? Earbuds (which), and / or the phone's
 * own buttons; then only the permissions that choice needs; then the Nothing X step
 * for CMF buds; then a try-it page where every press lights up its function.
 * [onDone] true = continue in Setup controls (a remote or keyboard to add).
 */
@Composable
fun OnboardingScreen(tick: Int, steps: (Controls, () -> Unit) -> List<SetupItem>, onDone: (openControls: Boolean) -> Unit) {
    val ctx = LocalContext.current
    var page by remember { mutableStateOf(Page.BUDS) }
    var buds by remember { mutableStateOf<Preset?>(Presets.CMF) }
    var budsPicked by remember { mutableStateOf(false) }
    var phone by remember { mutableStateOf(PhoneChoice.NONE) }
    var disclosure by remember { mutableStateOf(false) }

    fun controls(): Controls {
        val phonePreset = when (phone) {
            PhoneChoice.VOLUME -> Presets.VOLUME_KEYS
            PhoneChoice.VOLUME_BACKTAP -> Presets.VOLUME_BACKTAP
            PhoneChoice.BACKTAP -> Presets.BACKTAP
            else -> null
        }
        return Presets.combine(*listOfNotNull(buds, phonePreset).toTypedArray())
    }
    fun next() {
        page = when (page) {
            Page.BUDS -> Page.PHONE
            Page.PHONE -> { ControllerStore.save(ctx, controls()); Page.PERMISSIONS }
            Page.PERMISSIONS -> if (buds == Presets.CMF) Page.DIAL else Page.TRY
            Page.DIAL -> Page.TRY
            Page.TRY -> { onDone(phone == PhoneChoice.OTHER); Page.TRY }
        }
    }
    fun back() {
        page = when (page) {
            Page.BUDS -> Page.BUDS
            Page.PHONE -> Page.BUDS
            Page.PERMISSIONS -> Page.PHONE
            Page.DIAL -> Page.PERMISSIONS
            Page.TRY -> if (buds == Presets.CMF) Page.DIAL else Page.PERMISSIONS
        }
    }
    BackHandler(page != Page.BUDS) { back() }

    val noButtons = buds == null && phone == PhoneChoice.NONE
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.surface) {
    Column(Modifier.fillMaxSize().systemBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            if (page != Page.BUDS) TextButton(::back) { Text("Back") } else Spacer(Modifier.size(1.dp))
            Spacer(Modifier.weight(1f))
            Dots(Page.entries.indexOf(page), Page.entries.size)
            Spacer(Modifier.weight(1f))
            TextButton({ onDone(false) }) { Text("Skip") }
        }
        AnimatedContent(page, Modifier.weight(1f), label = "page", transitionSpec = {
            (slideInHorizontally { it / 6 } + fadeIn()) togetherWith (slideOutHorizontally { -it / 6 } + fadeOut())
        }) { p ->
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally) {
                when (p) {
                    Page.BUDS -> {
                        item { Title("Do you have earbuds?", "Orbit can turn their buttons into a controller. Pick yours, or none.") }
                        Presets.BUDS.forEach { pr ->
                            item { Choice(pr.name, pr.about, budsPicked && buds == pr) { buds = pr; budsPicked = true } }
                        }
                        item { Choice("No earbuds", "Use the phone's own buttons instead.", budsPicked && buds == null) { buds = null; budsPicked = true } }
                    }
                    Page.PHONE -> {
                        item {
                            if (buds == null) Title("Which buttons on your phone?", "Pick how you'd like to open the menu, move and select.")
                            else Title("Also use your phone?", "Optional. The earbuds are enough; this adds the phone's buttons too.")
                        }
                        PhoneChoice.entries.filter { buds != null || it != PhoneChoice.NONE }.forEach { c ->
                            item { Choice(c.title, c.sub, phone == c) { phone = c } }
                        }
                        if (phone == PhoneChoice.VOLUME || phone == PhoneChoice.VOLUME_BACKTAP) item {
                            Hint("While the screen is on, the volume keys drive Orbit. To change the volume, use the Volume tool, or turn Orbit off.")
                        }
                    }
                    Page.PERMISSIONS -> {
                        item { Title("A few permissions", "Only what your setup needs. Each one opens the right settings page.") }
                        item {
                            @Suppress("UNUSED_VARIABLE") val t = tick                 // re-checked when you come back
                            Group {
                                steps(controls()) { disclosure = true }.forEachIndexed { i, st ->
                                    if (i > 0) Div()
                                    ListItem(colors = clear,
                                        leadingContent = { SetMark(st.done) },
                                        headlineContent = { Text(st.title + if (st.optional) " (optional)" else "", fontWeight = FontWeight.Medium) },
                                        supportingContent = { Text(st.sub, color = MaterialTheme.colorScheme.onSurfaceVariant) },
                                        trailingContent = { if (!st.done) FilledTonalButton(st.action) { Text("Allow") } })
                                }
                            }
                        }
                    }
                    Page.DIAL -> {
                        item { Title("Set the dial in Nothing X", "The dial talks to Orbit through its music controls. In the Nothing X app → Controls → Dial:") }
                        item {
                            Group {
                                listOf("Single press" to "Play / Pause", "Double press" to "Next track", "Triple press" to "Previous track",
                                    "Press and hold" to "Voice assistant").forEachIndexed { i, (g, a) ->
                                    if (i > 0) Div()
                                    ListItem(colors = clear, headlineContent = { Text(g) },
                                        trailingContent = { Text(a, color = SetGreen, fontWeight = FontWeight.Medium) })
                                }
                                Div()
                                ListItem(colors = clear, modifier = Modifier.clickable {
                                    val nx = ctx.packageManager.getLaunchIntentForPackage("com.nothing.smartcenter")
                                    ctx.startActivity((nx ?: Intent(Settings.ACTION_BLUETOOTH_SETTINGS)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                                }, leadingContent = { RowIcon(R.drawable.ic_settings, MaterialTheme.colorScheme.primary) },
                                    headlineContent = { Text("Open Nothing X", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Medium) })
                            }
                        }
                        item { PressCheck() }
                    }
                    Page.TRY -> {
                        item { Title("Try it", "Use your buttons: each function lights up when you press it. Nothing else happens yet.") }
                        item { TryControls(ControllerStore.load(ctx)) }
                    }
                }
            }
        }
        Surface(color = MaterialTheme.colorScheme.surface) {
            val a11y = page != Page.PERMISSIONS || steps(controls()) {}.first().done
            Button(::next, enabled = when (page) {
                Page.BUDS -> budsPicked
                Page.PHONE -> !noButtons
                Page.PERMISSIONS -> a11y
                else -> true
            }, modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp).height(52.dp)) {
                Text(when {
                    page == Page.TRY && phone == PhoneChoice.OTHER -> "Add my remote"
                    page == Page.TRY -> "Done"
                    page == Page.PERMISSIONS && !a11y -> "Allow the accessibility service first"
                    else -> "Continue"
                })
            }
        }
    }

    }

    if (disclosure) AlertDialog(
        onDismissRequest = { disclosure = false },
        title = { Text("Accessibility permission") },
        text = { Text(ctx.getString(R.string.a11y_description) + "\n\nNext: Accessibility settings → Orbit → turn on. " +
            "If the switch is greyed out: App info → ⋮ → Allow restricted settings.") },
        confirmButton = { Button({ disclosure = false; ctx.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }) { Text("I agree, continue") } },
        dismissButton = { TextButton({ disclosure = false }) { Text("Not now") } },
    )
}

@Composable
private fun Title(title: String, sub: String) {
    Column(Modifier.fillMaxWidth().widthIn(max = 560.dp).padding(top = 12.dp, bottom = 18.dp)) {
        Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Text(sub, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun Choice(title: String, sub: String, picked: Boolean, onClick: () -> Unit) {
    val border by animateColorAsState(if (picked) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant, label = "b")
    Surface(color = if (picked) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f) else MaterialTheme.colorScheme.surfaceContainer,
        shape = RoundedCornerShape(18.dp), border = BorderStroke(if (picked) 2.dp else 1.dp, border),
        modifier = Modifier.fillMaxWidth().widthIn(max = 560.dp).padding(bottom = 10.dp).clickable(onClick = onClick)) {
        Row(Modifier.padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Medium)
                Text(sub, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            SetMark(picked)
        }
    }
}

@Composable
private fun Dots(at: Int, n: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        repeat(n) { i ->
            Box(Modifier.size(if (i == at) 20.dp else 7.dp, 7.dp)
                .background(if (i <= at) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant, CircleShape))
        }
    }
}

/** Nothing X step: turns green the moment a dial press reaches Orbit. */
@Composable
private fun PressCheck() {
    val since = remember { Orbit.lastPress }
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { while (!seen) { delay(250); seen = Orbit.lastPress > since } }
    Spacer(Modifier.height(14.dp))
    Group {
        ListItem(colors = ListItemDefaults.colors(containerColor = if (seen) SetGreen.copy(alpha = 0.16f) else Color.Transparent),
            leadingContent = { SetMark(seen) },
            headlineContent = { Text(if (seen) "Presses reach Orbit" else "Now press the dial once", fontWeight = FontWeight.Medium) },
            supportingContent = { Text(if (seen) "All good." else "This turns green when Orbit hears it. Buds in the case work too.",
                color = MaterialTheme.colorScheme.onSurfaceVariant) })
    }
}

/** The four functions; each lights up when its trigger is pressed (captured, nothing acts). */
@Composable
private fun TryControls(c: Controls) {
    val ctx = LocalContext.current
    var lit by remember { mutableStateOf<String?>(null) }
    var litAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(Clock.now()) }
    var count by remember { mutableIntStateOf(0) }
    val hub = remember(c) {
        ControlsHub { ev ->
            lit = ev.action ?: when {
                ev.kind == Kind.ROTATE && ev.delta > 0 -> OrbitActions.FORWARD
                ev.kind == Kind.ROTATE -> OrbitActions.BACK
                else -> OrbitActions.SELECT
            }
            litAt = Clock.now(); count++
        }.also { it.set(c) }
    }
    LaunchedEffect(hub) { while (true) { hub.tick(Clock.now()); now = Clock.now(); delay(20) } }
    CaptureButtons { e -> if (e.counted) hub.pulse(e.input) else hub.onKey(e.device, e.input, e.down, Clock.now()) }
    Group {
        c.actions.forEachIndexed { i, a ->
            if (i > 0) Div()
            val on = lit == a && now - litAt < 700
            val bg by animateColorAsState(if (on) SetGreen.copy(alpha = 0.22f) else Color.Transparent, label = "t")
            ListItem(colors = ListItemDefaults.colors(containerColor = bg),
                headlineContent = { Text(actionName(ctx, a), fontWeight = FontWeight.Medium) },
                supportingContent = { TriggersText(c.triggers(a)) })
        }
    }
    Hint(if (count == 0) "Change any of these later in Controls → Set up controls." else "Nice. Change any of these later in Controls → Set up controls.")
}
