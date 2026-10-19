---
name: drive-phone
description: Operates an Android phone or emulator through the digitomancy MCP tools — reading the screen, tapping, swiping, typing, launching apps, and remembering buttons as anchors. Use when the user asks to "do something on my phone", "open X on the phone", "tap", "check what's on screen", "automate this app", "read my settings", or names an Android app to operate, and whenever digitomancy tools are about to be called.
---

# Drive the phone

Operate the device through the `digitomancy` MCP tools. Treat the phone as the user's real device: some taps have real-world effects.

## The loop

1. **Look.** Call `look` for a compact list of on-screen elements. Each line is `#idx Class 'text' id=resource @(x,y) tap`, where coordinates are fractions of the screen. Call `screenshot` only when `look` can't see the content (games, canvases, video, maps) or when the layout is ambiguous.
2. **Prefer known paths.** Call `list_maps` and `list_routines` once per session. If a routine already does the job, run it with `run_routine`. If a map has an anchor for the target, use `tap_anchor "map:name"`.
3. **Act on elements, not pixels.** Use `tap_node <idx>` from the latest `look`. Fall back to `tap x y` with fractional coordinates only for things the UI tree doesn't expose. Re-`look` after every action that changes the screen; node indexes go stale.
4. **Verify.** After an action, confirm the expected screen with `look` or `check "map:screen"` before taking the next step. Never chain several blind taps.
5. **Remember.** When a target had to be found by hand and will likely be needed again, call `save_anchor` with the node index. It stores a selector (survives layout changes) plus a fractional point (fallback). Use the app's name as the map name.
6. **Release.** Call `release` when finished. While uiautomator is connected, the phone's accessibility services (Tasker, AutoInput, screen readers, button remappers) are suspended. The server also releases automatically after 60s idle.

## Safety rules

- **Read the map's hazards first.** Each map YAML may contain a `hazards:` list. Those rules are binding: never tap what they forbid.
- **Ask before anything with consequences.** Get explicit confirmation before sending messages or email, making purchases or payments, deleting data, changing accounts or security settings, toggling switches in Settings, granting permissions, or running a task or automation the user hasn't described. Reading is free; changing needs a yes.
- **Never disable USB debugging, developer options, or wireless debugging.** That severs the connection mid-task.
- **Never force-stop automation apps** (Tasker, MacroDroid, Automate, AutoInput). It kills their background monitoring.
- **Treat widgets and shortcuts on the home screen as live controls.** Smart-home, door, and payment widgets act on the real world. Don't coordinate-tap the home screen without looking first.
- **Respect auto-rotate.** Fractional points mean different spots in portrait and landscape. `look` reports the current size; re-look if it changed.

## Useful tools beyond the loop

| Tool | Use for |
|---|---|
| `devices` | Which registered devices are online, the default, unregistered serials |
| `workspace` | Where `devices.yaml`, maps, routines, and failure snapshots live |
| `launch` | Start an app by package name (resolves the real launcher activity) |
| `key` | `back`, `home`, `enter`, `recent`, `volume_up`, … |
| `swipe` | Scrolling: `swipe 0.5 0.75 0.5 0.35` scrolls down a page |
| `check` | Evaluate a saved screen checkpoint without acting |
| `shell` | Raw `adb shell` for reads the UI can't give (e.g. `settings get global adb_enabled`, `dumpsys battery`). Prefer read-only commands; ask before anything that writes. |

## When things go wrong

- A failed `run_routine` returns the failed stage, an error, a snapshot directory (screenshot plus UI dump), and a `resume_hint`. Read the snapshot before guessing, fix the screen state, then resume with `resume_from`.
- If `look` shows a different app than expected, a dialog, ad, or permission prompt may be on top. Handle it (usually `key back`) and look again.
- If no device is online, switch to the **connect-phone** skill.
