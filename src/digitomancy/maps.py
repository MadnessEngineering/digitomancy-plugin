"""Anchor maps: per-app YAML of named tap targets and named screens.

    maps/settings.yaml
    app: com.android.settings
    anchors:
      network:
        selector: {textContains: "Network"}   # tried first
        point: [0.5, 0.31]                    # fallback (normalized)
    screens:
      home: {all: [{app: com.android.settings}, {selector: {text: Settings}}]}

Refs are "map:name" — e.g. `settings:network`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config


class AnchorMissed(RuntimeError):
    pass


@dataclass
class Anchor:
    name: str
    selector: dict | None = None
    point: tuple[float, float] | None = None
    notes: str = ""


@dataclass
class AppMap:
    name: str
    app: str | None
    anchors: dict[str, Anchor] = field(default_factory=dict)
    screens: dict[str, dict] = field(default_factory=dict)
    path: Path | None = None


def _path(name: str) -> Path:
    return config.MAPS_DIR / f"{name}.yaml"


def list_maps() -> list[str]:
    return sorted(p.stem for p in config.MAPS_DIR.glob("*.yaml"))


def load_map(name: str) -> AppMap:
    path = _path(name)
    if not path.exists():
        raise KeyError(f"no map '{name}' (have: {', '.join(list_maps()) or 'none'})")
    data = yaml.safe_load(path.read_text()) or {}
    anchors = {
        k: Anchor(
            name=k,
            selector=v.get("selector"),
            point=tuple(v["point"]) if v.get("point") else None,
            notes=v.get("notes", ""),
        )
        for k, v in (data.get("anchors") or {}).items()
    }
    return AppMap(name=name, app=data.get("app"), anchors=anchors, screens=data.get("screens") or {}, path=path)


def split_ref(ref: str) -> tuple[str, str]:
    if ":" not in ref:
        raise ValueError(f"ref '{ref}' must look like map:name")
    m, n = ref.split(":", 1)
    return m, n


def anchor(ref: str) -> Anchor:
    m, n = split_ref(ref)
    amap = load_map(m)
    if n not in amap.anchors:
        raise KeyError(f"no anchor '{n}' in map '{m}' (have: {', '.join(amap.anchors)})")
    return amap.anchors[n]


def screen(ref: str) -> dict:
    m, n = split_ref(ref)
    amap = load_map(m)
    if n not in amap.screens:
        raise KeyError(f"no screen '{n}' in map '{m}' (have: {', '.join(amap.screens)})")
    return amap.screens[n]


def save_anchor(
    map_name: str,
    name: str,
    selector: dict | None = None,
    point: tuple[float, float] | None = None,
    notes: str = "",
    app: str | None = None,
) -> Path:
    """Upsert an anchor. Note: rewrites the YAML, so hand comments are lost."""
    if not selector and not point:
        raise ValueError("anchor needs a selector or a point")
    path = _path(map_name)
    data = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
    if app and not data.get("app"):
        data["app"] = app
    entry: dict = {}
    if selector:
        entry["selector"] = selector
    if point:
        entry["point"] = [round(float(point[0]), 4), round(float(point[1]), 4)]
    if notes:
        entry["notes"] = notes
    data.setdefault("anchors", {})[name] = entry
    data.setdefault("screens", data.get("screens") or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


def tap_anchor(device, ref: str, timeout: float = 3.0) -> str:
    """Selector first (survives layout shifts), point second. Returns which won."""
    a = anchor(ref)
    if a.selector and device.wait_exists(a.selector, timeout):
        device.click_selector(a.selector)
        return "selector"
    if a.point:
        device.tap(*a.point)
        return "point"
    raise AnchorMissed(f"{ref}: selector {a.selector} not found and no fallback point")
