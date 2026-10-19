package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class EngineTest {
    private var now = 1_000L
    private val log = mutableListOf<String>()
    private var passthrough: Boolean? = null
    private val duck = mutableListOf<Float?>()

    private val huds = mutableListOf<Hud>()

    @Before fun clock() { Clock.now = { now } }

    private val actions = object : Actions {
        var bright = 0.5f
        var scale = 1f
        override fun swipe(direction: Int, sideways: Boolean) { log += if (sideways) "side:$direction" else "swipe:$direction" }
        override fun zoom(scale: Float): Float { this.scale = scale; log += "zoom:$scale"; return scale }
        override fun zoomScale() = scale
        override fun brightness() = bright
        override fun setBrightness(v: Float) { bright = v; log += "bright:$v" }
        override fun torchAvailable() = true
        override fun torch(on: Boolean, level: Float) { log += "torch:$on" }
        override fun recentApps() = listOf(App("a.one", "One"), App("b.two", "Two"))
        override fun openApp(pkg: String) { log += "open:$pkg" }
        override fun global(action: String) { log += "global:$action" }
        override fun media(command: String) { log += "media:$command" }
        override fun launch(pkg: String) { log += "launch:$pkg" }
        override fun volume() = 0.5f
        override fun haptic() {}
        override fun shutter() { log += "shutter" }
        override fun nudge(direction: Int) { log += "nudge:$direction" }
        override fun tapPlayPause() { log += "tap" }
        override fun stepVolume(steps: Int) { log += "vol:$steps" }
    }
    private val ui = object : Ui {
        override fun wheelOpen(items: List<Tool>, index: Int) { log += "ui:open:$index" }
        override fun wheelMove(index: Int, direction: Int) { log += "ui:move:$index" }
        override fun wheelCommit(index: Int) { log += "ui:commit:$index" }
        override fun wheelCancel() { log += "ui:cancel" }
        override fun hud(h: Hud) { huds += h }
    }
    private val rot = object : RotationControl {
        override fun setPassthrough(on: Boolean) { passthrough = on }
        override fun setDuck(factor: Float?) { duck += factor }
        override fun level() = 0.5f
    }

    private fun engine() = Engine(actions, ui, rot, defaultTools())
    private fun Engine.ev(k: Kind, d: Int = 0) { now += 400; handle(DialEvent(k, d, "test", now)) }

    @Test fun startsOnVolumeWithPassthrough() {
        val e = engine()
        assertEquals("volume", e.tool.id); assertEquals(true, passthrough)
    }

    @Test fun doubleOpensRotateMovesPressSelects() {
        val e = engine()
        e.ev(Kind.DOUBLE)
        assertEquals(Engine.State.WHEEL, e.state); assertEquals(false, passthrough); assertEquals(0.5f, duck.last())
        e.ev(Kind.ROTATE, 2)
        e.ev(Kind.CLICK)
        assertEquals("scroll", e.tool.id); assertEquals(null, duck.last()); assertEquals(false, passthrough)
        e.ev(Kind.ROTATE, 1)
        assertTrue(log.any { it.startsWith("swipe:") })
    }

    @Test fun wheelMovesFurtherOnFastReportsWhenAccelIsOn() {
        val e = Engine(actions, ui, rot, defaultTools(), wheelAccel = 2)
        e.ev(Kind.DOUBLE)
        val n = e.tools.size
        val moved = mutableListOf<Int>()
        for ((d, gap) in listOf(1 to 1500L, 1 to 1500L, 1 to 350L, 1 to 350L, -1 to 350L, -1 to 1500L)) {
            val before = e.index
            now += gap - 400            // ev() adds 400
            e.ev(Kind.ROTATE, d)
            moved += ((e.index - before + n + 4) % n) - 4
        }
        assertEquals(listOf(1, 1, 2, 2, -1, -1), moved)
    }

    @Test fun wheelIsOneItemPerClickByDefault() {
        val e = engine()
        e.ev(Kind.DOUBLE)
        val start = e.index
        repeat(3) { now += 50; e.ev(Kind.ROTATE, 1) }     // 0.45 s apart
        assertEquals((start + 3) % e.tools.size, e.index)
    }

    @Test fun doubleClosesWithoutChange() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, 3); e.ev(Kind.DOUBLE)
        assertEquals(Engine.State.TOOL, e.state); assertEquals("volume", e.tool.id)
        assertTrue(log.none { it.startsWith("media") })
    }

    @Test fun wheelWrapsBackwards() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, -1)
        assertEquals(e.tools.size - 1, e.index)
    }

    @Test fun timeoutKeepsStickyNeverFiresOneShot() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, 1)
        e.tick(now + 6000)
        assertEquals("brightness", e.tool.id)
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, -2)          // claude (one-shot)
        e.tick(now + 6000)
        assertTrue(log.none { it.startsWith("launch") })
    }

    @Test fun oneShotRunsAndKeepsTool() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, -1); e.ev(Kind.CLICK)
        assertTrue("launch:com.anthropic.claude" in log); assertEquals("volume", e.tool.id)
    }

    @Test fun volumeToolGestures() {
        val e = engine()
        e.ev(Kind.CLICK); e.ev(Kind.TRIPLE); e.ev(Kind.HOLD)
        assertEquals(listOf("media:play_pause", "media:next", "launch:com.anthropic.claude"),
            log.filter { it.startsWith("media") || it.startsWith("launch") })
    }

    @Test fun tripleFlipsLastTool() {
        val e = engine()
        e.setTool("zoom")
        e.ev(Kind.TRIPLE)
        assertEquals("volume", e.tool.id)
    }

    @Test fun appsFirstClickHighlightsThePreviousAppAndPauseOpensIt() {
        val e = engine()
        e.setTool("apps")
        e.ev(Kind.ROTATE, 1)
        val strip = huds.last().strip!!
        assertEquals(0, strip.index); assertTrue(strip.commitInMs > 0)
        e.tick(now + 300)
        assertTrue(log.none { it.startsWith("open:") })           // still browsing
        e.tick(now + 2000)
        assertTrue("open:a.one" in log)
        assertTrue(huds.last().strip!!.opened)
    }

    @Test fun appsEachClickMovesOnePressOpensAtOnce() {
        val e = engine()
        e.setTool("apps")
        e.ev(Kind.ROTATE, 1); e.ev(Kind.ROTATE, 1)
        assertEquals(1, huds.last().strip!!.index)
        e.ev(Kind.CLICK)
        assertEquals(listOf("open:b.two"), log.filter { it.startsWith("open:") })
        assertTrue(huds.last().strip!!.opened)
        e.tick(now + 2000)
        assertEquals(1, log.count { it.startsWith("open:") })     // no second open
    }

    @Test fun teleprompterNudgesPerClickAndPressTapsPlayPause() {
        val e = engine()
        e.setTool("teleprompter")
        e.ev(Kind.ROTATE, 1); e.ev(Kind.ROTATE, -1)
        e.ev(Kind.CLICK)
        assertEquals(listOf("nudge:1", "nudge:-1", "tap"), log.filter { it.startsWith("nudge") || it == "tap" })
        assertTrue(log.none { it.startsWith("media:") })
    }

    @Test fun cameraPressIsTheShutterAndTurningDoesNothing() {
        val e = engine()
        e.setTool("camera")
        e.ev(Kind.ROTATE, 1)
        e.ev(Kind.CLICK); e.ev(Kind.CLICK)
        assertEquals(listOf("shutter", "shutter"), log.filter { it == "shutter" })
        assertTrue(log.none { it.startsWith("swipe") || it.startsWith("media:") })
    }

    @Test fun slidesIsOneSidewaysSwipePerClick() {
        val e = engine()
        e.setTool("slides")
        e.ev(Kind.ROTATE, 1); e.ev(Kind.ROTATE, 1); e.ev(Kind.ROTATE, -1)
        assertEquals(listOf("side:1", "side:1", "side:-1"), log.filter { it.startsWith("side:") })
    }

    @Test fun scrollIsOneSwipePerClick() {
        val e = engine()
        e.setTool("scroll")
        e.ev(Kind.ROTATE, 1); e.ev(Kind.ROTATE, 1); e.ev(Kind.ROTATE, -1)
        assertEquals(listOf("swipe:1", "swipe:1", "swipe:-1"), log.filter { it.startsWith("swipe:") })
    }

    @Test fun controllerTurnsStepTheVolumeButTheBudsDialDoesNot() {
        val e = engine()
        e.ev(Kind.ROTATE, 1)                                    // the buds already moved the volume
        now += 400; e.handle(DialEvent(Kind.ROTATE, -1, CONTROLLER + "Remote", now))
        assertEquals(listOf("vol:-1"), log)
    }

    @Test fun controllerMenuOpensWheelNextMovesSelectPicks() {
        val e = engine()
        val hub = ControllerHub { e.handle(it) }
        hub.set(listOf(Controller("r", "Remote", "d", Controller.layout(listOf(1 to "A", 2 to "B")))))
        hub.onKey("d", 2, true, now); now += ButtonRecognizer.HOLD_MS; hub.tick(now); hub.onKey("d", 2, false, now)
        assertEquals(Engine.State.WHEEL, e.state)
        hub.onKey("d", 1, true, now); now += 60; hub.onKey("d", 1, false, now)        // tap A: next item
        hub.onKey("d", 1, true, now); now += ButtonRecognizer.HOLD_MS; hub.tick(now)    // hold A: select
        assertEquals(Engine.State.TOOL, e.state)
        assertEquals(e.wheel[1].id, e.tool.id)
    }
}
