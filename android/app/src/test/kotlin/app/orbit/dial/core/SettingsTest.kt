package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Same rules as tests/test_settings.py. */
class SettingsTest {
    private val all = defaultTools()
    private val d = OrbitSettings.defaults(all)

    @Test fun defaultsPutEveryToolButTheOptionalOnesOnTheWheel() {
        assertEquals(all.map { it.id } - setOf("zoom", "claude", "teleprompter"), d.wheel(all).map { it.id })
        assertEquals(setOf(Kind.DOUBLE), d.openWith())
    }

    @Test fun disabledToolsLeaveTheWheelInTheChosenOrder() {
        val s = d.copy(order = listOf("scroll", "volume", "apps") + d.order.filter { it !in listOf("scroll", "volume", "apps") },
                       enabled = setOf("volume", "scroll", "apps"))
        assertEquals(listOf("scroll", "volume", "apps"), s.wheel(all).map { it.id })
    }

    @Test fun unknownIdsAreDroppedAndNewToolsAppear() {
        val s = OrbitSettings(listOf("gone", "volume"), setOf("gone", "volume"), "gone", d.gestures).normalized(all)
        assertEquals("volume", s.order.first())
        assertTrue(s.order.containsAll(all.map { it.id }))
        assertEquals("volume", s.defaultTool)
    }

    @Test fun gesturesDriveTheEngineAndHiddenToolsStayUsable() {
        val s = d.copy(enabled = setOf("volume"), defaultTool = "scroll",
                       gestures = d.gestures + (Kind.DOUBLE to "media:next") + (Kind.TRIPLE to OrbitSettings.OPEN_WHEEL) +
                           (Kind.CLICK to "tool:zoom"))
        val log = mutableListOf<String>()
        val e = s.buildEngine(object : Actions by FakeActions(log) {}, NoUi, null, all)
        assertEquals(listOf("volume"), e.wheel.map { it.id })
        assertEquals("scroll", e.tool.id)                                // start tool need not be on the wheel
        e.handle(DialEvent(Kind.DOUBLE)); assertTrue("media:next" in log)
        e.handle(DialEvent(Kind.CLICK)); assertEquals("zoom", e.tool.id)
        e.handle(DialEvent(Kind.TRIPLE)); assertEquals(Engine.State.WHEEL, e.state)
    }

    @Test fun thereIsAlwaysAWayIntoTheWheel() {
        val s = d.copy(gestures = d.gestures + (Kind.DOUBLE to "none"))
        assertEquals(setOf(Kind.TRIPLE), s.openWith())
    }

    private object NoUi : Ui {
        override fun wheelOpen(items: List<Tool>, index: Int) {}
        override fun wheelMove(index: Int, direction: Int) {}
        override fun wheelCommit(index: Int) {}
        override fun wheelCancel() {}
        override fun hud(h: Hud) {}
    }

    private class FakeActions(val log: MutableList<String>) : Actions {
        override fun swipe(direction: Int, sideways: Boolean) {}
        override fun zoom(scale: Float) = scale
        override fun zoomScale() = 1f
        override fun brightness() = 0.5f
        override fun setBrightness(v: Float) {}
        override fun torchAvailable() = false
        override fun torch(on: Boolean, level: Float) {}
        override fun recentApps() = emptyList<App>()
        override fun openApp(pkg: String) {}
        override fun global(action: String) { log += "global:$action" }
        override fun media(command: String) { log += "media:$command" }
        override fun launch(pkg: String) { log += "launch:$pkg" }
        override fun volume() = 0.5f
        override fun haptic() {}
        override fun shutter(video: Boolean) = true
        override fun nudge(direction: Int) {}
        override fun tapPlayPause() {}
    }
}
