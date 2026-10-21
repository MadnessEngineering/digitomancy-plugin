"""`dgm` — the bench-side CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

from . import config


_opened: list = []


def _device(args):
    from .device import Device

    d = Device.named(args.device)
    _opened.append(d)
    return d


def cmd_doctor(args) -> int:
    ok = True
    for tool in ("adb", "scrcpy"):
        path = shutil.which(tool)
        print(f"{'✓' if path else '✗'} {tool}: {path or 'missing (brew install ' + ('android-platform-tools' if tool == 'adb' else 'scrcpy') + ')'}")
        ok &= bool(path) or tool == "scrcpy"
    specs, default = config.load_devices()
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout if shutil.which("adb") else ""
    online = {line.split()[0] for line in out.splitlines()[1:] if line.strip().endswith("device")}
    print(f"devices.yaml: {config.DEVICES_FILE} (default: {default})")
    for n, s in specs.items():
        print(f"  {'●' if s.serial in online else '○'} {n:14} {s.serial}{'  (adb connect)' if s.connect else ''}")
    for extra in sorted(online - {s.serial for s in specs.values()}):
        print(f"  ● {'(unregistered)':14} {extra}")
    print(f"maps: {config.MAPS_DIR}  routines: {config.ROUTINES_DIR}")
    return 0 if ok else 1


def cmd_connect(args) -> int:
    spec = config.resolve_device(args.device)
    return subprocess.call(["adb", "connect", spec.serial])


def cmd_look(args) -> int:
    from . import ui

    d = _device(args)
    print(d.current_app())
    print(ui.render(ui.parse(d.dump(), d.size, everything=args.all), args.limit))
    return 0


def cmd_tap(args) -> int:
    from . import maps

    d = _device(args)
    if ":" in args.target:
        print(maps.tap_anchor(d, args.target))
    else:
        x, y = (float(v) if "." in v else int(v) for v in args.target.split(","))
        print(d.tap(x, y))
    return 0


def cmd_check(args) -> int:
    from . import checkpoints, maps

    res = checkpoints.wait(_device(args), maps.screen(args.screen), args.timeout)
    print("\n".join(res.detail))
    return 0 if res.ok else 1


def cmd_routines(args) -> int:
    from . import routines

    for r in routines.load_all().values():
        d = r.describe()
        print(f"{d['name']:28} {d['doc']}  stages={[s['name'] for s in d['stages']]}")
    return 0


def cmd_run(args) -> int:
    from . import routines

    params = dict(p.split("=", 1) for p in args.param)
    report = routines.run(args.name, _device(args), params, args.resume_from)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def cmd_tasker(args) -> int:
    from . import tasker

    params = dict(p.split("=", 1) for p in args.param)
    print(json.dumps(tasker.run_task(_device(args), args.task, params, args.wait), indent=2))
    return 0


def cmd_catalog(args) -> int:
    from pathlib import Path

    from . import tasker_catalog

    sources = [Path(x) for x in args.sources] or tasker_catalog.default_sources(config.TASKER_ROOT)
    cat = tasker_catalog.build(
        sources,
        tasker_catalog.manual_hazards(config.CATALOG_DIR / "hazards_manual.txt"),
        config.CATALOG_DIR / "hazard_patterns.txt",
        config.CATALOG_DIR / "redact_patterns.txt",
    )
    j, m = tasker_catalog.write(cat, config.CATALOG_DIR)
    for name, p in cat["projects"].items():
        print(f"  {name:22} {len(p['profiles']):3} profiles {len(p['tasks']):4} tasks  newest {p['newest_edit']}  <- {Path(p['source']).name}")
    print(f"{len(cat['projects'])} projects, {len(cat['callable'])} callable named tasks, {len(cat['hazard_tasks'])} hazards")
    print(f"wrote {j} and {m}")
    return 0


def cmd_mirror(args) -> int:
    """scrcpy window for watching the agent work. Extra args pass through."""
    spec = config.resolve_device(args.device)
    if spec.connect:
        subprocess.run(["adb", "connect", spec.serial], capture_output=True)
    return subprocess.call(["scrcpy", "-s", spec.serial, "--window-title", f"dgm:{spec.name}", *args.extra])


def cmd_mcp(args) -> int:
    from .mcp_server import main as serve

    serve()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgm", description="Digitomancy — divination by fingers")
    p.add_argument("-d", "--device", help="name from devices.yaml or a raw serial (default: $DGM_DEVICE / yaml default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check tools and which devices are online").set_defaults(fn=cmd_doctor)
    sub.add_parser("connect", help="adb connect a network device (BlueStacks)").set_defaults(fn=cmd_connect)
    s = sub.add_parser("look", help="compact UI tree")
    s.add_argument("--all", action="store_true")
    s.add_argument("--limit", type=int, default=200)
    s.set_defaults(fn=cmd_look)
    s = sub.add_parser("tap", help="tap map:anchor, or x,y (0.5,0.3 fractions / 540,800 pixels)")
    s.add_argument("target")
    s.set_defaults(fn=cmd_tap)
    s = sub.add_parser("check", help="evaluate a map:screen checkpoint")
    s.add_argument("screen")
    s.add_argument("-t", "--timeout", type=float, default=0)
    s.set_defaults(fn=cmd_check)
    sub.add_parser("routines", help="list routines").set_defaults(fn=cmd_routines)
    s = sub.add_parser("run", help="run a routine")
    s.add_argument("name")
    s.add_argument("-p", "--param", action="append", default=[], help="key=value")
    s.add_argument("--resume-from")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("tasker", help="fire a Tasker task via broadcast")
    s.add_argument("task")
    s.add_argument("-p", "--param", action="append", default=[], help="key=value")
    s.add_argument("-w", "--wait", type=float, default=0, help="seconds to wait for a result file")
    s.set_defaults(fn=cmd_tasker)
    s = sub.add_parser("catalog", help="build catalog/ from Tasker exports + backups (default: $DGM_TASKER_ROOT)")
    s.add_argument("sources", nargs="*")
    s.set_defaults(fn=cmd_catalog)
    s = sub.add_parser("mirror", help="open scrcpy on the device")
    s.add_argument("extra", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_mirror)
    sub.add_parser("mcp", help="run the MCP server (stdio)").set_defaults(fn=cmd_mcp)

    args = p.parse_args(argv)
    for path in config.ensure_workspace():
        print(f"created {path}", file=sys.stderr)
    try:
        return args.fn(args)
    finally:
        # uiautomator suppresses Tasker/AutoInput accessibility while alive
        for d in _opened:
            d.release()


if __name__ == "__main__":
    sys.exit(main())
