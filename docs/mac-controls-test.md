# macOS: controls hands-on test

For the Mac session. Branch `experiment/any-controller`. The pure parts (key codes,
media-key decoding, swallow bookkeeping) are unit-tested on every OS; this checks the
real event tap on a Mac.

Setup: `pip install -r requirements.txt`, then `python -m orbit --debug`. Orbit must be
allowed under System Settings → Privacy & Security → **Accessibility** (it already asks).
Watch the log: `~/.orbit/orbit.log` (or the terminal).

| # | Do | Expect |
|---|---|---|
| 1 | Start Orbit | log: `key capture up: event tap up`. If it says `unavailable`, Accessibility isn't granted: grant it, restart Orbit. |
| 2 | Menu bar → Settings → Controls → **Load preset → Spare keys (F13–F16)** → Save | Rows show F13 / F14 / F15 / F16 |
| 3 | In any app, press **F16** | The wheel opens. F16 does nothing else. |
| 4 | **F14**, **F14**, then **F15** | Highlight moves twice, F15 selects |
| 5 | Type in TextEdit: letters, Space, Enter | Everything types normally (only bound keys are taken) |
| 6 | Settings → Controls → Next → Change → **Record** → press **⌘F13** → Use this → Done → Save | Next shows `Cmd+F13 · tap` |
| 7 | Press ⌘F13 / plain F13 | ⌘F13 moves Next; plain F13 is Previous (as set) |
| 8 | **Load preset → Keyboard volume knob / media keys** → Save. Press the Mac's **volume up / down** keys | The wheel highlight moves; the system volume does **not** change; no volume HUD |
| 9 | Press **play/pause** (F8 on Apple keyboards) | Select (in Volume: play / pause of the player) |
| 10 | Pick the Scroll tool, press volume up | Scrolls. Then pick Volume, press volume up: the volume goes up (Orbit steps it) |
| 11 | With a mouse that has side buttons: **Load preset → Mouse side buttons** → Save. Back / forward clicks; hold forward | Move; hold forward opens the wheel; Safari's back / forward don't fire |
| 12 | Settings open, press any bound key | Its function lights up; "Last heard: …" updates; nothing else happens |
| 13 | Menu bar → untick **Orbit on**; press F16 / volume keys | They behave as without Orbit (volume changes) |
| 14 | Earbuds (CMF Buds Pro 2): **Load preset → CMF Buds Pro 2** → Save; double press, turn, press | Same as before the change |
| 15 | Settings → Controls → Add a function → **Custom command…** → Press a key combo **⌘⇧4** → Next → Record a trigger (e.g. F17) → Save; press F17 | The screenshot crosshair appears |

Report the log lines from steps 1, 3 and 8, and any step that didn't match.
