"""Tasker bridge: fire a Tasker task over adb, optionally wait for its answer.

Phone-side setup (once) — see docs/TASKER.md:
  Profile: Event > System > Intent Received, Action = cc.madness.digitomancy.RUN
  Task "DGM Dispatch": Perform Task %task, Parameter 1 = %par1, Parameter 2 = %par2
  To answer back: Write File Download/digitomancy/%dgm_id.json

Tasker exposes intent extras as lowercase local vars (%task, %par1, %dgm_id…).
"""

from __future__ import annotations

import json
import shlex
import time
import uuid

ACTION = "cc.madness.digitomancy.RUN"
RESULT_DIR = "/sdcard/Download/digitomancy"


def broadcast_cmd(task: str, params: dict | None = None, dgm_id: str | None = None) -> str:
    parts = ["am", "broadcast", "-a", ACTION, "--es", "task", task]
    for k, v in (params or {}).items():
        parts += ["--es", str(k), str(v)]
    if dgm_id:
        parts += ["--es", "dgm_id", dgm_id]
    return " ".join(shlex.quote(p) for p in parts)


class HazardTask(PermissionError):
    pass


def run_task(device, task: str, params: dict | None = None, wait_result: float = 0, allow_hazard: bool = False) -> dict:
    """Fire-and-forget by default; `wait_result` seconds polls for the result file.

    Refuses tasks the catalog marks as hazards (door/unlock control, or
    anything that calls one). Rebuild the catalog with `dgm catalog`.
    """
    from . import config, tasker_catalog

    if not allow_hazard:
        # Name check too: tasks newer than any export aren't catalogued.
        patterns = config.CATALOG_DIR / "hazard_patterns.txt"
        if tasker_catalog.is_hazard_name(task, patterns) or task in tasker_catalog.hazard_tasks(config.CATALOG_DIR / "tasker_catalog.json"):
            raise HazardTask(f"Tasker task '{task}' is a hazard (door/unlock control); refusing")
    dgm_id = uuid.uuid4().hex[:12] if wait_result else None
    out = device.shell(broadcast_cmd(task, params, dgm_id))
    res = {"task": task, "broadcast": out.strip()}
    if not dgm_id:
        return res
    path = f"{RESULT_DIR}/{dgm_id}.json"
    deadline = time.monotonic() + wait_result
    while time.monotonic() < deadline:
        body = device.shell(f"cat {path} 2>/dev/null; true").strip()
        if body:
            device.shell(f"rm -f {path}")
            try:
                res["result"] = json.loads(body)
            except json.JSONDecodeError:
                res["result"] = body
            return res
        time.sleep(0.5)
    res["result"] = None
    res["timeout"] = True
    return res
