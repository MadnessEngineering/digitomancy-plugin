# Example: read every Developer options row

Shipped as a starter in the workspace (`routines/devopts.py`, `maps/devopts.yaml`).

```yaml
# maps/devopts.yaml
app: com.android.settings
hazards:
  - "switch_bar 'Use developer options' — turning it off disables USB debugging and drops our adb link. Never anchor it."
  - "USB debugging / Wireless debugging rows — same story."
anchors:
  search:
    selector: {description: "Search settings"}
screens:
  main:
    all:
      - activity: DevelopmentSettingsActivity
      - selector: {text: "Use developer options"}
```

```python
# routines/devopts.py (abridged)
from digitomancy import ui
from digitomancy.routines import Routine

scan = Routine("devopts.scan", "Open Developer options and read every row")

@scan.stage("open")
def _(ctx):
    ctx.device.stop("com.android.settings")   # Settings is safe to restart: fresh page starts at top
    ctx.intent("android.settings.APPLICATION_DEVELOPMENT_SETTINGS")
    ctx.expect("devopts:main")

@scan.stage("collect", requires="devopts:main")
def _(ctx):
    rows = ctx.scroll_collect(lambda: ui.rows(ctx.device.dump()), key=lambda r: r["title"])
    ctx.result["rows"] = rows
    ctx.result["enabled"] = [r["title"] for r in rows if r["checked"]]
```

Why it's shaped this way:
- Deep-link intent instead of Settings → System → Developer options (menu paths differ per manufacturer).
- The hazard list exists because the most prominent element on the page would cut the connection.
- `collect` requires `main`, so if scrolling fails halfway, `resume_from="collect"` works once the user is back on the page.
- Data goes in `ctx.result`, so the agent gets structured rows back instead of parsing logs.
