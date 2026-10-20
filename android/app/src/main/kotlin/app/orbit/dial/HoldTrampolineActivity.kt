package app.orbit.dial

import android.app.Activity
import android.os.Build
import android.os.Bundle
import app.orbit.dial.core.DialEvent
import app.orbit.dial.core.Kind

/**
 * Press-and-hold arrives as VOICE_COMMAND (the buds send HFP AT+BVRA=1 and the
 * Bluetooth stack starts this intent). Turn it into a HOLD and vanish.
 * We deliberately don't call BluetoothHeadset.startVoiceRecognition: that would
 * open a call-quality audio link and pause music; the stack just times out.
 */
class HoldTrampolineActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Orbit.pulse("media:hold")
        finish()
        if (Build.VERSION.SDK_INT >= 34) overrideActivityTransition(OVERRIDE_TRANSITION_CLOSE, 0, 0)
        else @Suppress("DEPRECATION") overridePendingTransition(0, 0)
    }
}
