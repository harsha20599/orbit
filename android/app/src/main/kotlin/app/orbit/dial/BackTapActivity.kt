package app.orbit.dial

import android.app.Activity
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle

/**
 * Back tap (Pixel Quick Tap, Samsung RegiStar): the phone "opens" one of two hidden
 * app entries; each is a button of the Back of the phone configuration. Press it, vanish.
 */
class BackTapActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val second = intent?.component?.className?.endsWith("BackTap2") == true
        if (Orbit.enabled(this)) Orbit.pulse(if (second) INPUT_2 else INPUT_1)
        finish()
        if (Build.VERSION.SDK_INT >= 34) overrideActivityTransition(OVERRIDE_TRANSITION_CLOSE, 0, 0)
        else @Suppress("DEPRECATION") overridePendingTransition(0, 0)
    }

    companion object {
        const val INPUT_1 = "backtap:1"
        const val INPUT_2 = "backtap:2"

        /** Show / hide the "Orbit back tap" entries the phone's back-tap setting can pick. */
        fun setAvailable(ctx: Context, on: Boolean) {
            val state = if (on) PackageManager.COMPONENT_ENABLED_STATE_ENABLED else PackageManager.COMPONENT_ENABLED_STATE_DISABLED
            for (n in listOf("BackTap1", "BackTap2"))
                ctx.packageManager.setComponentEnabledSetting(ComponentName(ctx, "app.orbit.dial.$n"), state, PackageManager.DONT_KILL_APP)
        }
    }
}
