"""Workshop paths and the device registry."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml


def _default_home(checkout: Path | None = None) -> Path:
    """$DGM_HOME, else the source checkout (has devices.yaml), else ~/.digitomancy.

    The checkout case keeps the workshop repo self-contained; installed copies
    (the Claude plugin, a pip install) get a per-user workspace instead.
    """
    if os.environ.get("DGM_HOME"):
        return Path(os.environ["DGM_HOME"]).expanduser()
    checkout = checkout or Path(__file__).resolve().parents[2]
    if (checkout / "devices.yaml").exists():
        return checkout
    return Path.home() / ".digitomancy"


HOME = _default_home()
STARTER_DIR = Path(__file__).resolve().parent / "starter"
MAPS_DIR = HOME / "maps"
ROUTINES_DIR = HOME / "routines"
RUNS_DIR = HOME / ".runs"
DEVICES_FILE = HOME / "devices.yaml"
CATALOG_DIR = HOME / "catalog"
# Tasker exports (*.prj.xml + backups/*.xml) for `dgm catalog`. A source checkout
# that sits in a workshop tree looks two levels up for `tasker/`; anyone else
# keeps them in the workspace (or points $DGM_TASKER_ROOT at them).
_IN_CHECKOUT = HOME == Path(__file__).resolve().parents[2]
TASKER_ROOT = Path(
    os.environ.get("DGM_TASKER_ROOT") or (HOME.parents[1] / "tasker" if _IN_CHECKOUT else HOME / "tasker")
).expanduser()


@dataclass(frozen=True)
class DeviceSpec:
    name: str
    serial: str
    connect: bool = False  # network device: needs `adb connect` first
    notes: str = ""


def load_devices(path: Path | None = None) -> tuple[dict[str, DeviceSpec], str | None]:
    path = path or DEVICES_FILE
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    data = data or {}
    specs = {
        name: DeviceSpec(name=name, serial=str(d["serial"]), connect=bool(d.get("connect")), notes=d.get("notes", ""))
        for name, d in (data.get("devices") or {}).items()
    }
    return specs, data.get("default")


def resolve_device(name: str | None = None) -> DeviceSpec:
    """Name → spec. Falls back to $DGM_DEVICE, then devices.yaml default.

    An unknown name is treated as a raw serial so ad-hoc devices still work.
    """
    specs, default = load_devices()
    name = name or os.environ.get("DGM_DEVICE") or default
    if not name:
        raise ValueError("no device given and no default in devices.yaml")
    if name in specs:
        return specs[name]
    return DeviceSpec(name=name, serial=name, connect=":" in name)


DEVICES_TEMPLATE = """\
# Named devices. Pick with `--device NAME`, the MCP `device` arg, or $DGM_DEVICE.
# `adb devices -l` lists serials. Unknown names are used as raw serials.
default: phone
devices:
  phone:
    serial: CHANGE_ME            # USB serial from `adb devices`
    notes: "main phone"
  bluestacks:
    serial: 127.0.0.1:5555       # BlueStacks Settings > Advanced > enable ADB
    connect: true                # `adb connect` before use
"""


def ensure_workspace() -> list[str]:
    """Create the workspace on first use; seed starter maps/routines. Returns what it created.

    Never overwrites: an existing file always wins over a starter.
    """
    created = []
    for d in (MAPS_DIR, ROUTINES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not DEVICES_FILE.exists():
        DEVICES_FILE.write_text(DEVICES_TEMPLATE)
        created.append(str(DEVICES_FILE))
    for sub, dest in (("maps", MAPS_DIR), ("routines", ROUTINES_DIR)):
        for src in sorted((STARTER_DIR / sub).glob("*")):
            if src.suffix in (".yaml", ".py") and not (dest / src.name).exists():
                shutil.copy(src, dest / src.name)
                created.append(str(dest / src.name))
    return created
