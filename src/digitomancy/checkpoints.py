"""Checkpoints: assert "we are where we think we are" before acting.

A screen spec is a dict of conditions combined with all/any:

    {all: [{app: com.android.settings}, {selector: {text: "Wi-Fi"}}]}
    {any: [{anchor: "settings:network"}, {image: "settings/wifi_icon.png"}]}
    [{app: ...}, {gone: {text: "Loading"}}]      # bare list = all

Conditions:
    selector: {...}   element exists          gone: {...}   element absent
    app: pkg          foreground package       activity: s  substring of activity
    anchor: map:name  that anchor's selector exists
    image: path       template match vs screenshot (needs `vision` extra);
                      path relative to maps/, optional threshold: 0.0-1.0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, maps


class CheckpointFailed(RuntimeError):
    def __init__(self, name: str, detail: list[str], snapshot: Path | None):
        self.name, self.detail, self.snapshot = name, detail, snapshot
        super().__init__(f"checkpoint '{name}' failed: {'; '.join(detail)}" + (f" (snapshot: {snapshot})" if snapshot else ""))


@dataclass
class CheckResult:
    ok: bool
    elapsed: float
    detail: list[str] = field(default_factory=list)


def _condition(device, cond: dict, app_cache: dict) -> tuple[bool, str]:
    def current():
        if "v" not in app_cache:
            app_cache["v"] = device.current_app()
        return app_cache["v"]

    if "selector" in cond:
        ok = device.exists(cond["selector"])
        return ok, f"selector {cond['selector']} {'present' if ok else 'missing'}"
    if "gone" in cond:
        ok = not device.exists(cond["gone"])
        return ok, f"gone {cond['gone']} {'ok' if ok else 'still present'}"
    if "app" in cond:
        pkg = current().get("package")
        return pkg == cond["app"], f"app {pkg!r} want {cond['app']!r}"
    if "activity" in cond:
        act = current().get("activity") or ""
        return cond["activity"] in act, f"activity {act!r} want ~{cond['activity']!r}"
    if "anchor" in cond:
        a = maps.anchor(cond["anchor"])
        if not a.selector:
            return False, f"anchor {cond['anchor']} has no selector to check"
        ok = device.exists(a.selector)
        return ok, f"anchor {cond['anchor']} {'present' if ok else 'missing'}"
    if "image" in cond:
        score = match_template(device, config.MAPS_DIR / cond["image"])
        want = float(cond.get("threshold", 0.85))
        return score >= want, f"image {cond['image']} score {score:.2f} want ≥{want}"
    return False, f"unknown condition {cond}"


def evaluate(device, spec) -> CheckResult:
    t0 = time.monotonic()
    if isinstance(spec, list):
        spec = {"all": spec}
    mode = "any" if "any" in spec else "all"
    conds = spec.get(mode, [])
    cache: dict = {}
    detail, oks = [], []
    for c in conds:
        ok, why = _condition(device, c, cache)
        oks.append(ok)
        detail.append(("✓ " if ok else "✗ ") + why)
        if mode == "all" and not ok:
            break
        if mode == "any" and ok:
            break
    ok = any(oks) if mode == "any" else (bool(oks) and all(oks))
    return CheckResult(ok=ok, elapsed=time.monotonic() - t0, detail=detail)


def wait(device, spec, timeout: float = 10.0, interval: float = 0.5) -> CheckResult:
    deadline = time.monotonic() + timeout
    t0 = time.monotonic()
    while True:
        res = evaluate(device, spec)
        if res.ok or time.monotonic() >= deadline:
            res.elapsed = time.monotonic() - t0
            return res
        time.sleep(interval)


def snapshot(device, label: str) -> Path:
    """Screenshot + hierarchy into .runs/ — the evidence a failed run leaves behind."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = config.RUNS_DIR / f"{stamp}_{label.replace(':', '_').replace('/', '_')}"
    out.mkdir(parents=True, exist_ok=True)
    try:
        device.screenshot(out / "screen.png")
        (out / "hierarchy.xml").write_text(device.dump())
        (out / "activity.txt").write_text(device.shell("dumpsys activity activities | grep -E '^Display #|Resumed'; true"))
    except Exception as e:  # a dead device shouldn't mask the real failure
        (out / "snapshot_error.txt").write_text(repr(e))
    return out


def expect(device, ref_or_spec, timeout: float = 10.0) -> CheckResult:
    """Wait for a screen; raise CheckpointFailed (with snapshot) if it never shows."""
    name = ref_or_spec if isinstance(ref_or_spec, str) else "inline"
    spec = maps.screen(ref_or_spec) if isinstance(ref_or_spec, str) else ref_or_spec
    res = wait(device, spec, timeout)
    if not res.ok:
        raise CheckpointFailed(name, res.detail, snapshot(device, name))
    return res


def match_template(device, template: Path) -> float:
    try:
        import cv2
        import numpy as np
    except ImportError as e:
        raise RuntimeError("image checkpoints need: uv sync --extra vision") from e
    screen = cv2.cvtColor(np.array(device.screenshot()), cv2.COLOR_RGB2GRAY)
    tmpl = cv2.imread(str(template), cv2.IMREAD_GRAYSCALE)
    if tmpl is None:
        raise FileNotFoundError(template)
    _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED))
    return float(score)
