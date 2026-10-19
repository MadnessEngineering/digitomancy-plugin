"""Digitomancy MCP server — the agent's hands on the phone.

Workflow an agent should follow:
  1. `look` to see the screen as a compact node list (+ screenshot if needed)
  2. act by anchor (`tap_anchor`) when a map has one, else by node/coords
  3. `save_anchor` anything it had to find by hand, so next time is a lookup
  4. prefer `run_routine` for known multi-step flows; they checkpoint and resume
  5. call `release` when done — while uiautomator runs, the phone's
     accessibility services (Tasker, AutoInput…) are suppressed. An idle
     watchdog also releases after 60s without use.
"""

from __future__ import annotations

import io
import threading
import time

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from . import checkpoints, config, maps, routines, tasker, ui
from .device import Device

mcp = FastMCP("digitomancy", instructions=__doc__)

_devices: dict[str, Device] = {}
_last_nodes: dict[str, list[ui.Node]] = {}  # per device, from the last `look`


IDLE_RELEASE = 60.0


def _dev(name: str | None) -> Device:
    spec = config.resolve_device(name)
    if spec.name not in _devices:
        _devices[spec.name] = Device(spec)
    return _devices[spec.name]


def _watchdog() -> None:
    while True:
        time.sleep(10)
        for d in list(_devices.values()):
            if d.connected and time.monotonic() - d.last_used > IDLE_RELEASE:
                try:
                    d.release()
                except Exception:
                    pass


@mcp.tool
def release(device: str | None = None) -> str:
    """Stop uiautomator on the device so Tasker/AutoInput accessibility comes back."""
    return "released" if _dev(device).release() else "was not connected"


@mcp.tool
def devices() -> dict:
    """Registered devices (devices.yaml), the default, and which serials adb sees right now."""
    import subprocess

    specs, default = config.load_devices()
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    online = {line.split()[0] for line in out.splitlines()[1:] if line.strip().endswith("device")}
    return {
        "default": default,
        "devices": {n: {"serial": s.serial, "online": s.serial in online, "notes": s.notes} for n, s in specs.items()},
        "unregistered_online": sorted(online - {s.serial for s in specs.values()}),
    }


@mcp.tool
def look(device: str | None = None, limit: int = 150, everything: bool = False) -> str:
    """Current app + compact UI node list. Lines: #idx class 'text' id=res @(x,y normalized) [tap]."""
    d = _dev(device)
    nodes = ui.parse(d.dump(), d.size, everything=everything)
    _last_nodes[d.name] = nodes
    app = d.current_app()
    return f"device={d.name} size={d.size} app={app.get('package')} activity={app.get('activity')}\n" + ui.render(nodes, limit)


@mcp.tool
def screenshot(device: str | None = None, scale: float = 0.5) -> Image:
    """PNG of the screen (downscaled to save tokens). Use when `look` can't see it (games, canvases)."""
    img = _dev(device).screenshot()
    if scale != 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Image(data=buf.getvalue(), format="png")


@mcp.tool
def tap(x: float, y: float, device: str | None = None) -> str:
    """Tap. Floats in [0,1] are screen fractions (preferred); otherwise pixels."""
    return f"tapped {_dev(device).tap(x, y)}"


@mcp.tool
def tap_node(index: int, device: str | None = None) -> str:
    """Tap node #index from the last `look` on this device."""
    d = _dev(device)
    n = _last_nodes.get(d.name, [])[index]
    return f"tapped #{index} {n.text or n.desc or n.res_id} at {d.tap(*n.center)}"


@mcp.tool
def tap_anchor(ref: str, device: str | None = None, timeout: float = 3.0) -> str:
    """Tap a mapped anchor 'map:name' (selector first, saved point as fallback)."""
    return f"{ref} via {maps.tap_anchor(_dev(device), ref, timeout)}"


@mcp.tool
def swipe(x1: float, y1: float, x2: float, y2: float, duration: float = 0.3, device: str | None = None) -> str:
    """Swipe between two points (fractions or pixels). Scroll down = swipe(0.5,0.75,0.5,0.25)."""
    _dev(device).swipe(x1, y1, x2, y2, duration)
    return "ok"


@mcp.tool
def key(name: str, device: str | None = None) -> str:
    """Press a key: home, back, enter, recent, power, volume_up, volume_down, delete…"""
    _dev(device).key(name)
    return "ok"


@mcp.tool
def type_text(text: str, clear: bool = False, device: str | None = None) -> str:
    """Type into the focused field."""
    _dev(device).type_text(text, clear)
    return "ok"


@mcp.tool
def launch(package: str, stop_first: bool = False, device: str | None = None) -> str:
    """Start an app by package name."""
    _dev(device).launch(package, stop_first)
    return "ok"


@mcp.tool
def check(screen: str, timeout: float = 0.0, device: str | None = None) -> dict:
    """Evaluate a mapped screen 'map:screen' (optionally waiting). Returns ok + per-condition detail."""
    res = checkpoints.wait(_dev(device), maps.screen(screen), timeout)
    return {"ok": res.ok, "elapsed": round(res.elapsed, 2), "detail": res.detail}


@mcp.tool
def list_maps() -> dict:
    """All maps with their anchors and screens."""
    out = {}
    for name in maps.list_maps():
        m = maps.load_map(name)
        out[name] = {"app": m.app, "anchors": list(m.anchors), "screens": list(m.screens)}
    return out


@mcp.tool
def save_anchor(
    map_name: str,
    name: str,
    node: int | None = None,
    x: float | None = None,
    y: float | None = None,
    notes: str = "",
    device: str | None = None,
) -> str:
    """Remember a tap target. From a `look` node (stores selector + point) or raw normalized x,y."""
    d = _dev(device)
    selector, point = None, None
    if node is not None:
        n = _last_nodes.get(d.name, [])[node]
        selector, point = n.selector(), n.center
        app = n.package
    elif x is not None and y is not None:
        point = (x, y)
        app = d.current_app().get("package")
    else:
        return "give node= or x=,y="
    path = maps.save_anchor(map_name, name, selector, point, notes, app=app)
    return f"saved {map_name}:{name} -> {path.name} selector={selector} point={point}"


@mcp.tool
def list_routines() -> list[dict]:
    """Known routines with params and stage names (stages are resume points)."""
    return [r.describe() for r in routines.load_all().values()]


@mcp.tool
def run_routine(name: str, params: dict | None = None, resume_from: str | None = None, device: str | None = None) -> dict:
    """Run a routine. On failure returns the failed stage, snapshot dir, and a resume hint."""
    return routines.run(name, _dev(device), params, resume_from)


@mcp.tool
def tasker_run(task: str, params: dict | None = None, wait_result: float = 0, device: str | None = None) -> dict:
    """Fire a Tasker task via broadcast (needs the DGM Dispatch profile, docs/TASKER.md)."""
    return tasker.run_task(_dev(device), task, params, wait_result)


@mcp.tool
def tasker_lookup(query: str = "", project: str | None = None, limit: int = 25) -> dict:
    """Search the Tasker catalog (built by `dgm catalog`) by task/profile name substring.

    Returns matching tasks with their actions and calls, plus hazard flags.
    Never fire a task marked hazard; tasker_run refuses them anyway.
    """
    import json

    path = config.CATALOG_DIR / "tasker_catalog.json"
    if not path.exists():
        return {"error": "no catalog; run `dgm catalog`"}
    cat = json.loads(path.read_text())
    q = query.lower()
    tasks, profiles = [], []
    for pname, p in cat["projects"].items():
        if project and pname.lower() != project.lower():
            continue
        tasks += [{"project": pname, "on_phone": p["on_phone"], **t} for t in p["tasks"] if t["name"] and q in t["name"].lower()]
        profiles += [{"project": pname, **pr} for pr in p["profiles"] if q in (pr["name"] or "").lower()]
    return {"catalog_generated": cat["generated"], "hazard_tasks": cat["hazard_tasks"],
            "tasks": tasks[:limit], "profiles": profiles[:limit], "truncated": len(tasks) > limit or len(profiles) > limit}


@mcp.tool
def shell(cmd: str, device: str | None = None) -> str:
    """Raw `adb shell` escape hatch."""
    return _dev(device).shell(cmd)


@mcp.tool
def workspace() -> dict:
    """Where devices.yaml, maps/ and routines/ live (created and seeded if missing). Edit devices.yaml there."""
    created = config.ensure_workspace()
    return {
        "home": str(config.HOME),
        "devices_file": str(config.DEVICES_FILE),
        "maps": str(config.MAPS_DIR),
        "routines": str(config.ROUTINES_DIR),
        "runs": str(config.RUNS_DIR),
        "created_now": created,
    }


def main() -> None:
    config.ensure_workspace()
    threading.Thread(target=_watchdog, daemon=True, name="u2-idle-release").start()
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
