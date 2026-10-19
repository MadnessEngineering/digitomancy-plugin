---
name: connect-phone
description: Sets up and troubleshoots the connection between digitomancy and an Android device — USB debugging, BlueStacks or other emulators over adb, wireless debugging, and the devices.yaml registry. Use when the user says "connect my phone", "set up phone automation", "the phone isn't showing up", "use BlueStacks", "add a device", or when digitomancy tools report no device online.
---

# Connect a phone

## Check the prerequisites

1. Confirm `adb` is installed: run `adb version`. If missing, tell the user how to install Android platform-tools (macOS: `brew install android-platform-tools`; Windows: `winget install Google.PlatformTools`; Linux: the distro's `android-tools` package).
2. Confirm `uv` is installed (`uv --version`); the MCP server runs through `uv run`. If missing: `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `winget install astral-sh.uv`.
3. Optional: `scrcpy` mirrors the screen in a window so the user can watch the automation.

## Connect the device

**Physical phone over USB:**
1. On the phone: Settings → About phone → tap **Build number** seven times to enable developer options.
2. Settings → System → Developer options → enable **USB debugging**.
3. Plug in, then accept the "Allow USB debugging?" prompt on the phone (tick "Always allow").
4. Run `adb devices -l`; the phone should show as `device`, not `unauthorized`.

**BlueStacks or another emulator:**
1. BlueStacks: Settings → Advanced → enable **Android Debug Bridge**. Note the port it shows (often 5555).
2. Run `adb connect 127.0.0.1:<port>`.
3. Other emulators: Android Studio emulators appear automatically; Genymotion and others usually need `adb connect`.

**Wireless debugging (Android 11+):** Developer options → Wireless debugging → Pair device with pairing code, then `adb pair <ip:port>` and `adb connect <ip:port>`.

## Register the device

1. Call the `workspace` tool to find `devices.yaml` (default `~/.digitomancy/devices.yaml`, override with the `DGM_HOME` environment variable).
2. Call `devices`: online serials that aren't registered appear under `unregistered_online`.
3. Edit `devices.yaml`: give each device a short name, its `serial`, `connect: true` for network devices, and set `default:`. Example:

```yaml
default: pixel
devices:
  pixel:
    serial: 0123456789ABCDEF
  bluestacks:
    serial: 127.0.0.1:5555
    connect: true
```

Unregistered serials also work directly as the `device` argument.

## Smoke test

Call `look`. The first connection installs uiautomator2's helper on the device and takes 10–20 seconds. Then call `release`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `unauthorized` in `adb devices` | Unlock the phone and accept the debugging prompt; if it never appears, revoke USB debugging authorizations in Developer options and replug |
| Device missing entirely | Try another cable/port (charge-only cables are common); on Windows, install the OEM USB driver |
| `look` reports the wrong app | Apps on scrcpy virtual displays are ignored by design; make sure the target is on the phone's real screen |
| Taps land in the wrong place | Screen rotated since the anchor was saved; re-look and re-save |
| Tasker/AutoInput stopped responding | uiautomator is still connected; call `release` |
