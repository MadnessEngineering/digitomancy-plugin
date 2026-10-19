"""Compact UI tree: the hierarchy dump squeezed into agent-sized lines.

A raw uiautomator dump is tens of KB of XML. Agents need: what's on screen,
what's tappable, and where — so each interesting node becomes one line with
a stable index the agent can hand back to `save_anchor`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


@dataclass
class Node:
    index: int
    cls: str
    text: str
    desc: str
    res_id: str
    package: str
    clickable: bool
    bounds: tuple[int, int, int, int]
    center: tuple[float, float]  # normalized

    def selector(self) -> dict:
        """Best stable uiautomator2 selector for this node."""
        if self.res_id:
            sel = {"resourceId": self.res_id}
            if self.text:  # ids repeat in lists; text disambiguates
                sel["text"] = self.text
            return sel
        if self.text:
            return {"text": self.text}
        if self.desc:
            return {"description": self.desc}
        return {"className": self.cls}

    def line(self) -> str:
        label = self.text or self.desc
        rid = self.res_id.split("/")[-1] if self.res_id else ""
        parts = [f"#{self.index}", self.cls.split(".")[-1]]
        if label:
            parts.append(repr(label[:60]))
        if rid:
            parts.append(f"id={rid}")
        parts.append(f"@({self.center[0]:.3f},{self.center[1]:.3f})")
        if self.clickable:
            parts.append("tap")
        return " ".join(parts)


def parse(xml: str, size: tuple[int, int] | None = None, everything: bool = False) -> list[Node]:
    root = ET.fromstring(xml)
    if size is None:
        # root/first node bounds = screen
        first = next((n for n in root.iter("node")), None)
        m = _BOUNDS.match(first.get("bounds", "")) if first is not None else None
        size = (int(m.group(3)), int(m.group(4))) if m else (1080, 2400)
    w, h = size
    nodes: list[Node] = []
    for el in root.iter("node"):
        m = _BOUNDS.match(el.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        if x2 <= x1 or y2 <= y1:
            continue
        text, desc, rid = el.get("text", ""), el.get("content-desc", ""), el.get("resource-id", "")
        clickable = el.get("clickable") == "true" or el.get("long-clickable") == "true"
        if not everything and not (text or desc or (clickable and rid)):
            continue
        nodes.append(
            Node(
                index=len(nodes),
                cls=el.get("class", ""),
                text=text,
                desc=desc,
                res_id=rid,
                package=el.get("package", ""),
                clickable=clickable,
                bounds=(x1, y1, x2, y2),
                center=(round((x1 + x2) / 2 / w, 4), round((y1 + y2) / 2 / h, 4)),
            )
        )
    return nodes


def rows(xml: str) -> list[dict]:
    """Settings-style list rows: {title, summary, checked}.

    A row is a clickable node holding an `…id/title` TextView. `checked` comes
    from the row's checkable descendant (switch/checkbox); None if it has none.
    Works for AOSP/Pixel Settings and most PreferenceScreen apps.
    """
    root = ET.fromstring(xml)
    out = []
    for el in root.iter("node"):
        if el.get("clickable") != "true":
            continue
        title = summary = None
        checked = None
        for sub in el.iter("node"):
            rid = sub.get("resource-id", "")
            if title is None and rid.endswith("id/title"):
                title = sub.get("text", "")
            elif summary is None and rid.endswith("id/summary"):
                summary = sub.get("text", "")
            if sub is not el and sub.get("checkable") == "true":
                checked = sub.get("checked") == "true"
        if el.get("checkable") == "true" and checked is None:
            checked = el.get("checked") == "true"
        if title:
            out.append({"title": title, "summary": summary, "checked": checked})
    return out


def render(nodes: list[Node], limit: int = 150) -> str:
    lines = [n.line() for n in nodes[:limit]]
    if len(nodes) > limit:
        lines.append(f"… {len(nodes) - limit} more (raise limit)")
    return "\n".join(lines)
