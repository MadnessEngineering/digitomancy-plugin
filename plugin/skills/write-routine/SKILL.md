---
name: write-routine
description: Turns a phone task into a saved, repeatable digitomancy routine — an app map (anchors and screen checkpoints in YAML) plus a staged Python routine that can resume after failures. Use when the user says "save this as a routine", "make a script for this", "automate this every time", "remember how to do this on my phone", "map this app", or after a manual phone task that is likely to be repeated.
---

# Write a routine

A routine is a saved multi-step phone task. It has two parts, both stored in the user's workspace (call the `workspace` tool for the paths):

- **A map** — `maps/<app>.yaml`: named **anchors** (things to tap) and named **screens** (checkpoints that prove where we are). Referenced as `app:name`.
- **A routine file** — `routines/<topic>.py`: Python that walks through **stages**, each one resumable.

Full syntax: `references/api.md`. A worked example: `references/example.md`.

## Process

1. **Walk it once by hand** with the drive-phone loop (`look` → act → verify). Note each screen you pass through and each element you tap.
2. **Build the map as you go.** For every element tapped, call `save_anchor` with the node index. That records a selector plus a fractional point. For each screen, write a checkpoint under `screens:` that identifies it uniquely: usually the activity name or a distinctive element, plus `app:`.
3. **Record hazards.** Add a `hazards:` list to the map naming anything on these screens that must never be tapped (live toggles, delete buttons, things with real-world effects), and why.
4. **Write the routine.** One stage per screen transition. Give every stage after the first a `requires=` screen, so a failed run can `resume_from` that stage. End each stage with `ctx.expect(...)` for the screen it should land on.
5. **Return data, don't print it.** Anything the routine reads goes in `ctx.result[...]`; it comes back in the run report.
6. **Test it.** `list_routines` (confirms it loads), then `run_routine`. On failure, read the snapshot directory, fix the map or routine, and resume from the failed stage instead of starting over.
7. **Release** when done.

## Rules of thumb

- **Selectors beat points.** Prefer `resourceId`; add `text` when ids repeat in lists. Use `textMatches` with a regex like `"(?i)^(wi-?fi|internet)$"` when wording varies across Android skins. Keep `point` only as a fallback.
- **Deep-link when possible.** `ctx.intent("android.settings.WIFI_SETTINGS")` beats walking menus. `ctx.launch(pkg)` resolves the real launcher activity.
- **Read-only first.** Write routines that read and report before writing ones that change things. Any stage that changes state should be its own stage, named for what it changes, and the user should approve the routine before it runs.
- **Lists:** use `ctx.scroll_collect(collect_fn, key=..., guard=...)`. A `guard` that checks we're still on the expected activity stops runaway swipes when a gesture opens something unexpected.
- **Games and canvases:** no UI tree. Use `image:` checkpoints (template PNGs stored next to the map, needs the `vision` extra) and point anchors.
- **Don't force-stop** (`stop_first=True`) apps that run background automations.
