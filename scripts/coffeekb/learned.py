"""Layouts the chat teaches the engine, stored as data (never as code).

When a screen is not recognized and the chat has read it, the chat can describe the layout in inbox/layout-paste.md:

    LAYOUT | campaign settings
    MATCH | MARKETING CAMPAIGNS
    SAMPLE | IMG_8817.PNG
    FIELD | free_wifi_price | Free WIFI | below | money | USD per week | $300

MATCH lines must all appear on a screen for the rule to apply. FIELD reads the nearest value of a type (money, number,
percent, onoff, text) to the right of, below or above an anchor label. The last column is the value the chat read by eye.
`learn-layout` saves the rule only if, run on the SAMPLE screen text, it reproduces every expected value and it does
not match any screen an existing parser already recognizes. The rule file is core/learned-layouts.json (git-tracked).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .screens_core import Doc, Line, Parsed, is_money, row
from .util import atomic_write, note_problem, today

RULES_FILE = "core/learned-layouts.json"
PASTE = "inbox/layout-paste.md"
TYPES = ("money", "number", "percent", "onoff", "text")
DIRS = ("right", "below", "above")
RULES: list = []


def load(v: Path) -> list:
    """Load the learned rules into the module-level list the classifier reads."""
    RULES.clear()
    p = v / RULES_FILE
    if p.exists():
        try:
            RULES.extend(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            note_problem(__name__, e)
    return RULES


def doc_from_text(path: Path) -> Doc:
    """Rebuild a screen from an archived text dump (y x height confidence text)."""
    lines, w, h = [], 0, 0
    for ln in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"#\s*\S+\s+(\d+)x(\d+)", ln)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            continue
        m = re.match(r"\s*(\d+)\s+(\d+)\s+h\s*(\d+)\s+([\d.]+)\s+(.*)$", ln)
        if m:
            y, x, hh, c, t = m.groups()
            lines.append(Line(t.strip(), float(c), float(x), float(y), 100.0, float(hh)))
    return Doc(path.name.replace(".txt", ""), w, h, lines, [])


def _of_type(l: Line, typ: str) -> bool:
    t = l.t.strip()
    if typ == "money":
        return is_money(t)
    if typ == "number":
        return bool(re.fullmatch(r"[\d,]+(\.\d+)?", t))
    if typ == "percent":
        return bool(re.fullmatch(r"-?\d+(\.\d+)?%", t))
    if typ == "onoff":
        return t.lower() in ("on", "off")
    return bool(re.search(r"[A-Za-z]{2}", t))


def read_field(d: Doc, anchor: str, direction: str, typ: str):
    a = next((l for l in d.lines if l.t.strip().lower() == anchor.strip().lower()), None)
    if a is None:
        return None
    if direction == "right":
        c = [l for l in d.lines if l is not a and _of_type(l, typ) and abs(l.cy - a.cy) <= max(40, a.h) and l.x > a.x]
        return min(c, key=lambda l: l.x - a.x, default=None)
    below = direction == "below"
    c = [l for l in d.lines if l is not a and _of_type(l, typ) and abs(l.cx - a.cx) <= 300
         and ((0 < l.y - a.y <= 250) if below else (0 < a.y - l.y <= 250))]
    return min(c, key=lambda l: abs(l.y - a.y), default=None)


def matches(d: Doc, rule: dict) -> bool:
    texts = [l.t.lower() for l in d.lines]
    return all(any(m.lower() in t for t in texts) for m in rule.get("match", [])) and bool(rule.get("match"))


def find_rule(d: Doc):
    return next((r for r in RULES if matches(d, r)), None)


def parse_learned(d: Doc) -> Parsed:
    rule = find_rule(d)
    p = Parsed("learned")
    if rule is None:
        p.flags.append(f"{d.file}: no learned layout applies")
        p.kind = "other"
        return p
    for f in rule["fields"]:
        hit = read_field(d, f["anchor"], f["dir"], f["type"])
        if hit is None:
            p.flags.append(f"{d.file.split('/')[-1]}: learned layout '{rule['name']}' could not find {f['name']} (next to '{f['anchor']}')")
            continue
        p.rows.append(row(d.file, f["name"], hit.t, f.get("unit", ""), hit.c))
    return p


def parse_paste(text: str) -> dict:
    rule = {"name": "", "match": [], "samples": [], "fields": [], "expect": {}}
    for ln in text.splitlines():
        parts = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(parts) < 2 or ln.lstrip().startswith("#"):
            continue
        key = parts[0].upper()
        if key == "LAYOUT":
            rule["name"] = parts[1]
        elif key == "MATCH":
            rule["match"].append(parts[1])
        elif key == "SAMPLE":
            rule["samples"].append(parts[1])
        elif key == "FIELD" and len(parts) >= 5:
            name = re.sub(r"[^a-z0-9_]+", "_", parts[1].lower()).strip("_")
            rule["fields"].append({"name": name, "anchor": parts[2], "dir": parts[3].lower(), "type": parts[4].lower(),
                                   "unit": parts[5] if len(parts) > 5 else ""})
            if len(parts) > 6 and parts[6]:
                rule["expect"][name] = parts[6]
    return rule


def _sample_path(v: Path, name: str):
    base = name if name.endswith(".txt") else name + ".txt"
    for d in [v / "raw" / "ocr" / "screens", *sorted((v / "raw" / "ocr").glob("2*"), reverse=True)]:
        for cand in (d / base, d / (name.replace(" ", "_") + ".txt")):
            if cand.exists():
                return cand
    return None


def learn(v: Path) -> tuple:
    """Validate the rule in inbox/layout-paste.md and save it. Returns (ok, message)."""
    from . import screens
    src = v / PASTE
    if not src.exists() or not src.read_text(encoding="utf-8").strip():
        return False, "inbox/layout-paste.md is empty. See .agents/skills/coffee-week/references/self-repair.md for the format."
    rule = parse_paste(src.read_text(encoding="utf-8"))
    problems = []
    if not rule["name"] or not rule["match"] or not rule["fields"] or not rule["samples"]:
        problems.append("a rule needs LAYOUT, at least one MATCH, at least one SAMPLE and at least one FIELD line")
    for f in rule["fields"]:
        if f["dir"] not in DIRS or f["type"] not in TYPES:
            problems.append(f"field {f['name']}: direction must be one of {DIRS} and type one of {TYPES}")
    if not rule["expect"]:
        problems.append("give the value you read by eye as the last column of each FIELD line, so the engine can prove the rule reads it")
    if problems:
        return False, "Layout rejected, nothing saved: " + "; ".join(problems)
    load(v)
    saved = list(RULES)
    RULES.clear()                      # test the new rule against what the existing parsers already do
    try:
        for s in rule["samples"]:
            path = _sample_path(v, s)
            if path is None:
                return False, f"Layout rejected: no archived text for sample {s} (look in raw/ocr/)."
            d = doc_from_text(path)
            if not matches(d, rule):
                return False, f"Layout rejected: the MATCH lines do not all appear on {s}."
            for f in rule["fields"]:
                hit = read_field(d, f["anchor"], f["dir"], f["type"])
                want = rule["expect"].get(f["name"])
                if want is not None and (hit is None or hit.t.strip() != want.strip()):
                    return False, f"Layout rejected: field {f['name']} read {hit.t if hit else 'nothing'} on {s}, but you read {want}. Adjust the anchor, direction or type."
        clash = []
        for p in sorted((v / "raw" / "ocr" / "screens").glob("*.txt")):
            d = doc_from_text(p)
            if matches(d, rule) and screens.classify(d) != "other" and p.name.replace(".txt", "") not in rule["samples"]:
                clash.append(p.name)
        if clash:
            return False, f"Layout rejected: its MATCH lines also fit screens an existing parser already reads ({', '.join(clash[:3])}). Make MATCH more specific."
    finally:
        RULES.clear()
        RULES.extend(saved)
    if any(r["name"] == rule["name"] for r in saved):
        return False, f"A layout named '{rule['name']}' already exists. Give the new one a different name (rules are only appended)."
    entry = {k: rule[k] for k in ("name", "match", "fields", "samples")}
    entry["learned"] = today()
    atomic_write(v / RULES_FILE, json.dumps(saved + [entry], indent=1) + "\n")
    src.unlink()
    load(v)
    return True, f"Learned layout '{rule['name']}' ({len(rule['fields'])} fields). From the next week it is read by the engine; reprocess with `week --reprocess <week>` if the screens are still kept."
