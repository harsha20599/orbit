# Orbit

**Turn the controls you already have into a controller for your computer and phone.**

Open a wheel of tools, move to pick one, press to choose. Then your control drives that tool:
scroll pages and reels, flip slides, scrub a video timeline, change brightness, switch apps,
undo / redo, take a photo or a video, and more. Works on **Windows, macOS and Android**. Free,
with the source code here.

**What can drive it:** the CMF Buds Pro 2 case dial (the original), any earbuds or headphones
with buttons (AirPods, OnePlus, Galaxy, Pixel Buds…), wired earphones, Bluetooth speakers,
keyboard volume knobs and media keys, any key or shortcut, mouse side buttons, Ctrl + scroll,
trackpad gestures, and on Android the phone's volume keys, selfie sticks, remotes, game pads,
back tap, chop and twist. Setup asks what you have and sets it up; Settings → Controls lets
you change any trigger (Choose from a list, or Record by pressing it).

## Download

Get the latest version from **[Releases](https://github.com/harsha20599/orbit/releases/latest)**:

| | File | Install |
|---|---|---|
| **Windows 10 / 11** | `Orbit-Windows-Setup.exe` | Run it. Windows may say "Windows protected your PC": click **More info → Run anyway** (the app isn't code-signed yet). When Orbit starts it asks for admin: say yes, it's needed to read press-and-hold. |
| **macOS 13+** (Apple Silicon) | `Orbit-macOS.zip` | Unzip, drag **Orbit.app** to Applications. The first time, **right-click → Open** (it isn't notarized yet). Allow **Accessibility** when asked (System Settings → Privacy & Security → Accessibility). |
| **Android 8+** | `Orbit-Android.apk` | Open it on the phone and allow installing from your browser. Then in Orbit, follow the setup checklist. If the Accessibility switch is greyed out: App info → ⋮ → **Allow restricted settings**. |

## CMF Buds Pro 2: set the dial's gestures

Orbit reads the dial through the buds' music controls, so the dial has to send them.
In the **Nothing X** app (on a Nothing phone: Settings → Connected devices → CMF Buds Pro 2)
→ **Controls → Dial**, set:

| Dial gesture | Set it to |
|---|---|
| Single press | Play / Pause |
| Double press | Next track |
| Triple press | Previous track |
| Press and hold | Voice assistant |

If the wheel never opens, this is almost always why. On Android, Help → **Wheel won't open?** in the app
turns green the moment a press arrives.

## Using it

| Do this | When a tool is active | When the wheel is open |
|---|---|---|
| **Turn** | drives the tool | moves the highlight |
| **Press** | the tool's action (or play / pause) | choose it |
| **Double press** | open the wheel | close |
| **Triple press** | back to the previous tool | close |
| **Hold** | Windows: Claude dictation · Android: open Claude | close |

Optional tools you can switch on in Settings include **Teleprompter** on Android (turn to move
the script, press to play / pause, for apps like NEEWER Teleprompter).

Everything is adjustable in **Settings** (tray / menu-bar icon → Settings…, or the Android app's
home screen): which tools are on the wheel and in what order, what each press does (including
"Open an app…"), your own keyboard-shortcut items, scroll speed, light / dark look.

## Controls: any buttons

The dial is only the start. In **Settings → Controls** (Android: **Set up controls**) pick
what does each of Orbit's four functions (**Single press / Select, Open menu, Previous,
Next**), with any mix of:

- the CMF dial, or any earbuds' or headphones' press gestures (AirPods, OnePlus, Galaxy…)
- volume and media keys, a keyboard's volume knob, spare keys (F13–F24) and shortcuts
- mouse side buttons (Windows, macOS)
- the phone's volume keys, back taps, chop or twist (Android)

Each trigger can be a tap, double tap, triple tap or hold. Start from a preset, then
**Choose** (search or browse) or **Record** (press it the way you'll use it). Keys you use
for Orbit are taken from apps while Orbit is on; every other key works as usual.
Optional extra functions: Open assistant, Previous tool, Custom command (desktop).

## Good to know

- **Fast spins lose some clicks.** The buds send at most about three dial steps a second and
  drop the rest, so Orbit makes fast turning go further to compensate. Slow clicks are exact.
- **Each click makes a small tone in the buds.** That's the buds' firmware; Orbit can't turn it off.
- **macOS shows its own volume slider** on each click. macOS doesn't let apps hide it.
- **Press-and-hold** works on Windows (with admin) and Android; macOS doesn't pass it to apps.
- **Privacy:** Orbit runs only on your device and sends nothing anywhere. On Android, its
  accessibility service draws the wheel and performs the actions you pick; it reads only the
  name of the app in front (for the app switcher) and, when you press with the Camera tool,
  the camera app's buttons to find its shutter.

## Turning Orbit off

- **Windows / macOS:** tray / menu-bar icon → untick **Orbit on**. The buds then work as if
  Orbit weren't installed (press = play / pause, dial = volume). Clicking the tray icon opens
  Settings; opening Orbit again while it runs does the same.
- **Android:** the switch at the top of the app, **Turn off** on Orbit's notification, or the
  **Orbit** Quick Settings tile (edit your Quick Settings to add it).

## If something's off

- **The wheel never opens:** set the dial gestures above. On Windows also check the tray
  menu says **Buds connected**: the buds must be this PC's audio output.
- **Can't find Orbit on Windows:** it lives in the system tray; click **^** by the clock.
  Starting Orbit again opens its Settings.
- **Android: the Accessibility switch is greyed out:** App info → ⋮ → **Allow restricted settings**.

## License

Free to use, change and share under the [Orbit License](LICENSE): MIT, plus one rule. **If you
share anything built on Orbit publicly** (an app, a fork, a video or post showing your work),
**credit "Based on Orbit by Yemcube"** with a link to Instagram
[@yem.cube](https://www.instagram.com/yem.cube). Private use needs no credit.

## Help and feedback

Questions, problems, ideas? Join **[Orbit on Telegram](https://t.me/orbit_issues)**, or
**[open an issue](https://github.com/harsha20599/orbit/issues/new/choose)**.
Logs help a lot: tray / menu-bar icon → Open log (Windows `%LOCALAPPDATA%\Orbit\orbit.log`,
macOS `~/.orbit/orbit.log`); on Android, Help → **Report a problem** copies the log.

---

# For developers

## Overview

The case dial on the CMF Buds Pro 2 becomes a Surface-Dial-style controller on
**Windows, macOS and Android**: **double-press** to open a wheel, **turn** to pick a
tool, **press** to use it. After that, turning and pressing drive the chosen tool
(volume, brightness, scroll, zoom, app/window switcher, undo, tabs, ...).

| | Windows | macOS | Android |
|---|---|---|---|
| Code | `orbit/` (Python) | `orbit/` (Python) | `android/` (Kotlin) |
| Turn | ✅ verified with the buds | built, CI-tested, **needs a Mac + buds** | built, emulator-tested, **needs a phone + buds** |
| Press / double / triple | ✅ verified | built (MPRemoteCommandCenter) | ✅ emulator (same path as the buds) |
| Hold | ✅ (admin) → Claude dictation | not observable on macOS | ✅ emulator (VOICE_COMMAND) → Claude |
| Wheel + HUD | ✅ | built (Qt, same QML) | ✅ emulator |

## Gestures (all platforms)

| Gesture | Tool active | Wheel open |
|---|---|---|
| Turn | drives the tool | moves the highlight, one item per click, wraps |
| Press | tool's click, else play/pause on your music app | **select** |
| Double press | **open wheel** | close, no change |
| Triple press | back to the previous tool (Volume: next track) | close, no change |
| Hold | Windows: Claude Quick Entry + voice typing · Android: open Claude · macOS: — | close, no change |
| Wait 5 s | — | keeps the highlighted tool (one-shot actions never fire on timeout) |

Fast spins go further (scroll, brightness); careful single clicks stay exact; turning
back is always one precise step. While the wheel is open your audio drops to half so
each click's volume blip stays soft. (The tone per click is the buds' firmware.)

## Windows

```
pip install -r requirements.txt
python -m orbit              # asks for admin (only needed for press-and-hold)
python -m orbit --no-elevate # everything except hold
python -m orbit --dev        # also accept test events: python -m orbit.inject double
```
Desktop tools include Timeline (DaVinci Resolve / Premiere / Final Cut: careful clicks step a frame, fast turning jumps with Shift+arrow, press = play/pause), Slides (one slide per click, press = black screen) and Camera (press = shutter in the Windows Camera app / Photo Booth; off the wheel by default).

Tray icon: Show wheel, Settings (scroll feel sliders, any gesture can "Open an app…" by name, wheel items on/off and order, start tool, what each press
does, dark / light / match-system appearance, your Claude Quick Entry shortcut, and custom
**Shortcuts**: wheel items that press a key combo when you pick them and press the dial;
saved to `settings.json` next to your config and applied at once), Open config (your
overrides: a short file in `%APPDATA%\Orbit` / `~/Library/Application Support/Orbit` that
is merged over the built-in `config.toml`, so updated defaults still reach you), Open
log, Restart, Quit; toggle "Hide Windows volume
bar". Log: `%LOCALAPPDATA%\Orbit\orbit.log`. Brightness drives Twinkle Tray if installed.

## macOS

```
pip install -r requirements.txt       # pulls the PyObjC frameworks on macOS
python -m orbit
```
1. Pair the buds and make them the output device.
2. Grant **Accessibility** when prompted (System Settings → Privacy & Security →
   Accessibility → enable the app you launched Orbit from), then restart Orbit.
   Keep `--config` files out of `~/Documents`, `~/Desktop` and `~/Downloads`: macOS
   holds the read for a privacy prompt and Orbit waits silently before it can log.
   Without it, keys and scrolling are silently dropped.
3. The first time a press is forwarded to Spotify/Music, allow the Automation prompt.

Shortcuts are remapped for macOS in `config.toml` → `[platforms.mac]` (Cmd instead of
Ctrl, Cmd+Tab app switcher, Spaces). Brightness: built-in display via DisplayServices,
external monitors via [`m1ddc`](https://github.com/waydabber/m1ddc) if on PATH.
Known limits: the system volume HUD may flash per click (no public way to hide it);
hold isn't available. First-run checklist: [docs/research-macos.md](docs/research-macos.md#test-checklist-first-session-on-a-mac-with-the-buds).

## Android

Install the APK (CI artifact `orbit-android-debug`, or `cd android && ./gradlew assembleDebug`),
open **Orbit**, and work through the checklist:
1. Notifications · 2. Accessibility (draws the wheel, performs actions — if the switch
is greyed out: App info → ⋮ → Allow restricted settings) · 3. Notification access (so a
press still plays/pauses your music app) · 4. Press-and-hold: tap, pick **Orbit →
Always** · 5. Modify system settings (Brightness tool).

Android tools: Volume, Brightness, Slides (one sideways swipe per click), Camera (press the dial = shutter; opens the camera if needed), Scroll (one flick per click: next / previous reel,
Short or story; about a page in lists), Apps (a strip of recent-app icons: each click
moves the highlight, let go of the dial ~0.9 s or press to open it), Zoom (magnification), Torch, and
one-shot Screenshot and Claude. Known limits: the system volume panel flashes per click
(the Bluetooth stack requests it); a hold is detected at most about once per 5 s.

## How the dial reaches the host (reverse-engineered)

| Gesture | Over Bluetooth | Windows | macOS | Android |
|---|---|---|---|---|
| Turn | AVRCP absolute volume (1/15–1/16 per click, ≤ ~3/s) | endpoint volume callback | CoreAudio VirtualMainVolume | 40 ms poll of STREAM_MUSIC |
| Press ×1/2/3 | AVRCP play-pause / next / previous | own SMTC session | own now-playing session | own MediaSession |
| Hold | HFP `AT+BVRA=1` (or `=0`, the buds toggle) | raw HCI via ETW (admin) | — | VOICE_COMMAND intent |

Turning is borrowed from volume, so `orbit/core/volume_dial.py` (and its Kotlin port)
learns the click size, treats any change in a direction as at least one click, filters
the buds' stale reports after Orbit resets the level, and restores the level 0.9 s after
you stop turning. Tests replay real traces recorded with the buds.

## Code map

```
orbit/                     desktop app (Python, Qt Quick UI)
  core/                    no OS or UI code: events, engine, tools, actions, config,
                           volume_dial (click detection), motion (spin speed)
  platform/windows/        volume, media session, Bluetooth ETW, flyout hiding, output
  platform/mac/            CoreAudio (ctypes), MPRemoteCommandCenter, Quartz output, overlay
  ui/                      qtui.py bridge, qml/ (two small windows: wheel, HUD), icons/
android/app/src/main/kotlin/app/orbit/dial/
  core/                    Kotlin ports: VolumeDial, SpinTracker, Engine, Tools
  OrbitAccessibilityService, OrbitMediaService, OverlayController/OverlayUi,
  HoldTrampolineActivity, MainActivity (setup)
tests/                     desktop tests (python -m pytest -q)
tools/                     render_overlay.py (offscreen render check), mac_smoke.py,
                           bt_diag.py, svg_to_vector.py
docs/                      research.md (interaction design), research-macos.md, research-android.md
```

CI (`.github/workflows`): Windows + macOS unit tests, offscreen overlay render, macOS API
smoke test; Android unit tests + debug APK.

Icons: [Lucide](https://lucide.dev) (ISC).
