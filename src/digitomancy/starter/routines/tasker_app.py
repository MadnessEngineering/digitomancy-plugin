"""Tasker app — read-only scans of what's on the phone. See maps/tasker.yaml hazards."""

import re
import xml.etree.ElementTree as ET

from digitomancy.routines import Routine

PKG = "net.dinglisch.android.taskerm"
_TAB = re.compile(r"/tab_(text|icon)$")


def parse_profiles(xml: str) -> list[dict]:
    """Profile rows in document order: name, enabled, contexts, tasks.

    Collapsed profiles show no contexts/tasks — that's Tasker's view, not ours.
    """
    out, cur = [], None
    for el in ET.fromstring(xml).iter("node"):
        rid = el.get("resource-id", "").rsplit("/", 1)[-1]
        if rid == "profile_name":
            cur = {"name": el.get("text", ""), "enabled": None, "contexts": [], "tasks": []}
            out.append(cur)
        elif cur is None:
            continue
        elif rid == "button_enabled":
            cur["enabled"] = el.get("checked") == "true"
        elif rid.startswith("context_text_"):
            cur["contexts"].append(el.get("text", "").replace("\n", " | "))
        elif rid.startswith("task_text_"):
            cur["tasks"].append(el.get("text", ""))
    return out


def parse_project_tabs(xml: str) -> list[str]:
    return [
        el.get("text") or el.get("content-desc", "")
        for el in ET.fromstring(xml).iter("node")
        if _TAB.search(el.get("resource-id", "")) and el.get("bounds", "").split("][")[0] > "[0,1"  # below entity tabs
        and int(re.findall(r"\d+", el.get("bounds"))[1]) > 1500
    ]


def dismiss_interface_scene(ctx):
    """Back out of any Tasker scene covering the main screen (scenes exit on Back)."""
    for _ in range(2):
        if not ctx.device.current_app().get("activity", "").endswith(".SceneActivity"):
            return
        ctx.key("back")
        ctx.sleep(0.8)


def _open(ctx):
    dismiss_interface_scene(ctx)
    ctx.launch(PKG)
    ctx.sleep(0.8)
    dismiss_interface_scene(ctx)  # never stop_first: force-stopping Tasker kills profile monitoring
    ctx.expect("tasker:main")


projects = Routine("tasker.projects", "List Tasker project tabs (swipes the tab bar, no taps)")


@projects.stage("open")
def _(ctx):
    _open(ctx)


@projects.stage("collect", requires="tasker:main")
def _(ctx):
    names: list[str] = []
    for _ in range(8):
        before = len(names)
        for n in parse_project_tabs(ctx.device.dump()):
            if n not in names:
                names.append(n)
        if len(names) == before and before:
            break
        ctx.swipe(0.85, 0.935, 0.15, 0.935, 0.3)
        ctx.sleep(0.5)
    ctx.result["projects"] = names


profiles = Routine("tasker.profiles", "Read every profile in the currently selected project")


@profiles.stage("open")
def _(ctx):
    _open(ctx)
    if not ctx.check("tasker:profiles"):  # re-tapping the active tab opens a menu
        ctx.tap("tasker:tab_profiles")
    ctx.expect("tasker:profiles")


@profiles.stage("collect", requires="tasker:profiles")
def _(ctx):
    # No pull-to-top: a downward drag can trigger gesture-bound scenes.
    # Collect forward from wherever the list is.
    rows = ctx.scroll_collect(
        lambda: parse_profiles(ctx.device.dump()),
        key=lambda r: r["name"],
        guard=lambda: ctx.device.current_app().get("activity", "").endswith(".Main"),
    )
    ctx.result["profiles"] = rows
    ctx.result["enabled"] = sum(1 for r in rows if r["enabled"])
    ctx.result["count"] = len(rows)
