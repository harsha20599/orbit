package app.orbit.dial

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.orbit.dial.core.DialEvent
import app.orbit.dial.core.Kind

/** Orbit's dark world as Material roles (same palette as the wheel overlay and desktop). */
val OrbitColors = darkColorScheme(
    primary = Color(0xFF8FA8FF), onPrimary = Color(0xFF0B1230),
    primaryContainer = Color(0xFF26325C), onPrimaryContainer = Color(0xFFDCE3FF),
    secondary = Color(0xFFB7C1DE), onSecondary = Color(0xFF1E2538),
    tertiary = Color(0xFFF2B46B), onTertiary = Color(0xFF3A2400),
    background = Color(0xFF101217), onBackground = Color(0xFFF2F4F8),
    surface = Color(0xFF101217), onSurface = Color(0xFFF2F4F8),
    surfaceVariant = Color(0xFF20242D), onSurfaceVariant = Color(0xFFA4AAB8),
    surfaceContainerLowest = Color(0xFF0B0D11), surfaceContainerLow = Color(0xFF151820),
    surfaceContainer = Color(0xFF1A1D25), surfaceContainerHigh = Color(0xFF20242D),
    surfaceContainerHighest = Color(0xFF272B35),
    outline = Color(0xFF4A5060), outlineVariant = Color(0xFF262A34),
)

/** The app: Orbit's switch, setup (collapsed when done), the wheel and gestures, help. */
class MainActivity : ComponentActivity() {
    private var refresh by mutableIntStateOf(0)
    /** null = home, "controls", or "onboarding" (again, from Help) */
    private var screen by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        applyDebugExtras(intent)
        setContent {
            MaterialTheme(colorScheme = OrbitColors) {
                when {
                    screen == "onboarding" || !Orbit.prefs(this).getBoolean("onboarded", false) ->
                        OnboardingScreen(refresh, ::setupSteps) { openControls ->
                            Orbit.prefs(this).edit().putBoolean("onboarded", true).apply()
                            screen = if (openControls) "controls" else null; refresh++
                        }
                    screen == "controls" -> ControlsScreen(a11yOn(), onSetUpA11y = {
                        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    }) { screen = null; refresh++ }
                    else -> Home(refresh)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); applyDebugExtras(intent) }
    override fun onResume() { super.onResume(); refresh++ ; if (a11yOn()) OrbitMediaService.start(this) }   // start() is a no-op when Orbit is off

    /** adb shell am start -n app.orbit.dial/.MainActivity --ez require_bt false  (emulator testing) */
    private fun applyDebugExtras(i: Intent) {
        if (i.hasExtra("require_bt")) Orbit.setRequireBluetooth(this, i.getBooleanExtra("require_bt", true))
        i.getStringExtra("emit")?.let { spec ->           // --es emit "rotate:1" | "double" | "click" ...
            val (k, d) = (spec.split(":") + "0").let { it[0] to it[1].toIntOrNull() }
            runCatching { Orbit.emit(DialEvent(Kind.valueOf(k.uppercase()), d ?: 0, "intent")) }
        }
    }

    // ---- status checks
    fun a11yOn(): Boolean {
        val want = ComponentName(this, OrbitAccessibilityService::class.java).flattenToString()
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        return TextUtils.SimpleStringSplitter(':').apply { setString(enabled) }.any { it.equals(want, true) }
    }
    fun listenerOn(): Boolean = (Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: "")
        .contains(ComponentName(this, OrbitNotificationListener::class.java).flattenToString())
    fun holdIsOurs(): Boolean = packageManager.resolveActivity(Intent(Intent.ACTION_VOICE_COMMAND),
        PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.packageName == packageName
    fun notifOn(): Boolean = Build.VERSION.SDK_INT < 33 ||
        checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    fun writeOn(): Boolean = Settings.System.canWrite(this)

    private fun copyLog() {
        val cm = getSystemService(android.content.ClipboardManager::class.java)
        cm.setPrimaryClip(android.content.ClipData.newPlainText("Orbit log",
            "Orbit ${BuildConfig.VERSION_NAME} · Android ${Build.VERSION.RELEASE} · ${Build.MANUFACTURER} ${Build.MODEL}\n" +
                Orbit.logLines.value.joinToString("\n")))
        android.widget.Toast.makeText(this, "Log copied: paste it into your GitHub issue", android.widget.Toast.LENGTH_LONG).show()
    }

    /** Home = Orbit's switch, setup (collapsed once done) and the whole Customize content. */
    @Composable
    private fun Home(@Suppress("UNUSED_PARAMETER") tick: Int) {
        var disclosure by remember { mutableStateOf(false) }
        var gestures by remember { mutableStateOf(false) }
        CustomizeScreen(
            title = "Orbit",
            top = {
                item { OnOffCard() }
                item { SetupCard { disclosure = true } }
                controlsSection(refresh, onOpen = { screen = "controls" })
            },
            bottom = {
                item { Section("Help", "Something not working? These usually sort it out.") }
                item {
                    Group {
                        HelpRow(R.drawable.ic_settings, "Wheel won't open?", "Check that your earbuds' presses reach Orbit") { gestures = true }
                        androidx.compose.material3.HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        HelpRow(R.drawable.ic_rotate_ccw, "Set up again", "Pick your earbuds and buttons from the start") { screen = "onboarding" }
                        androidx.compose.material3.HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        HelpRow(R.drawable.ic_edit, "Report a problem", "Copies the log, then opens GitHub Issues") {
                            copyLog()
                            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/harsha20599/orbit/issues/new/choose")))
                        }
                    }
                    Text("Orbit ${BuildConfig.VERSION_NAME} · free · by Yemcube (@yem.cube)", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.fillMaxWidth().padding(top = 18.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                }
            },
        )
        if (gestures) GesturesDialog { gestures = false }
        if (disclosure) AlertDialog(
            onDismissRequest = { disclosure = false },
            title = { Text("Accessibility permission") },
            text = { Text(getString(R.string.a11y_description) + "\n\nNext: Accessibility settings → Orbit → turn on. " +
                "If the switch is greyed out: App info → ⋮ → Allow restricted settings.") },
            confirmButton = { Button({ disclosure = false; startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }) { Text("I agree, continue") } },
            dismissButton = { TextButton({ disclosure = false }) { Text("Not now") } },
        )
    }

    /** What these controls need: earbud presses need notification access (play / pause your
     *  music); a hold needs Orbit as the voice-command app; the rest everyone needs. */
    fun setupSteps(c: app.orbit.dial.core.Controls, onA11y: () -> Unit): List<SetupItem> = buildList {
        add(SetupItem("Accessibility service", "Draws the wheel and performs actions.", a11yOn(), action = onA11y))
        add(SetupItem("Notifications", "Shows that Orbit is on, with a Turn off button.", notifOn()) {
            if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        })
        if (c.uses("media:")) add(SetupItem("Notification access", "Lets a press still play / pause your music.", listenerOn()) {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })
        if (c.uses("media:hold")) add(SetupItem("Press-and-hold", "Needed for the hold: tap, then pick Orbit and Always.", holdIsOurs()) {
            startActivity(Intent(Intent.ACTION_VOICE_COMMAND).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        })
        add(SetupItem("Modify system settings", "For the Brightness tool.", writeOn(), optional = true) {
            startActivity(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:$packageName")))
        })
    }

    /** The master switch, as the first thing on the page. */
    @Composable
    private fun OnOffCard() {
        var on by remember { mutableStateOf(Orbit.enabled(this)) }
        val bg by androidx.compose.animation.animateColorAsState(
            if (on) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainer, label = "onBg")
        androidx.compose.material3.Surface(color = bg, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
            Row(Modifier.padding(horizontal = 20.dp, vertical = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(if (on) "Orbit is on" else "Orbit is off", style = MaterialTheme.typography.titleLarge,
                        color = if (on) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface)
                    Text(if (on) "Press your Open menu button to open the wheel." else "Every button works as normal until you turn Orbit on.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (on) MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f) else MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(on, { on = it; Orbit.setEnabled(this@MainActivity, it) })
            }
        }
    }

    /** Setup: every step while something's missing; one quiet line once it's all done. */
    @Composable
    private fun SetupCard(onA11y: () -> Unit) {
        @Suppress("UNUSED_VARIABLE") val tick = refresh     // re-check every step on resume
        val steps = setupSteps(ControllerStore.load(this), onA11y)
        val missing = steps.count { !it.done && !it.optional }
        var open by remember(missing) { mutableStateOf(missing > 0) }
        Column(Modifier.padding(top = 12.dp)) {
            Group {
                androidx.compose.material3.ListItem(
                    colors = androidx.compose.material3.ListItemDefaults.colors(containerColor = Color.Transparent),
                    modifier = Modifier.fillMaxWidth().clickable { open = !open },
                    leadingContent = { StatusDot(missing == 0) },
                    headlineContent = { Text(if (missing == 0) "All set" else "Finish setting up",
                        fontWeight = FontWeight.Medium) },
                    supportingContent = { Text(if (missing == 0) "Permissions granted" else "$missing step${if (missing == 1) "" else "s"} left",
                        color = MaterialTheme.colorScheme.onSurfaceVariant) },
                    trailingContent = { Icon(painterResource(if (open) R.drawable.ic_chevron_up else R.drawable.ic_chevron_down), null,
                        Modifier.size(20.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant) },
                )
                androidx.compose.animation.AnimatedVisibility(open) {
                    Column {
                        steps.forEach { st ->
                            androidx.compose.material3.HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                            androidx.compose.material3.ListItem(
                                colors = androidx.compose.material3.ListItemDefaults.colors(containerColor = Color.Transparent),
                                leadingContent = { StatusDot(st.done, small = true) },
                                headlineContent = { Text(st.title) },
                                supportingContent = { Text(st.sub, color = MaterialTheme.colorScheme.onSurfaceVariant) },
                                trailingContent = { if (!st.done) androidx.compose.material3.FilledTonalButton(st.action) { Text("Set up") } },
                            )
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun StatusDot(done: Boolean, small: Boolean = false) {
        val size = if (small) 22.dp else 28.dp
        Box(Modifier.size(size).background(if (done) Color(0xFF3DDC97) else MaterialTheme.colorScheme.surfaceContainerHighest, CircleShape),
            contentAlignment = Alignment.Center) {
            if (done) Text("✓", color = Color(0xFF0B1A12), fontWeight = FontWeight.Bold, fontSize = if (small) 12.sp else 14.sp)
        }
    }

    @Composable
    private fun HelpRow(icon: Int, title: String, sub: String, onClick: () -> Unit) {
        androidx.compose.material3.ListItem(
            colors = androidx.compose.material3.ListItemDefaults.colors(containerColor = Color.Transparent),
            modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
            leadingContent = { Icon(painterResource(icon), null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant) },
            headlineContent = { Text(title, fontWeight = FontWeight.Medium) },
            supportingContent = { Text(sub, color = MaterialTheme.colorScheme.onSurfaceVariant) },
        )
    }

    /** "Wheel won't open?": the press test plus the Nothing X gesture fix. */
    @Composable
    private fun GesturesDialog(onDismiss: () -> Unit) {
        var seen by remember { mutableStateOf(false) }
        val since = remember { Orbit.lastPress }
        androidx.compose.runtime.LaunchedEffect(Unit) {
            while (!seen) { kotlinx.coroutines.delay(300); seen = Orbit.lastPress > since }
        }
        AlertDialog(
            onDismissRequest = onDismiss,
            title = { Text(if (seen) "Presses reach Orbit ✓" else "Press your earbuds once") },
            text = { Text(if (seen) "Orbit hears your earbuds. Check which press opens the wheel in Set up controls." else
                "If nothing changes here when you press, your earbuds aren't sending music controls to this phone. " +
                "Make sure they're connected, and if they have their own app, set their gestures to play / pause, next and previous track.\n\n" +
                "CMF Buds Pro 2: in the Nothing X app (on Nothing phones: Settings → Connected devices → CMF Buds Pro 2) → Controls → Dial, set " +
                "single press Play / Pause, double Next track, triple Previous track, hold Voice assistant.\n\n" +
                "Keys, remotes and back taps: Set up controls shows each press as you make it.") },
            confirmButton = {
                if (seen) Button(onDismiss) { Text("Done") }
                else Button({
                    onDismiss()
                    val nx = packageManager.getLaunchIntentForPackage("com.nothing.smartcenter")
                    startActivity(nx ?: Intent(Settings.ACTION_BLUETOOTH_SETTINGS))
                }) { Text("Open buds settings") }
            },
            dismissButton = { if (!seen) TextButton(onDismiss) { Text("Close") } },
        )
    }

}
