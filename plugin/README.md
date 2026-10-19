# Digitomancy

*Divination by fingers.* Lets Claude drive an Android phone or emulator: read the screen, tap and type, remember buttons as named anchors, and run saved multi-step routines that check where they are at every step and can resume after a failure.

## What you get

**Tools (MCP server `digitomancy`):**
- `look`: the screen as a compact list of elements
- `screenshot`
- `tap`, `tap_node`, `tap_anchor`, `swipe`, `key`, `type_text`, `launch`
- `check` for screen checkpoints
- `save_anchor`, `list_maps`, `list_routines`, `run_routine`
- `tasker_run`
- `devices`, `workspace`, `release`
- `shell` (raw adb)

**Skills:**
- **drive-phone**: the look → act → verify → remember loop, plus safety rules
- **connect-phone**: USB debugging, BlueStacks or emulators, wireless debugging, the device list
- **write-routine**: turning a task you did once into a saved, resumable routine
- **tasker-bridge**: running Tasker tasks from Claude, exploring Tasker read-only, analyzing Tasker backups

## Requirements

- `adb` (Android platform-tools) on your PATH
- `uv` (runs the server; on first start it creates the environment and fetches Python 3.11+ if needed, which takes a few seconds)
- An Android device with USB debugging enabled, or an emulator with ADB enabled
- Optional: `scrcpy`, to watch the phone on your screen while Claude works

## Your workspace

On first run the server creates `~/.digitomancy/`. Set the `DGM_HOME` environment variable to use another folder, such as a git repo you want to keep routines in. It contains:

- `devices.yaml`: your devices by name. Edit the `serial` values (from `adb devices`).
- `maps/`: app maps (anchors, screen checkpoints, hazards). Starters for Android Settings, Developer options and Tasker are included.
- `routines/`: saved routines. Starters include a Wi-Fi settings walk, a Developer options scan and read-only Tasker scans.
- `.runs/`: evidence from failed checkpoints (screenshot, UI dump, foreground activities).

Existing files are never overwritten.

## Good to know

- While Claude is connected through uiautomator, the phone's **accessibility services pause**, including Tasker, AutoInput and screen readers. The server releases the connection after 60 seconds idle, or immediately when the `release` tool is called.
- Claude asks before anything with consequences: sending, buying, deleting, toggling settings, or running automations you didn't describe.
- The **Tasker bridge** needs a one-time profile on the phone; the tasker-bridge skill walks you through it. It has unit tests but hasn't yet been verified end to end on a device.

## License

MIT. Copyright (c) 2026 Madness Engineering. See `LICENSE`.

## Credits

The Tasker action code table comes from [Taskomater/Tasker-XML-Info](https://github.com/Taskomater/Tasker-XML-Info) (MIT).
