"""Developer options — read-only scans. Nothing here toggles anything."""

from digitomancy import ui
from digitomancy.routines import Routine

DEV_INTENT = "android.settings.APPLICATION_DEVELOPMENT_SETTINGS"

# settings-provider keys worth knowing for automation, namespace -> keys
SHELL_KEYS = {
    "global": [
        "development_settings_enabled", "adb_enabled", "adb_wifi_enabled", "stay_on_while_plugged_in",
        "window_animation_scale", "transition_animation_scale", "animator_duration_scale",
    ],
    "system": ["show_touches", "pointer_location", "screen_off_timeout", "accelerometer_rotation"],
    "secure": ["enabled_accessibility_services", "default_input_method"],
}

settings_read = Routine("devopts.settings", "Read automation-relevant settings via `settings get` (no UI, instant)")


@settings_read.stage("read")
def _(ctx):
    cmd = "; ".join(f"echo {ns}.{k}=$(settings get {ns} {k})" for ns, keys in SHELL_KEYS.items() for k in keys)
    for line in ctx.device.shell(cmd).splitlines():
        k, _, v = line.partition("=")
        ctx.result[k] = v.split(":") if k.endswith("accessibility_services") and v != "null" else v


scan = Routine("devopts.scan", "Open Developer options and read every row (title/summary/toggle state)")


@scan.stage("open")
def _(ctx):
    ctx.device.stop("com.android.settings")  # fresh page = starts at the top
    ctx.intent(DEV_INTENT)
    ctx.expect("devopts:main")


@scan.stage("collect", requires="devopts:main")
def _(ctx):
    rows = ctx.scroll_collect(lambda: ui.rows(ctx.device.dump()), key=lambda r: r["title"])
    ctx.result["rows"] = rows
    ctx.result["enabled"] = [r["title"] for r in rows if r["checked"]]
    ctx.result["count"] = len(rows)
