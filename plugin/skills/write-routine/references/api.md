# Digitomancy routine API

## Map file: `maps/<app>.yaml`

```yaml
app: com.example.app            # package; used by `app:` checks and save_anchor
hazards:                        # binding: never tap these
  - "switch_bar toggles the feature live"
anchors:
  compose:
    selector: {resourceId: "com.example.app:id/fab"}   # tried first (waits up to 3s)
    point: [0.88, 0.91]                                 # fallback, fractions of the screen
    notes: "bottom-right compose button"
  inbox:
    selector: {textMatches: "(?i)^inbox$"}
screens:
  home:                         # all = every condition must hold (default for a bare list)
    all:
      - app: com.example.app
      - anchor: example:compose
  loading_or_error:             # any = one is enough
    any:
      - selector: {textContains: "Loading"}
      - selector: {text: "Try again"}
```

**Selector keys** (uiautomator2): `text`, `textContains`, `textMatches`, `textStartsWith`, `resourceId`, `resourceIdMatches`, `description`, `descriptionContains`, `className`, `checked`, `enabled`, `index`, `instance`.

**Screen conditions:**

| Condition | True when |
|---|---|
| `selector: {...}` | element exists |
| `gone: {...}` | element absent |
| `app: pkg` | foreground package equals pkg (physical display only) |
| `activity: substr` | foreground activity contains substr |
| `anchor: map:name` | that anchor's selector exists |
| `image: path.png` (+ `threshold: 0.85`) | template matches the screenshot; path relative to `maps/` |

## Routine file: `routines/<topic>.py`

```python
from digitomancy.routines import Routine, routine

flow = Routine("app.do_thing", "One-line description", params={"query": "what to search for"})

@flow.stage("open")
def _(ctx):
    ctx.launch("com.example.app")
    ctx.expect("example:home")

@flow.stage("search", requires="example:home")
def _(ctx):
    ctx.tap("example:search")
    ctx.type(ctx.params.get("query", ""))
    ctx.key("enter")
    ctx.expect("example:results", timeout=15)
    ctx.result["first"] = ...

@routine("app.quick", "Single-stage shorthand; params arrive as kwargs")
def quick(ctx, times="1"):
    for _ in range(int(times)):
        ctx.key("back")
```

- Routine names are global; prefix them with the app or topic.
- Stages run in order. `requires` is checked (5s) before the stage runs, which is what makes `resume_from` safe.
- Files starting with `_` are not loaded.

## `ctx` methods

| Method | Does |
|---|---|
| `tap("map:anchor")` / `tap((x, y))` | anchor (selector, then point) or coordinates (fractions or pixels) |
| `expect(screen, timeout=10)` | wait for a screen; raises with a snapshot if it never appears |
| `check(screen, timeout=0)` | non-raising probe → bool, for branches (close an ad if present) |
| `launch(pkg, stop_first=False)` | start app via its real launcher activity |
| `intent(action, extra="")` | `am start -a ACTION` deep link |
| `key(name)` | back, home, enter, recent, volume_up, delete, … |
| `swipe(x1, y1, x2, y2, duration=0.3)` | gesture |
| `type(text, clear=False)` | type into focused field |
| `sleep(seconds)` | pause |
| `scroll_collect(collect, max_swipes=25, key=repr, guard=None)` | swipe until no new items; returns de-duplicated list |
| `tasker(task, **params)` | fire a Tasker task (see tasker-bridge skill) |
| `ctx.device` | lower level: `dump()`, `shell(cmd)`, `current_app()`, `size`, `screenshot(path)` |
| `ctx.params` / `ctx.result` | inputs / outputs |

For parsing Settings-style lists: `from digitomancy import ui` → `ui.rows(ctx.device.dump())` returns `[{title, summary, checked}]`.

## Run report

```json
{"routine": "...", "device": "...", "ok": false, "passed": ["open"],
 "failed": {"stage": "search", "error": "...", "snapshot": ".runs/<stamp>_<label>",
            "resume_hint": "fix the screen, then run with resume_from='search'"},
 "result": {...}, "log": ["12:00:01 stage open", "..."]}
```

Snapshot directories hold `screen.png`, `hierarchy.xml` and `activity.txt` (per-display foreground activities).
