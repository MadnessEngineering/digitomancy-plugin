"""Routines: named multi-step flows built from stages.

Each stage is a resumable checkpoint. A stage may declare `requires` — a
screen that must be showing before it runs — so `resume_from` can pick up a
half-finished run without replaying everything (handy when a game ad or a
permission dialog derails step 7 of 9).

    from digitomancy.routines import Routine

    wifi = Routine("settings.wifi", "Open Wi-Fi settings")

    @wifi.stage("open")
    def _(ctx):
        ctx.launch("com.android.settings", stop_first=True)
        ctx.expect("settings:home")

    @wifi.stage("network", requires="settings:home")
    def _(ctx):
        ctx.tap("settings:network")
        ctx.expect("settings:network")

Files in routines/*.py are imported on demand; any Routine they create registers itself.
"""

from __future__ import annotations

import importlib.util
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from . import checkpoints, config, maps, tasker

REGISTRY: dict[str, "Routine"] = {}


@dataclass
class Stage:
    name: str
    fn: Callable
    requires: str | dict | None = None
    takes_params: bool = False  # single-stage @routine fns get params as kwargs


class Routine:
    def __init__(self, name: str, doc: str = "", params: dict[str, str] | None = None):
        self.name, self.doc = name, doc
        self.params = params or {}  # name -> description, for agents
        self.stages: list[Stage] = []
        REGISTRY[name] = self

    def stage(self, name: str, requires: str | dict | None = None):
        def deco(fn):
            self.stages.append(Stage(name, fn, requires))
            return fn

        return deco

    def describe(self) -> dict:
        return {
            "name": self.name,
            "doc": self.doc,
            "params": self.params,
            "stages": [{"name": s.name, "requires": s.requires} for s in self.stages],
        }


def routine(name: str, doc: str = "", params: dict[str, str] | None = None):
    """Single-stage shorthand: decorate a plain fn(ctx, **params)."""

    def deco(fn):
        r = Routine(name, doc or (fn.__doc__ or "").strip(), params)
        r.stages.append(Stage("main", fn, takes_params=True))
        return fn

    return deco


class Ctx:
    """What a stage gets. Every action is logged into the run report."""

    def __init__(self, device, params: dict | None = None):
        self.device = device
        self.params = params or {}
        self.log: list[str] = []
        self.result: dict = {}  # whatever the routine wants to hand back

    def _note(self, msg: str) -> None:
        self.log.append(f"{time.strftime('%H:%M:%S')} {msg}")

    def tap(self, target, timeout: float = 3.0):
        """`"map:anchor"` or `(x, y)` (normalized floats or pixels)."""
        if isinstance(target, str):
            how = maps.tap_anchor(self.device, target, timeout)
            self._note(f"tap {target} via {how}")
        else:
            px = self.device.tap(*target)
            self._note(f"tap {target} -> {px}")

    def expect(self, screen, timeout: float = 10.0):
        res = checkpoints.expect(self.device, screen, timeout)
        self._note(f"checkpoint {screen if isinstance(screen, str) else 'inline'} ok ({res.elapsed:.1f}s)")
        return res

    def check(self, screen, timeout: float = 0.0) -> bool:
        """Non-raising probe — for branches like 'if the ad is up, close it'."""
        spec = maps.screen(screen) if isinstance(screen, str) else screen
        ok = checkpoints.wait(self.device, spec, timeout).ok
        self._note(f"check {screen if isinstance(screen, str) else 'inline'} -> {ok}")
        return ok

    def launch(self, package: str, stop_first: bool = False):
        self.device.launch(package, stop_first)
        self._note(f"launch {package}")

    def key(self, key: str):
        self.device.key(key)
        self._note(f"key {key}")

    def swipe(self, x1, y1, x2, y2, duration: float = 0.3):
        self.device.swipe(x1, y1, x2, y2, duration)
        self._note(f"swipe ({x1},{y1})->({x2},{y2})")

    def type(self, text: str, clear: bool = False):
        self.device.type_text(text, clear)
        self._note(f"type {len(text)} chars")

    def sleep(self, seconds: float):
        self.device.sleep(seconds)
        self._note(f"sleep {seconds}s")

    def intent(self, action: str, extra: str = ""):
        """`am start -a ACTION` — deep-links that skip menu walking."""
        self.device.shell(f"am start -a {action} {extra}".strip())
        self._note(f"intent {action}")

    def scroll_collect(self, collect, max_swipes: int = 25, key=lambda r: repr(r), guard=None) -> list:
        """Swipe up until a page adds nothing new; `collect()` returns a list per page.

        Order is preserved, duplicates (by `key`) dropped. Starts from wherever
        the list currently is — scroll to top first if that matters.
        `guard()` runs after every swipe; falsy aborts (tripwire for gestures
        that open something unexpected — a Tasker scene did exactly that).
        """
        seen, out = set(), []
        for i in range(max_swipes + 1):
            fresh = [r for r in collect() if key(r) not in seen]
            if not fresh and i:
                break
            for r in fresh:
                seen.add(key(r))
                out.append(r)
            self.device.swipe(0.5, 0.75, 0.5, 0.35, 0.25)
            self.device.sleep(0.6)
            if guard and not guard():
                raise RuntimeError(f"scroll_collect tripwire: guard failed after swipe {i + 1}")
        self._note(f"scroll_collect {len(out)} items in {i} swipes")
        return out

    def tasker(self, task: str, **params):
        res = tasker.run_task(self.device, task, params)
        self._note(f"tasker {task}")
        return res


def load_all() -> dict[str, Routine]:
    for path in sorted(config.ROUTINES_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"dgm_routines.{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return REGISTRY


def run(name: str, device, params: dict | None = None, resume_from: str | None = None) -> dict:
    if name not in REGISTRY:
        load_all()
    if name not in REGISTRY:
        raise KeyError(f"no routine '{name}' (have: {', '.join(sorted(REGISTRY))})")
    r = REGISTRY[name]
    names = [s.name for s in r.stages]
    if resume_from and resume_from not in names:
        raise KeyError(f"no stage '{resume_from}' in {name} (stages: {names})")

    ctx = Ctx(device, params)
    report = {"routine": name, "device": device.name, "ok": False, "passed": [], "failed": None, "result": ctx.result, "log": ctx.log}
    started = resume_from is None
    for st in r.stages:
        if not started:
            if st.name != resume_from:
                ctx._note(f"skip stage {st.name} (resuming)")
                continue
            started = True
        ctx._note(f"stage {st.name}")
        try:
            if st.requires:
                ctx.expect(st.requires, timeout=5)
            st.fn(ctx, **ctx.params) if st.takes_params else st.fn(ctx)
        except Exception as e:
            report["failed"] = {
                "stage": st.name,
                "error": str(e),
                "snapshot": str(getattr(e, "snapshot", "") or checkpoints.snapshot(device, f"{name}_{st.name}")),
                "trace": traceback.format_exc(limit=3),
                "resume_hint": f"fix the screen, then run with resume_from='{st.name}'",
            }
            return report
        report["passed"].append(st.name)
    report["ok"] = True
    return report
