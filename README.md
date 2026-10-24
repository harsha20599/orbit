# Orbit

**Turn the buttons you already have into a controller for your computer and phone.**

Orbit puts a wheel of tools on your screen. Open it, move to a tool, select it, and from then
on your buttons drive that tool: scroll pages and reels, flip slides, scrub a video timeline,
change volume or brightness, switch apps, undo / redo, take a photo or record a video, and more.

It works with almost anything that has a button: earbuds and headphones, a keyboard's volume
knob, media keys, any key or shortcut, mouse side buttons, Ctrl + scroll, trackpad gestures,
and on Android the phone's own volume keys, Bluetooth remotes and selfie sticks, and even a
tap on the back of the phone.

**Windows · macOS · Android.** Free. [Download](#download) · [Telegram help group](https://t.me/orbit_issues)

---

## Contents

- [How it works](#how-it-works)
- [Download](#download)
- [First setup](#first-setup)
- [Using Orbit](#using-orbit)
- [Setting up your controls](#setting-up-your-controls)
- [Guides for each kind of control](#guides-for-each-kind-of-control)
- [The tools](#the-tools)
- [Settings](#settings)
- [Turning Orbit off](#turning-orbit-off)
- [Troubleshooting](#troubleshooting)
- [Privacy and permissions](#privacy-and-permissions)
- [Help and feedback](#help-and-feedback)
- [License](#license)
- [For developers](#for-developers)

## How it works

Orbit has four functions. You choose which button does each one.

| Function | What it does |
|---|---|
| **Open menu** | Opens the wheel of tools (and closes it again). |
| **Previous / Next** | In the wheel: move to the previous / next tool. In a tool: drive it (scroll up / down, volume down / up, previous / next slide…). |
| **Single press / Select** | In the wheel: pick the highlighted tool. In a tool: its press (play / pause, take a photo, open the app…). |

So with a pair of earbuds, for example: double press opens the wheel, volume up / down moves
through it, a single press picks a tool, and from then on volume up / down scrolls, flips slides
or changes brightness, depending on the tool. Open the wheel again to switch tools.

## Download

Get the latest version from **[Releases](https://github.com/harsha20599/orbit/releases/latest)**
(or [yemcube.tech/orbit](https://yemcube.tech/orbit)).

| | File | Install |
|---|---|---|
| **Windows 10 / 11** | `Orbit-Windows-Setup.exe` | Run it. If Windows says "Windows protected your PC", click **More info → Run anyway** (the installer isn't code-signed yet). When Orbit starts it asks for admin: say yes if you want press-and-hold triggers over admin apps; everything else works without. Orbit lives in the system tray (click **^** by the clock). |
| **macOS 13+** (Apple Silicon) | `Orbit-macOS.zip` | Unzip and drag **Orbit.app** to Applications. The first time, **right-click → Open** (it isn't notarized yet). Allow **Accessibility** when asked (System Settings → Privacy & Security → Accessibility). Orbit lives in the menu bar. **After updating**, switch Orbit off and on again in that Accessibility list. |
| **Android 8+** | `Orbit-Android.apk` | Open it on the phone and allow installing from your browser. Open Orbit and follow the setup. If the Accessibility switch is greyed out: App info → ⋮ → **Allow restricted settings**. |

**Updating:** install the new version over the old one. Your settings are kept.

## First setup

The first time you open Orbit it asks **"What do you want to control Orbit with?"** Pick what you
have, and Orbit sets up the four functions for it:

| Choice | What you get |
|---|---|
| **CMF Buds Pro 2** | The case dial: turn to move, press to select, double press to open. ([one extra step](#cmf-buds-pro-2-the-case-dial)) |
| **Other earbuds or headphones** | Press = select, double press = open, triple press = previous; on Android, swiping the volume moves. |
| **A volume knob or media keys** (desktop) | Volume keys move, play / pause selects. |
| **Mouse side buttons** (desktop) | Back / forward move; holding them selects or opens. |
| **Trackpad gestures** (desktop) | Windows: 3-finger swipes and taps. macOS: rotate and pinch. |
| **A key + scroll** (desktop) | Hold Ctrl and scroll. |
| **A macro pad or spare keys** (desktop) | F13 to F16. |
| **The phone's volume keys** (Android) | Tap to move; hold to select or open. Optionally with back tap. |
| **Back tap** (Android) | Tap the back of the phone twice to select, three times to open. |
| **Explore and set it up myself** | Start from nothing and pick every trigger yourself. |

Android then asks only for the permissions your choice needs, shows a **Try it** screen where each
function lights up as you press, and you're done.

You can run this setup again any time: **Settings → Controls → Run setup again**.

## Using Orbit

1. **Open menu**: the wheel appears in the middle of your screen.
2. **Previous / Next**: move the highlight to a tool. The wheel shows its name.
3. **Select**: the wheel closes and that tool is now active. A small pop-up shows what it's doing.
4. Your **Previous / Next** and **Select** now drive the tool until you open the menu again.

If you leave the wheel open for 5 seconds, it keeps the highlighted tool. While the wheel is open,
your music drops to half volume so the clicks stay quiet.

## Setting up your controls

Open **Settings → Controls** (Android: **Set up controls**). You'll see the four functions in this
order: **Open menu, Single press / Select, Previous, Next**, each with its triggers in green.

- **Change a function:** click it. Then either
  - **Choose**: browse by category (earbuds, keys, mouse, trackpad…) or search, or
  - **Record**: press the button the way you'll use it (a tap, double tap, triple tap or hold;
    a shortcut like Ctrl+Space; a scroll or trackpad gesture). Then **Save and close**.
- **More than one trigger per function** is fine: "Earbuds: double press *or* Volume + hold".
- **Load presets:** start from a preset (Orbit asks before replacing what you have).
- **Reset** (the circular-arrow icon): removes every trigger, after asking.
- **Add a function:** *Previous tool* (jump back to the tool you used before) or, on Windows and
  macOS, a *Custom command* (press any keyboard shortcut).
- **Test as you go:** press any of your buttons on this screen; its function lights up and
  "Last heard" shows what Orbit received. Nothing else happens while Settings is open.

**How keys behave:** Orbit only takes over a key while one of your triggers uses it; every other
key works as usual. If a key is set only for *hold* (or only for *double tap*), a quick single press
still does its normal job, so Volume + still turns the volume up.

## Guides for each kind of control

### Earbuds and headphones

Works with AirPods, OnePlus, Galaxy, Pixel Buds, Sony, Bluetooth speakers with buttons and wired
earphones with a button. Orbit receives the presses your earbuds send as music controls:
**press** (play / pause), **double press** (next track) and **triple press** (previous track).

- The earbuds must be connected to the device Orbit runs on. While another app is playing music,
  the phone or computer may send the earbuds' presses to that app instead of Orbit.
- Some earbuds let you choose what their gestures do (in their own app). Set them to play / pause,
  next and previous track, or Orbit won't hear them.
- Earbuds' *hold* gestures usually open the phone's voice assistant and don't reach apps.
- **Android:** swiping the earbuds' volume can move through the wheel too.

### CMF Buds Pro 2: the case dial

Orbit reads the dial through the buds' music controls, so set the dial to send them. In the
**Nothing X** app (on a Nothing phone: Settings → Connected devices → CMF Buds Pro 2) →
**Controls → Dial**:

| Dial gesture | Set it to |
|---|---|
| Single press | Play / Pause |
| Double press | Next track |
| Triple press | Previous track |
| Press and hold | Voice assistant |

Then turning the dial moves and drives tools, a press selects, a double press opens the wheel.
Good to know: the buds send at most about three dial steps a second, so Orbit makes fast turns go
further; each click makes a small tone in the buds (their firmware); on Windows the buds must be
this PC's audio output (the tray menu says **Buds connected**).

### Keyboard knob, media keys and any key

- **Volume knob or media keys:** choose the preset *A volume knob or media keys*, or Record the knob
  turning each way for Previous and Next. Bluetooth keyboards' knobs work too.
- **Any key or shortcut:** Record it (F13–F24 and macro-pad keys are ideal because nothing else uses
  them). Shortcuts like Ctrl+Shift+Space work as one trigger.
- **Mouse side buttons:** the *Mouse side buttons* preset, or Record back / forward / middle.
- **Ctrl + scroll:** the *A key + scroll* preset, or Record holding a key while you scroll. Plain
  scrolling is never taken.

### Trackpad gestures

- **Windows:** 3- and 4-finger swipes (left / right / up / down) and taps on a Precision Touchpad.
  Windows also runs its own action for these gestures; to use them only for Orbit, set them to
  **Nothing** in Settings → Bluetooth & devices → Touchpad → Three- / Four-finger gestures.
- **macOS:** rotate (two fingers), pinch in / out, swipes and the two-finger double tap.

### Phone buttons, remotes and selfie sticks (Android)

The phone's volume keys, Bluetooth remotes, selfie-stick buttons, keyboards and game pads all work.
Record a button in **Set up controls**; a button recorded on one remote only counts on that remote.
Buttons are read while the screen is on.

### Back tap, chop and twist (Android)

- **Back tap:** double or triple tap the back of the phone near the camera. Set it up with the
  *Tapping on back* option; a test screen shows each tap so you can pick the right sensitivity.
  On Pixel and Samsung phones you can also use the phone's own Quick Tap / back tap and point it at
  Orbit.
- **Chop:** a quick chopping shake. **Twist:** turn the wrist back and forth twice.
- These use the motion sensor only while the screen is on and only if one of your triggers uses them.

## The tools

What's on the wheel and in what order is up to you (Settings).

| Tool | Previous / Next | Select |
|---|---|---|
| **Volume** | volume down / up | play / pause |
| **Brightness** | dimmer / brighter (laptop screen; external monitors on Windows via [Twinkle Tray](https://twinkletray.com)) | |
| **Scroll** | scroll up / down (fast turns go further; on Android one flick per step: next reel, Short or story) | |
| **Slides** | previous / next slide | black out the screen (desktop) |
| **Timeline** (desktop) | glide through DaVinci Resolve, Premiere, Final Cut | play / pause |
| **Windows / Apps** | step through your open apps or windows | |
| **Undo / Redo** (desktop) | undo / redo | |
| **Tabs** (desktop) | previous / next tab | close tab (macOS) |
| **Desktops / Spaces** (desktop) | previous / next virtual desktop | Mission Control (macOS) |
| **Dictate / Claude** (desktop) | | Windows: voice typing · macOS: opens Claude |
| **Zoom** | zoom out / in | reset |
| **Camera** | Android: switch Photo / Video | take a photo, or start / stop recording |
| **Torch** (Android) | brightness of the torch | on / off |
| **Teleprompter** (Android, off by default) | move the script | play / pause |
| **Screenshot**, **Claude** (Android) | one-shot items: pick them to run | |
| **Your own shortcuts** (desktop) | | press any key combo you add |

## Settings

Windows: click the tray icon. macOS: menu-bar icon → Settings. Android: the app's home screen.

- **Controls:** your triggers (see above).
- **Wheel:** which tools are on it, their order, which one is active when Orbit starts.
- **Shortcuts** (desktop): add wheel items that press a key combo.
- **Scroll:** how far each step goes and how much fast turns speed up (with reset to defaults).
- **Look:** dark, light or follow the system.

## Turning Orbit off

- **Windows / macOS:** tray / menu-bar icon → untick **Orbit on**. Every button then works as if
  Orbit weren't installed.
- **Android:** the switch at the top of the app, **Turn off** on Orbit's notification, or the
  **Orbit** Quick Settings tile.

## Troubleshooting

- **The wheel never opens:** check which trigger opens it in Settings → Controls (**Open menu**) and
  press it on that screen: does it light up? If not, Orbit isn't receiving it. Earbuds: make sure
  they're connected to this device and their gestures send play / pause / next / previous (CMF
  dial: see [its guide](#cmf-buds-pro-2-the-case-dial)). Android: Help → **Wheel won't open?**
  turns green when a press arrives.
- **A key does nothing or does its old job:** Orbit may be off (tray / menu-bar), or the trigger is
  set for a different press (tap vs hold). Record it again.
- **Can't find Orbit on Windows:** it's in the system tray; click **^** by the clock. Opening Orbit
  again also opens Settings.
- **Trackpad gestures also switch desktops (Windows):** set Windows' own 3- / 4-finger gestures to
  *Nothing* (see [Trackpad gestures](#trackpad-gestures)).
- **macOS: keys stopped working after an update:** System Settings → Privacy & Security →
  Accessibility → switch Orbit off and on.
- **macOS: keys don't reach Orbit while typing a password:** macOS blocks all key capture in password
  fields ("Secure Input"); it comes back on its own.
- **Android: the Accessibility switch is greyed out:** App info → ⋮ → **Allow restricted settings**.
- **Android: Orbit stops after a while:** some phones close background apps. Allow Orbit to run
  in the background (battery settings: *Unrestricted*), see [dontkillmyapp.com](https://dontkillmyapp.com).

Still stuck? Ask in the [Telegram group](https://t.me/orbit_issues) with your device and the log
(see below).

## Privacy and permissions

Orbit runs only on your device and sends nothing anywhere. It doesn't even have internet access.

- **Windows:** keyboard and mouse hooks to see your trigger buttons (others pass straight through);
  admin only for press-and-hold over admin apps.
- **macOS:** Accessibility, to see your trigger buttons and press keys for the tools.
- **Android:** an accessibility service draws the wheel, does what you pick and sees button presses
  to match your triggers (presses no trigger uses go straight on and aren't kept). It reads the name
  of the app in front (for the app switcher) and the camera's buttons when you use the Camera tool.
  Notification access lets your music still play / pause; *Modify system settings* is for the
  Brightness tool; the motion sensor is used only for back tap, chop and twist.

## Help and feedback

Questions, problems, ideas? Join **[Orbit on Telegram](https://t.me/orbit_issues)**, or
[open an issue](https://github.com/harsha20599/orbit/issues/new/choose).

Logs help a lot: Windows tray icon → **Open log** (`%LOCALAPPDATA%\Orbit\orbit.log`); macOS
`~/.orbit/orbit.log`; Android: Help → **Report a problem** copies the log.

## License

Free to use, change and share under the [Orbit License](LICENSE): MIT, plus one rule. **If you
share anything built on Orbit publicly** (an app, a fork, a video or post showing your work),
**credit "Based on Orbit by Yemcube"** with a link to Instagram
[@yem.cube](https://www.instagram.com/yem.cube). Private use needs no credit.

Icons: [Lucide](https://lucide.dev) (ISC). Orbit is not affiliated with Nothing or CMF.

---

# For developers

| | Desktop (Windows, macOS) | Android |
|---|---|---|
| Code | `orbit/` (Python 3.11+, Qt / PySide6) | `android/` (Kotlin, Compose) |
| Run | `pip install -r requirements.txt` then `python -m orbit` | `cd android && ./gradlew assembleDebug` |
| Tests | `python -m pytest -q tests` | `cd android && ./gradlew testDebugUnitTest` |

Useful flags: `python -m orbit --no-elevate` (Windows, no admin prompt), `--dev` (accept test
events: `python -m orbit.inject double`), `--debug` (verbose log).

## How input reaches Orbit

Every input becomes an **input id** (`key:ctrl+f13`, `mouse:back`, `scroll:ctrl+up`,
`touchpad:3-swipe-left`, `media:play`, `vol:up`, and on Android `key:24`, `backtap:2`,
`motion:chop`). A **Trigger** is an input plus a press (tap, double, triple, hold; one-shot inputs
have none), and **Controls** maps triggers to the four functions. `ControlsHub` runs a
`PressRecognizer` per input (300 ms between taps, 500 ms hold, repeats while a move is held) and
emits events the engine already understands (moves arrive as turns, select as a press).

| | Windows | macOS | Android |
|---|---|---|---|
| Keys, media keys, mouse buttons | `WH_KEYBOARD_LL` / `WH_MOUSE_LL` hooks (swallow only bound inputs, skip Orbit's own events by a `dwExtraInfo` tag) | `CGEventTap` (session, head), own events tagged in `kCGEventSourceUserData` | `AccessibilityService.onKeyEvent` |
| Scroll with a key | wheel messages, 120 per notch | scroll events (momentum ignored) | — |
| Trackpad | Raw Input from Precision Touchpads (HID 0x0D / 0x05) → `orbit/core/touch.py` | magnify / rotate / swipe events | — |
| Earbuds' presses | own SMTC session | `MPRemoteCommandCenter` | own `MediaSession` |
| CMF dial turns | endpoint volume callback | CoreAudio volume | `STREAM_MUSIC` volume |
| Back tap, chop, twist | — | — | accelerometer / gyro detectors (`core/BackTap.kt`, `core/Motion.kt`) |

Keeping it working: key-ups are paired with their downs; a press is let go after 30 s if its up
was lost; everything is released on lock, sleep, screen off and Secure Input; Windows re-installs
its hooks if Windows drops them (watchdog) and after unlock / resume, and sends a mask key so a
swallowed Win+key doesn't open Start; the macOS tap is re-enabled, re-created when Accessibility is
granted, and torn down if it's removed. Presses no trigger uses are re-sent so the key keeps its
normal job.

### The CMF Buds Pro 2 dial

| Gesture | Over Bluetooth | Windows | macOS | Android |
|---|---|---|---|---|
| Turn | AVRCP absolute volume (about 1/16 per click, at most ~3 a second) | endpoint volume callback | CoreAudio | `STREAM_MUSIC` poll |
| Press ×1 / 2 / 3 | AVRCP play-pause / next / previous | SMTC | now-playing session | `MediaSession` |
| Hold | HFP `AT+BVRA` | raw HCI via ETW (admin) | — | `VOICE_COMMAND` |

Turning is borrowed from volume, so `orbit/core/volume_dial.py` (and its Kotlin port) learns the
click size, filters the buds' stale reports and restores the level after you stop. Tests replay
real traces recorded with the buds.

## Code map

```
orbit/                      desktop app
  core/                     no OS or UI code: controls (triggers, presets, PressRecognizer,
                            Router), engine, tools, touch (trackpad gestures), volume_dial
  platform/windows/         input_keys + keynames (hooks), touchpad (Raw Input), media, volume,
                            Bluetooth ETW, brightness, output
  platform/mac/             input_keys + keytap (event tap), media, volume, output, overlay
  ui/                       settings_window, controls_ui (setup, Choose / Record), qml/ (wheel, HUD)
android/app/src/main/kotlin/app/orbit/dial/
  core/                     Controls, Engine, Tools, VolumeDial, BackTap, Motion (pure Kotlin)
  OrbitAccessibilityService, OrbitMediaService, Onboarding, ControllersUi, MainActivity
tests/                      desktop tests (incl. test_trigger_edges.py: lost key-ups, timing edges…)
tools/                      key_capture_check.py (real Windows hooks), startup_check.py, inject…
docs/                       research notes, mac-controls-test.md (hands-on Mac checklist)
```

## Releasing

Bump `orbit/__init__.py`, update `packaging/RELEASE_NOTES.md`, push `main`, then push a tag
`vX.Y.Z`. The `release` workflow tests and builds all three apps (and checks the packaged Windows
app starts) into a **draft** release with the files `Orbit-Windows-Setup.exe`, `Orbit-macOS.zip`
and `Orbit-Android.apk`; publish it with `gh release edit vX.Y.Z --draft=false --latest`. The
Android release key is kept outside the repo (CI secrets `ORBIT_KEYSTORE_B64` /
`ORBIT_KEYSTORE_PASSWORD`). Play Store builds use `ORBIT_APP_ID=com.littyl.orbit`.
