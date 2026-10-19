# Digitomancy

*Divination by fingers.* Android automation for people and agents: read the screen, tap and type, remember buttons as named **anchors**, check where you are with **checkpoints**, and run multi-step **routines** that resume after a failure. Works with a USB phone, an emulator or BlueStacks, from a CLI, from Python, or from Claude as an MCP server and plugin.

**Status:** early but working. Tested on a Pixel 9 (Android 16) plus unit tests against a fake device. The Tasker bridge has unit tests but hasn't yet been verified end to end on a device.

## Why not just use X

| Tool | Good for | Why it isn't the whole answer |
|---|---|---|
| [mobile-mcp](https://github.com/mobile-next/mobile-mcp) | Ad-hoc agent poking via the accessibility tree | No memory: every session finds the same buttons again |
| [droidrun](https://github.com/droidrun/droidrun) | A full LLM agent framework | Heavy and opinionated if you already have agents |
| [uiautomator2](https://github.com/openatx/uiautomator2) | Fast Android-only driver, no Appium server | **Digitomancy builds on this** |
| Appium | Cross-platform QA | Needs a server; overkill for Android-only |
| [scrcpy](https://github.com/Genymobile/scrcpy) | Mirroring the screen | Use `dgm mirror` to watch automation live |

What Digitomancy adds: **named devices**, **anchor maps** (selector first, normalized coordinates as fallback), **checkpoints** with failure snapshots, **resumable routines**, and a **Tasker bridge**. What an agent finds once gets written down; the next run looks it up.

## Install

**As a Claude plugin:** build it with `scripts/build_plugin.sh` and install `dist/digitomancy.plugin`. You need `adb` and [`uv`](https://docs.astral.sh/uv/) on your PATH. See [plugin/README.md](plugin/README.md).

**As a CLI or library:**

```bash
git clone https://github.com/MadnessEngineering/digitomancy-plugin && cd digitomancy-plugin
uv sync --group dev             # add --extra vision for image-template checkpoints
uv run dgm doctor               # tools, workspace, which devices are online
```

**As an MCP server** in any MCP client:

```json
{"mcpServers": {"digitomancy": {"command": "uv", "args": ["run", "--project", "/path/to/digitomancy-plugin", "digitomancy-mcp"]}}}
```

## Connect a device

- **Phone:** enable Developer options (tap Build number 7 times), turn on USB debugging, plug in, and accept the prompt. On first connect uiautomator2 installs its helper on the device.
- **BlueStacks:** go to Settings → Advanced and enable ADB, then `uv run dgm -d bluestacks connect`. Check the port it shows; edit `devices.yaml` to match.

## Workspace

Your devices, maps and routines live in a workspace: `$DGM_HOME`, or `~/.digitomancy` by default, created on first run with starter maps and routines. Existing files are never overwritten.

- **`devices.yaml`:** names → serials. Pick one with `-d NAME`, `$DGM_DEVICE` or `default:`. Unknown names are used as raw serials.
- **`maps/<app>.yaml`:** `anchors` (things to tap), `screens` (checkpoint specs) and `hazards` (things never to tap). Refer to them as `map:name`.
- **`routines/*.py`:** routines built from **stages**. A stage can `require` a screen, and a failed run can `resume_from` that stage.
- **`.runs/`:** evidence from failed checkpoints (screenshot, UI dump, foreground activities).
- **`catalog/`** (optional, from `dgm catalog`): a redacted index of your Tasker projects and tasks. `hazards_manual.txt` and `hazard_patterns.txt` there tell the Tasker bridge which tasks it must never fire.

## Concepts

- **Coordinates:** a float in `[0,1]` is a fraction of the screen, and an int is a pixel. Maps store fractions so they work at any resolution. They still depend on orientation.
- **Checkpoints:** a screen spec combines conditions with `all` or `any`: `selector`, `gone`, `app`, `activity`, `anchor`, `image`. A failed `expect` saves a snapshot to `.runs/`.
- **Tasker:** `dgm tasker "Task Name" -p par1=x` fires a task through `am broadcast`. It needs a one-time profile on the phone; see [docs/TASKER.md](docs/TASKER.md).

## CLI

```
dgm doctor | connect | look [--all] | tap map:anchor|x,y | check map:screen
dgm routines | run NAME [-p k=v] [--resume-from STAGE]
dgm tasker TASK [-p k=v] [-w SEC] | catalog [SOURCES…]
dgm mirror [-- scrcpy args] | mcp
```

## Known conflicts

- **Accessibility suppression.** While uiautomator2's on-device server runs, Android suppresses every accessibility service: Tasker, AutoInput, Join, screen readers. The CLI stops the server when each command exits; the MCP server stops it after 60s idle or on `release`.
- **scrcpy `--new-display`.** Apps on virtual displays don't count as foreground. Detection reads Display #0 only.
- **Launching apps.** `Device.launch()` resolves the default launcher activity. uiautomator2's `app_start` can pick a random one, and some apps (Tasker) run a task from their second launcher activity.

## Development

```bash
uv run pytest -q                 # no device needed: tests use a fake device
./scripts/build_plugin.sh        # dist/digitomancy/ and dist/digitomancy.plugin
claude plugin validate dist/digitomancy
```

## License

MIT. Copyright (c) 2026 Madness Engineering. The Tasker action code table in the plugin comes from [Taskomater/Tasker-XML-Info](https://github.com/Taskomater/Tasker-XML-Info) (MIT).
