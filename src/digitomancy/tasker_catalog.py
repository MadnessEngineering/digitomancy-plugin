"""Tasker catalog: every project/profile/task from exports, merged and made safe.

Sources are Tasker XML: per-project `.prj.xml` exports and full backups
(`backup.xml`). Each project is taken from whichever source holds its newest
edit (max `edate`), so a stale export never shadows a fresher backup.

Output is for agents: what exists, what calls what, and which tasks are
HAZARDS (door/unlock control — never fire from automation). String values are
redacted when they look like secrets; summaries are truncated.

Profile on/off state is NOT in the XML in any way we could decode (`flags`
was identical for an ON and an OFF profile) — merge it from the live UI scan
(`tasker.profiles` routine) instead.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # Tasker writes raw ESC etc.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{10,}|Bearer\s+\S+|AIza[0-9A-Za-z_\-]{20,}|ghp_[A-Za-z0-9]{20,}"
    r"|Basic\s+[A-Za-z0-9+/=]{8,}"
    r"|\b[A-Za-z0-9_\-]{32,}\b|(api[_-]?key|token|secret|passw(or)?d)\s*[:=]"
    r"|[\w.+-]+@[\w-]+\.[\w.]+"  # email
    r"|\+?\d[\d ()-]{8,}\d"  # phone-ish
    r"|-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,})",  # lat,long
    re.I,
)
# URLs collapse to their base host: paths/queries carry IDs and keys, and
# tenant subdomains (acme.slack.com, acme.atlassian.net) name the employer.
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s«»\"'<>]+", re.I)
_IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}$")
# Bare addresses (MQTT brokers, SSH hosts, code snippets) with optional :port.
_BARE_IP = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?::\d{1,5})?(?![\w.])")
_HOST_TOKEN = re.compile(r"\[(?:url [^\]]*|ip|lan)\]")
_VARREF = re.compile(r"%+(\w+)(\(\w*\))?")
# Variable names whose VALUE is secret. Checked per action: in
# "Variable Set %WifiPass hunter2" neither argument looks secret on its own.
_SECRET_NAME = re.compile(r"pass|pwd|token|secret|api_?key|auth|cred|otp|cookie|session|priv(ate)?_?key|(^|_)pin($|_)", re.I)
_site: re.Pattern | None = None  # site-specific redactions, set by build() from redact_patterns.txt

HAZARD_WORDS = r"doors?|unlock\w*|butterfly\w*|backdoor|garage|gates?"
HAZARD = re.compile(rf"\b({HAZARD_WORDS})\b", re.I)


def hazard_re(patterns_file: Path | None = None) -> re.Pattern:
    """HAZARD plus site-specific patterns from `hazard_patterns.txt` (one regex per line, # comments).

    Keeps personal place/device names out of the code: e.g. a line `warehouse`
    makes `open-warehouse-lot` a hazard by name.
    """
    extra = manual_hazards(patterns_file) if patterns_file else []
    if not extra:
        return HAZARD
    return re.compile(rf"\b({'|'.join([HAZARD_WORDS, *extra])})\b", re.I)

# Best-known Tasker action codes. Unknown codes render as `code:N`; the
# label / first args usually say enough. Extend as codes get confirmed.
ACTIONS = {
    20: "Launch App", 30: "Wait", 37: "If", 38: "End If", 39: "For", 40: "End For", 43: "Else",
    46: "Create Scene", 47: "Show Scene", 48: "Hide Scene", 49: "Destroy Scene",
    123: "Run Shell", 126: "Return", 130: "Perform Task", 135: "Goto", 137: "Stop",
    339: "HTTP Request", 523: "Notify", 547: "Variable Set", 548: "Flash", 549: "Variable Clear",
    590: "Variable Split",
}
CONTEXTS = {("State", 165): "Variable Value", ("Event", 3001): "Shake", ("Event", 2076): "NFC Tag"}


def load_xml(path: Path) -> ET.Element:
    return ET.fromstring(_BAD_XML.sub("", path.read_text(encoding="utf-8", errors="replace")))


def _ip_kind(ip: str) -> str | None:
    m = _IPV4.match(ip)
    if not m or any(int(x) > 255 for x in ip.split(".")):
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return "lan" if a in (10, 127) or (a, b) == (192, 168) or (a == 172 and 16 <= b <= 31) else "ip"


def url_host(url: str) -> str:
    """`https://acme.slack.com/x?k=v` -> `slack.com`; private IPs -> `lan`, public -> `ip`."""
    m = re.match(r"[a-z][a-z0-9+.-]*://(?:[^@/\s]*@)?([^/:?#\s…]+)", url, re.I)
    host = (m.group(1) if m else "").lower().rstrip(".")
    kind = _ip_kind(host)
    if kind:
        return kind
    parts = [x for x in host.split(".") if x]
    if len(parts) <= 2:
        return host or "?"
    keep = 3 if len(parts[-1]) == 2 and parts[-2] in ("co", "com", "net", "org", "ac", "gov", "edu") else 2
    return ".".join(parts[-keep:])


def site_re(path: Path | None) -> re.Pattern | None:
    """Site-specific redactions (one regex per line, # comments): employer names, places…"""
    lines = manual_hazards(path) if path else []
    return re.compile("|".join(f"(?:{x})" for x in lines), re.I) if lines else None


def is_secret_var(name: str) -> bool:
    return bool(_SECRET_NAME.search(name.lstrip("%")))


def _has_literal(s: str) -> bool:
    """True if `s` holds text beyond %variable references (i.e. a value worth hiding)."""
    return bool(re.search(r"[A-Za-z0-9]", _VARREF.sub("", s)))


def _sensitive(*texts: str) -> bool:
    return any(is_secret_var(m.group(1)) for t in texts if t for m in _VARREF.finditer(t))


def clean(s: str | None, n: int = 80) -> str:
    if not s:
        return ""
    s = " ".join(s.split())
    s = _URL.sub(lambda m: f"[url {url_host(m.group(0))}]", s)
    s = _BARE_IP.sub(lambda m: f"[{_ip_kind(m.group(1))}]" if _ip_kind(m.group(1)) else m.group(0), s)
    if _site is not None:
        s = _site.sub("[redacted]", s)
    if _SECRET.search(s):
        return "[redacted]"
    return s if len(s) <= n else s[: n - 1] + "…"


def _blurb_raw(el: ET.Element) -> str:
    for sub in el.iter():
        if sub.tag.endswith("BLURB") and sub.text:
            return sub.text
    return ""


def _blurb(el: ET.Element) -> str:
    return clean(_blurb_raw(el))


def _strs(el: ET.Element, k: int = 2, sensitive: bool = False, keep_first: bool = False) -> list[str]:
    """First `k` non-empty string args, cleaned. In a `sensitive` action (one that
    touches a secret-named variable) any arg with literal text is redacted whole;
    `keep_first` spares arg 0 (Perform Task's target is a task name, not a value)."""
    out = []
    for i, s in enumerate(x for x in el.findall("Str") if x.text and x.text.strip()):
        if i == k:
            break
        # a collapsed URL/IP can't carry the value, so it may stay visible
        hide = sensitive and _has_literal(_HOST_TOKEN.sub("", clean(s.text, 10**6))) and not (keep_first and i == 0)
        out.append("[redacted]" if hide else clean(s.text, 50))
    return out


def _ids(text: str | None) -> list[int]:
    return [int(x) for x in (text or "").split(",") if x.strip().isdigit()]


@dataclass
class Task:
    id: int
    name: str | None
    actions: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)  # Perform Task targets (by name)
    text: str = ""  # everything searchable, for hazard detection
    edate: int = 0
    hazard: bool = False
    hazard_reason: str = ""


def parse_task(t: ET.Element) -> Task:
    task = Task(id=int(t.findtext("id") or -1), name=t.findtext("nme"), edate=int(t.findtext("edate") or 0))
    raw = [task.name or ""]
    for a in t.findall("Action"):
        code = int(a.findtext("code") or -1)
        strs = [s.text or "" for s in a.findall("Str")]
        sensitive = _sensitive(a.findtext("label") or "", _blurb_raw(a), *strs)
        label = clean(a.findtext("label"), 60)
        blurb = "" if sensitive else _blurb(a)  # free-text summary may spell out the value
        args = _strs(a, sensitive=sensitive, keep_first=code == 130)
        name = ACTIONS.get(code, f"code:{code}")
        if code == 130:
            # raw target, not the display arg: redaction/truncation must not break the hazard graph
            target = next((x.strip() for x in strs if x and x.strip()), "")
            if target:
                task.calls.append(target)
        bits = [name] + ([f"«{label}»"] if label else []) + ([blurb] if blurb else args)
        task.actions.append(" ".join(b for b in bits if b))
        if code == 130:
            strs = strs[1:]  # call target is judged via `calls`, for a precise reason
        raw += [label, blurb, *strs]
    task.text = " ".join(r for r in raw if r)
    return task


def parse_context(c: ET.Element) -> str:
    code = c.findtext("code")
    name = CONTEXTS.get((c.tag, int(code))) if code and code.lstrip("-").isdigit() else None
    if c.tag in ("Time", "Day", "App", "Loc"):
        name = c.tag
    strs = [s.text or "" for s in c.findall("Str")]
    sensitive = _sensitive(_blurb_raw(c), *strs)
    bits = [name or f"{c.tag}:{code}", ("" if sensitive else _blurb(c)) or " ".join(_strs(c, sensitive=sensitive))]
    return " ".join(b for b in bits if b)


def parse_source(path: Path) -> dict:
    """One file -> {project_name: {...}} plus orphan tasks."""
    root = load_xml(path)
    tasks = {t.id: t for t in (parse_task(x) for x in root.findall("Task"))}
    profiles = {}
    for p in root.findall("Profile"):
        pid = int(p.findtext("id") or -1)
        profiles[pid] = {
            "id": pid,
            "name": p.findtext("nme"),
            "contexts": [parse_context(c) for c in p if c.tag in ("Event", "State", "Time", "Day", "App", "Loc")],
            "enter": int(p.findtext("mid0")) if p.findtext("mid0") else None,
            "exit": int(p.findtext("mid1")) if p.findtext("mid1") else None,
            "edate": int(p.findtext("edate") or 0),
        }
    scenes = {s.findtext("nme"): int(s.findtext("edate") or 0) for s in root.findall("Scene")}
    out = {}
    full_backup = len(root.findall("Project")) > 1  # per-project exports hold exactly one
    for pr in root.findall("Project"):
        pname = pr.findtext("name")
        if not pname:
            continue
        pp = [profiles[i] for i in _ids(pr.findtext("pids")) if i in profiles]
        # anonymous profile tasks aren't in `tids`; pull them in via mid0/mid1
        tids = _ids(pr.findtext("tids")) + [i for p in pp for i in (p["enter"], p["exit"]) if i]
        pt = [tasks[i] for i in dict.fromkeys(tids) if i in tasks]
        ps = [s for s in (pr.findtext("scenes") or "").split(",") if s]
        newest = max([t.edate for t in pt] + [p["edate"] for p in pp] + [scenes.get(s, 0) for s in ps] + [0])
        out[pname] = {"tasks": pt, "profiles": pp, "scenes": ps, "newest": newest,
                      "source": str(path), "tasker": root.get("tv"), "full_backup": full_backup}
    return out


def manual_hazards(path: Path) -> list[str]:
    """Hazard task names seen live but not (yet) in any export. One per line, # comments."""
    if not path.exists():
        return []
    return [ln.split("#", 1)[0].strip() for ln in path.read_text().splitlines() if ln.split("#", 1)[0].strip()]


def is_hazard_name(name: str, patterns_file: Path | None = None) -> bool:
    return bool(hazard_re(patterns_file).search(name))


def build(
    paths: list[Path],
    manual: list[str] | None = None,
    patterns_file: Path | None = None,
    redact_file: Path | None = None,
) -> dict:
    """Merge sources into the catalog. `redact_file`: site-specific redaction regexes."""
    global _site
    prev, _site = _site, site_re(redact_file)
    try:
        return _build(paths, manual, patterns_file)
    finally:
        _site = prev


def _build(paths: list[Path], manual: list[str] | None, patterns_file: Path | None) -> dict:
    rx = hazard_re(patterns_file)
    best: dict[str, dict] = {}
    on_phone: set[str] = set()  # projects present in any full backup = installed
    for path in paths:
        try:
            projects = parse_source(path)
        except ET.ParseError as e:
            print(f"skip {path}: {e}")
            continue
        for name, proj in projects.items():
            if proj["full_backup"]:
                on_phone.add(name)
            if name not in best or proj["newest"] > best[name]["newest"]:
                best[name] = proj

    # Hazards: direct keyword hits, then anything that (transitively) calls one.
    by_name: dict[str, Task] = {}
    for proj in best.values():
        for t in proj["tasks"]:
            m = rx.search(t.text)
            t.hazard, t.hazard_reason = bool(m), (f"mentions '{m.group(0)}'" if m else "")
            if t.name:
                by_name.setdefault(t.name, t)
    changed = True
    while changed:
        changed = False
        for t in by_name.values():
            # catalogued hazard, or an uncatalogued target whose name is a hazard
            bad = next((c for c in t.calls if (by_name.get(c) and by_name[c].hazard) or (c not in by_name and is_hazard_name(c))), None)
            if not t.hazard and bad:
                t.hazard, t.hazard_reason, changed = True, f"calls hazard '{bad}'", True

    now_ms = time.time() * 1000
    catalog = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "projects": {}, "hazard_tasks": [], "callable": []}
    for name, proj in sorted(best.items()):
        tasks_by_id = {t.id: t for t in proj["tasks"]}

        def tname(i):
            t = tasks_by_id.get(i)
            return (t.name or f"anon#{i}") if t else (f"#{i}" if i else None)

        catalog["projects"][name] = {
            # False = only in a per-project export: archived/legacy, or exported
            # after the newest backup. Its tasks may not exist on the phone.
            "on_phone": name in on_phone if on_phone else None,
            "source": proj["source"],
            "tasker": proj["tasker"],
            "newest_edit": time.strftime("%Y-%m-%d", time.localtime(proj["newest"] / 1000)) if proj["newest"] else None,
            "age_days": round((now_ms - proj["newest"]) / 86_400_000) if proj["newest"] else None,
            "scenes": proj["scenes"],
            "profiles": [
                {"name": p["name"] or " + ".join(p["contexts"])[:60], "contexts": p["contexts"],
                 "enter": tname(p["enter"]), "exit": tname(p["exit"]),
                 "hazard": any(tasks_by_id.get(i) and tasks_by_id[i].hazard for i in (p["enter"], p["exit"]))}
                for p in proj["profiles"]
            ],
            "tasks": [
                {"id": t.id, "name": t.name, "hazard": t.hazard, "hazard_reason": t.hazard_reason,
                 "calls": t.calls, "actions": t.actions}
                for t in proj["tasks"]
            ],
        }
        for t in proj["tasks"]:
            if t.name and t.hazard:
                catalog["hazard_tasks"].append(t.name)
            elif t.name and (name in on_phone or not on_phone):
                catalog["callable"].append(t.name)
    catalog["manual_hazards"] = sorted(set(manual or []))
    catalog["hazard_tasks"] = sorted(set(catalog["hazard_tasks"]) | set(manual or []))
    catalog["callable"] = sorted(set(catalog["callable"]))
    return catalog


def markdown(catalog: dict) -> str:
    lines = [f"# Tasker catalog\n\nGenerated {catalog['generated']} by `dgm catalog`. Do not edit by hand.\n",
             "Projects marked *export only* are not in the newest full backup (archived, or newer than it). "
             "Task names repeat across projects because Tasker bundles referenced tasks into each export.\n",
             "**Hazard tasks (never fire):** " + (", ".join(f"`{h}`" for h in catalog["hazard_tasks"]) or "none") + "\n",
             "| Project | Profiles | Tasks | Newest edit | Source |", "|---|---|---|---|---|"]
    for name, p in catalog["projects"].items():
        where = "" if p["on_phone"] in (True, None) else " *export only*"
        lines.append(f"| {name}{where} | {len(p['profiles'])} | {len(p['tasks'])} | {p['newest_edit']} | `{Path(p['source']).name}` (Tasker {p['tasker']}) |")
    for name, p in catalog["projects"].items():
        lines.append(f"\n## {name}\n")
        if p["scenes"]:
            lines.append("Scenes: " + ", ".join(p["scenes"]) + "\n")
        for pr in p["profiles"]:
            flag = " ⚠️" if pr["hazard"] else ""
            lines.append(f"- **{pr['name']}**{flag}: {' + '.join(pr['contexts']) or '—'} → `{pr['enter']}`"
                         + (f" / exit `{pr['exit']}`" if pr["exit"] else ""))
        named = [t for t in p["tasks"] if t["name"]]
        if named:
            lines.append("\n| Task | Actions | Calls |\n|---|---|---|")
            for t in named:
                flag = "⚠️ " if t["hazard"] else ""
                why = f" ({t['hazard_reason']})" if t["hazard"] else ""
                lines.append(f"| {flag}`{t['name']}`{why} | {len(t['actions'])} | {', '.join(t['calls'][:5])} |")
    return "\n".join(lines) + "\n"


def default_sources(tasker_root: Path) -> list[Path]:
    return sorted(tasker_root.glob("*/*.prj.xml")) + sorted(tasker_root.glob("backups/*.xml"))


def write(catalog: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j, m = out_dir / "tasker_catalog.json", out_dir / "TASKER_CATALOG.md"
    j.write_text(json.dumps(catalog, indent=1, ensure_ascii=False))
    m.write_text(markdown(catalog))
    return j, m


def hazard_tasks(path: Path) -> set[str]:
    try:
        found = set(json.loads(path.read_text())["hazard_tasks"])
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        found = set()
    return found | set(manual_hazards(path.parent / "hazards_manual.txt"))
