---
name: tasker-bridge
description: Connects digitomancy to Tasker on the phone — firing Tasker tasks over adb with optional results, exploring the Tasker app read-only, and analyzing Tasker backup XML (which tasks use which actions, privileged or device-owner actions). Use when the user mentions Tasker, "run my Tasker task", "what's in my Tasker", "audit my Tasker config", "which tasks use X", or wants a routine to call a Tasker task.
---

# Tasker bridge

Three jobs: **run** Tasker tasks from the agent, **explore** the Tasker app safely, and **analyze** Tasker backups.

## Safety first

- **Never run a task you haven't read.** Tasker tasks can unlock doors, send messages, toggle radios, or wipe data. Describe what a task does and get a yes before `tasker_run` on anything the user didn't name explicitly.
- **Never tap a profile's enable switch** (`button_enabled`) — it toggles the profile live.
- **Never force-stop Tasker** — it kills profile monitoring until Tasker restarts.
- **Long-press on project tabs opens a menu with Delete.** Tap only.
- **Release uiautomator when done** (`release`). While it's connected, Tasker's own accessibility service, and AutoInput's, are suspended, so Tasker profiles that depend on them stop firing.

## 1. Run tasks (`tasker_run`)

Digitomancy fires a broadcast that a one-time Tasker profile turns into a task call. **This needs a phone-side setup first** — walk the user through it, then test with a harmless task (e.g. one that shows a Flash).

1. **Profile:** Event → System → **Intent Received**, Action `cc.madness.digitomancy.RUN`.
2. **Task "DGM Dispatch"** for that profile: **Perform Task** with Name `%task`, Parameter 1 `%par1`, Parameter 2 `%par2`.
3. **Optional result channel:** in a task that should answer, if `%dgm_id` is set, **Write File** `Download/digitomancy/%dgm_id.json` with a JSON body. Call `tasker_run` with `wait_result` (seconds) to poll for and read it.

Intent extras arrive as lowercase local variables (`par1` → `%par1`). Inside routines, use `ctx.tasker("Task Name", par1="x")`.

**Status: the bridge is unit-tested but has not yet been verified end-to-end on a device.** Treat the first run as a test and confirm with the user that the task actually fired.

**Tasker or routine?** Tasker for what it already does well (system toggles, intents, plugins, scheduled and event triggers). Digitomancy routines when the agent needs to see the screen, verify checkpoints, or recover from surprises. Combine them freely.

## 2. Explore the app (read-only)

The workspace ships a `tasker` map (anchors for the PROFILES/TASKS/SCENES/VARS tabs, screens, and hazards) and two read-only routines:

- `tasker.projects` — lists project tabs by swiping the tab bar (no taps).
- `tasker.profiles` — reads every profile in the selected project: name, enabled, contexts, tasks.

Tapping a task row opens the task editor; back out without editing. Don't tap **Save & Apply** unless the user asked for a change.

## 3. Analyze a backup

Reading a backup is far faster and safer than scrolling the UI, and it sees everything.

1. Find backups: `shell "ls -d /sdcard/Tasker/configs/auto/*/"` (automatic, newest last) or `/sdcard/Tasker/configs/user/backup.xml` (manual).
2. Pull the newest locally with Bash: `adb -s <serial> pull <dir> <local-dir>`.
3. Run `python3 ${CLAUDE_PLUGIN_ROOT}/skills/tasker-bridge/scripts/tasker_backup.py <userbackup.xml>` for a summary: project/profile/task counts, action usage by name, and privileged actions with the tasks that use them. Add `--action "Kill App"` or `--code 18` to list the tasks using one action, and `--codes <file>` to load a fuller code table.

Notes on the format (the script already handles these):
- Backup XML is **not well-formed** (attributes run together), so parse with regex rather than an XML parser.
- Each action's `<code>` comes **after** its arguments; take the last `<code>` inside an `<Action>`.
- Codes in the millions or billions are **plugin actions** (AutoInput, AutoTools, Join…). Small unknown codes are newer built-in actions missing from public lists. Identify those through the Tasker UI if it matters.
- Device-owner–dependent behavior: the **Device Admin/Owner** action, and the **Wifi**, **Bluetooth** and **Kill App** actions, use Tasker's device-owner permission when it has one (Tasker 6.3+). `dumpsys device_policy` shows whether Tasker is device owner.
