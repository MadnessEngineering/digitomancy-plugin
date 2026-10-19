#!/usr/bin/env python3
"""Summarize a Tasker backup (userbackup.xml / backup.xml / *.prj.xml).

Usage:
  tasker_backup.py BACKUP.xml                 summary
  tasker_backup.py BACKUP.xml --code 18       tasks using action code 18
  tasker_backup.py BACKUP.xml --action wifi   tasks using actions whose name contains "wifi"
  tasker_backup.py BACKUP.xml --codes FILE    load a fuller code table: lines like "`18`: `Kill App`"
                                              (format of Taskomater/Tasker-XML-Info Tasker_XML_Codes.md)

Tasker backup XML is not well-formed, so this parses with regex.
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import re
import sys
from pathlib import Path

# Built-in action names: generated from Taskomater/Tasker-XML-Info (MIT), Tasker 5.15.5.
# Actions added after that version show up as "unknown built-in"; --codes adds more.
CODES: dict[str, str] = json.loads((Path(__file__).with_name("action_codes.json")).read_text())["actions"]

# Actions that need more than Tasker's default permissions. Only what's documented:
# Tasker 6.3 changelog says Wifi, Bluetooth and Kill App use device owner when available.
PRIVILEGED = {
    "18": "uses device owner if available; else root or ADB Wifi",
    "425": "uses device owner if available; else Tasker Settings, root or ADB Wifi",
    "294": "uses device owner if available; else Tasker Settings, root or ADB Wifi",
    "235": "WRITE_SECURE_SETTINGS for secure/global settings",
    "333": "elevated (varies by Android version)",
    "433": "elevated (varies by Android version)",
    "59": "elevated (root, or use the Device Admin/Owner action)",
    "113": "elevated (varies by Android version)",
    "114": "elevated (varies by Android version)",
    "15": "device admin",
    "150": "device admin (varies by Android version)",
}

_TASK = re.compile(r"<Task sr=\"[^\"]*\">(.*?)</Task>", re.S)
_ACTION = re.compile(r"<Action sr=\"act\d+\"\s*ve=\"\d+\">(.*?)</Action>", re.S)


def load_codes(path: str) -> None:
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.match(r"`(\d+)`: `(.+?)`", line.strip())
        if m:
            CODES.setdefault(m.group(1), m.group(2))  # actions are listed first in that file


def name_of(code: str) -> str:
    if code in CODES:
        return CODES[code]
    return "plugin action" if len(code) > 5 else "unknown built-in"


def scan(xml: str):
    use = collections.defaultdict(set)
    total = 0
    for t in _TASK.findall(xml):
        nm = re.search(r"<nme>(.*?)</nme>", t)
        tid = re.search(r"<id>(\d+)</id>", t)
        name = html.unescape(nm.group(1)) if nm else f"(unnamed #{tid.group(1) if tid else '?'})"
        for a in _ACTION.findall(t):
            codes = re.findall(r"<code>(\d+)</code>", a)
            if codes:
                use[codes[-1]].add(name)
                total += 1
    return use, total


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("backup")
    p.add_argument("--code")
    p.add_argument("--action")
    p.add_argument("--codes")
    a = p.parse_args()
    if a.codes:
        load_codes(a.codes)
    xml = open(a.backup, encoding="utf-8", errors="ignore").read()
    use, total = scan(xml)

    if a.code or a.action:
        wanted = [a.code] if a.code else [c for c in use if a.action.lower() in name_of(c).lower()]
        for c in wanted:
            print(f"{c} {name_of(c)}: {len(use.get(c, ()))} tasks")
            for t in sorted(use.get(c, ())):
                print(f"  {t}")
        return 0

    print(f"projects {xml.count('<Project ')}  profiles {xml.count('<Profile ')}  "
          f"tasks {xml.count('<Task ')}  actions {total}")
    print("\nMost used actions:")
    for c, tasks in sorted(use.items(), key=lambda kv: -len(kv[1]))[:20]:
        print(f"  {len(tasks):4} tasks  {c:>10}  {name_of(c)}")
    print("\nPrivileged actions:")
    for c, why in PRIVILEGED.items():
        if c in use:
            names = sorted(use[c])
            more = f" (+{len(names) - 8} more)" if len(names) > 8 else ""
            print(f"  {name_of(c)} [{why}]: {len(names)} tasks: {', '.join(names[:8])}{more}")
    unknown = sorted((c for c in use if c not in CODES and len(c) <= 5), key=int)
    if unknown:
        print("\nUnknown built-in codes (newer actions; identify in the Tasker UI):")
        for c in unknown:
            print(f"  {c}: {', '.join(sorted(use[c])[:6])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
