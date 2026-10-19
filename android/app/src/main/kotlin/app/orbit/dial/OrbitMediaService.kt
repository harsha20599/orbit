package app.orbit.dial

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioPlaybackConfiguration
import android.media.AudioTrack
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import androidx.core.content.ContextCompat
import app.orbit.dial.core.Clock
import app.orbit.dial.core.DialEvent
import app.orbit.dial.core.Kind
import app.orbit.dial.core.VolumeDial
import kotlin.math.roundToInt

/**
 * Foreground media service: the dial's input side (docs/research-android.md 1-2).
 *
 *  presses   the buds' AVRCP play/pause/next/previous go to the media session that
 *            last played audio, so we keep a session PLAYING and loop silence
 *            (no audio focus: real music keeps playing) and reclaim after others play.
 *  rotation  the Bluetooth stack calls setStreamVolume(STREAM_MUSIC) per click and
 *            sends VOLUME_CHANGED_ACTION; VolumeDial turns levels into clicks and
 *            restores the level (flags 0, no panel from us).
 */
class OrbitMediaService : Service() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var am: AudioManager
    private lateinit var session: MediaSession
    private var silence: AudioTrack? = null
    lateinit var dial: VolumeDial
        private set
    private val stream = AudioManager.STREAM_MUSIC
    private var ourSet: Pair<Int, Long>? = null           // (index, time) of our last setStreamVolume
    private var lastReassert = 0L

    /** 40 ms poll of the music volume: VOLUME_CHANGED_ACTION is deferred ~0.5 s by the
     *  broadcast queue (seen on Android 15), far too laggy for a dial. The broadcast
     *  stays as a backup; seeing the same level twice is a no-op in VolumeDial. */
    private var lastIdx = -1
    private val ticker = object : Runnable {
        override fun run() {
            onIndex(am.getStreamVolume(stream))
            dial.tick()
            main.postDelayed(this, 40)
        }
    }

    private val volumeRx = object : BroadcastReceiver() {
        override fun onReceive(c: Context, i: Intent) {
            if (i.getIntExtra("android.media.EXTRA_VOLUME_STREAM_TYPE", -1) != stream) return
            // Don't trust EXTRA_VOLUME_STREAM_VALUE: Nothing OS reports it x10 (100/16 for
            // 10/16, issue #1), which read as phantom clicks. Read the real index instead.
            onIndex(am.getStreamVolume(stream))
        }
    }

    private fun onIndex(idx: Int) {
        val max = am.getStreamMaxVolume(stream).coerceAtLeast(1)
        if (idx < 0 || idx > max) return                    // impossible reading: never a click
        if (idx == lastIdx) return
        lastIdx = idx
        val o = ourSet
        val ours = o != null && o.first == idx && Clock.now() - o.second < 700
        Orbit.log("vol $idx/$max${if (ours) " (ours)" else ""}")
        if (!ours && (Orbit.phoneKeyRecently() || !dialOutputActive())) {
            dial.onLevel(idx.toFloat() / max, ours = true)        // not the dial: just track it
            return
        }
        dial.onLevel(idx.toFloat() / max, ours)
    }

    override fun onCreate() {
        super.onCreate()
        am = getSystemService(AudioManager::class.java)
        startAsForeground()
        dial = VolumeDial(object : VolumeDial.Backend {
            override fun getLevel(): Float = am.getStreamVolume(stream).toFloat() / am.getStreamMaxVolume(stream).coerceAtLeast(1)
            override fun setLevel(level: Float) {
                val max = am.getStreamMaxVolume(stream)
                val idx = (level * max).roundToInt().coerceIn(0, max)
                ourSet = idx to Clock.now()
                am.setStreamVolume(stream, idx, 0)
            }
        }, { ev -> main.post { Orbit.emit(ev) } }, "android-volume",
            streamSteps = am.getStreamMaxVolume(stream).coerceAtLeast(1))
        dial.rebase()
        Orbit.media = this
        Orbit.rotation.replayInto(this)
        setupSession()
        startSilence()
        ContextCompat.registerReceiver(this, volumeRx, IntentFilter("android.media.VOLUME_CHANGED_ACTION"),
            ContextCompat.RECEIVER_NOT_EXPORTED)
        am.registerAudioPlaybackCallback(playbackCb, main)
        main.post(ticker)
        Orbit.log("media service up (volume ${am.getStreamVolume(stream)}/${am.getStreamMaxVolume(stream)})")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY

    override fun onDestroy() {
        main.removeCallbacks(ticker)
        dial.setDuck(null); dial.tick()
        runCatching { unregisterReceiver(volumeRx) }
        am.unregisterAudioPlaybackCallback(playbackCb)
        silence?.release()
        session.release()
        if (Orbit.media === this) Orbit.media = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?) = null

    // ------------------------------------------------------------ presses
    private fun setupSession() {
        session = MediaSession(this, "Orbit").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onMediaButtonEvent(i: Intent): Boolean {
                    @Suppress("DEPRECATION")
                    val ev = i.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT) ?: return false
                    if (ev.keyCode == KeyEvent.KEYCODE_HEADSETHOOK) { hookKey(ev); return true }
                    if (ev.action != KeyEvent.ACTION_DOWN || ev.repeatCount > 0) return true
                    val kind = when (ev.keyCode) {
                        KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE,
                        KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> Kind.CLICK
                        KeyEvent.KEYCODE_MEDIA_NEXT -> Kind.DOUBLE
                        KeyEvent.KEYCODE_MEDIA_PREVIOUS -> Kind.TRIPLE
                        else -> return false
                    }
                    press(kind, "key ${ev.keyCode}")
                    return true            // swallow; we never leave PLAYING
                }
                // Some phones (seen on Android 16) hand the buds' AVRCP presses to the
                // session as transport controls instead of media keys.
                override fun onPlay() = press(Kind.CLICK, "play")
                override fun onPause() = press(Kind.CLICK, "pause")
                override fun onStop() = press(Kind.CLICK, "stop")
                override fun onSkipToNext() = press(Kind.DOUBLE, "next")
                override fun onSkipToPrevious() = press(Kind.TRIPLE, "previous")
            }, main)
            setPlaybackState(PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or
                    PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_SKIP_TO_NEXT or
                    PlaybackState.ACTION_SKIP_TO_PREVIOUS)
                .setState(PlaybackState.STATE_PLAYING, 0, 1f).build())
            setMetadata(MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, "Orbit")
                .putString(MediaMetadata.METADATA_KEY_ARTIST, "Dial active").build())
            setMediaButtonReceiver(null)
            isActive = true
        }
    }

    // Wired earphone remotes: one button, HEADSETHOOK for every press; we count them.
    private val hook = app.orbit.dial.core.TapCounter { k -> press(k, "headset button") }
    private val hookTick = Runnable { hook.tick(Clock.now()); scheduleHook() }
    private fun scheduleHook() {
        main.removeCallbacks(hookTick)
        hook.nextWake()?.let { main.postDelayed(hookTick, (it - Clock.now()).coerceIn(0, 2000)) }
    }
    private fun hookKey(ev: KeyEvent) {
        if (Orbit.capturing()) { if (ev.action == KeyEvent.ACTION_DOWN && ev.repeatCount == 0) press(Kind.CLICK, "headset button"); return }
        if (ev.action == KeyEvent.ACTION_DOWN) hook.down(Clock.now()) else if (ev.action == KeyEvent.ACTION_UP) hook.up(Clock.now())
        scheduleHook()
    }

    private var lastPressAt = 0L
    private var lastPressKind: Kind? = null

    /** One press, however it arrived; a key and its transport-control twin count once. */
    private fun press(kind: Kind, how: String) {
        val now = Clock.now()
        if (kind == lastPressKind && now - lastPressAt < 150) return
        lastPressAt = now; lastPressKind = kind
        if (Orbit.capturing()) {
            val label = when (kind) { Kind.CLICK -> "Play / pause"; Kind.DOUBLE -> "Next track"; Kind.HOLD -> "Hold"; else -> "Previous track" }
            Orbit.capture(Orbit.Captured(-1, true, "media", "Headphones / speaker", label, media = true))
            return
        }
        Orbit.log("press: $how")
        Orbit.emit(DialEvent(kind, 0, "media-session"))
    }

    private fun startSilence() {
        val rate = 44100
        silence = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(rate)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(rate * 2).build().apply {
                write(ShortArray(rate), 0, rate)         // 1 s of zeros
                setLoopPoints(0, rate, -1)
                play()
            }
    }

    /** Become the media-button session again after another player started. */
    fun reassert() {
        val now = Clock.now()
        if (now - lastReassert < 1500) return          // two silent apps must not fight in a loop
        lastReassert = now
        silence?.let { it.pause(); it.flush(); it.reloadStaticData(); it.play() }
        session.isActive = true
        Orbit.log("reasserted media-button ownership")
    }

    private val playbackCb = object : AudioManager.AudioPlaybackCallback() {
        override fun onPlaybackConfigChanged(configs: MutableList<AudioPlaybackConfiguration>) {
            if (configs.size > 1) main.postDelayed({ reassert() }, 400)
        }
    }

    /** Only count volume changes as dial clicks while Bluetooth audio is the output. */
    private fun dialOutputActive(): Boolean {
        if (!Orbit.requireBluetooth(this)) return true
        return am.getDevices(AudioManager.GET_DEVICES_OUTPUTS).any {
            it.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP ||
                (Build.VERSION.SDK_INT >= 31 && it.type == AudioDeviceInfo.TYPE_BLE_HEADSET)
        }
    }

    // ------------------------------------------------------------ foreground
    private fun startAsForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("dial", getString(R.string.media_channel),
            NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE)
        val n = Notification.Builder(this, "dial")
            .setContentTitle("Orbit is on")
            .setContentText("Double-press the dial, or use your controller, to open the wheel")
            .setSmallIcon(R.drawable.ic_settings)
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Turn off",
                PendingIntent.getBroadcast(this, 1, Intent(this, OrbitToggleReceiver::class.java)
                    .setAction(OrbitToggleReceiver.OFF), PendingIntent.FLAG_IMMUTABLE)).build())
            .build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        else startForeground(1, n)
    }

    companion object {
        fun start(ctx: Context) {
            if (!Orbit.enabled(ctx)) return
            runCatching { ContextCompat.startForegroundService(ctx, Intent(ctx, OrbitMediaService::class.java)) }
                .onFailure { Orbit.log("media service start refused: ${it.message}") }
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, OrbitMediaService::class.java))
        }
    }
}
