"""The review desk: what happens to screens the engine could not settle by itself.

- `dump`: writes each unrecognized screen as compact text (one line per text box with its position), so a
  reviewer reads a few hundred characters instead of opening an image. Opening the image is the last resort.
- `signature`: a short fingerprint of a layout, used to keep the parser gap register.
- `record_gaps`: appends every new layout to references/parser-gaps.md in the skill, so the next build knows
  exactly which parsers are still missing and has a sample to build them from.
- `cross_check`: a second, independent read of the screens with Vision's fast recognizer. If a number the
  accurate pass read is not seen by the second pass, the row is flagged for a reviewer.
- `staffing`: how many reviewers to hire for this batch.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import vision
from .util import atomic_write, note_problem

SKILL = ".agents/skills/coffee-week"
GAPS = f"{SKILL}/references/parser-gaps.md"


def signature(doc) -> str:
    heads = [l.t for l in sorted(doc.lines, key=lambda l: l.y) if l.y > 550 and l.t.isupper() and 4 <= len(l.t) <= 40 and l.h >= 30]
    return " / ".join(heads[:3]) or "no headings"


def dump(v: Path, docs_by_name: dict) -> list:
    """docs_by_name: name -> screens.Doc. Returns the dump file paths."""
    out = []
    d = v / ".coffee-work" / "week" / "review"
    d.mkdir(parents=True, exist_ok=True)
    for name, doc in docs_by_name.items():
        lines = [f"# {name}  ({doc.w}x{doc.h}); columns: y x height confidence text"]
        for l in sorted(doc.lines, key=lambda l: (round(l.y / 20), l.x)):
            if 200 <= l.y <= 2550:
                lines.append(f"{l.y:5.0f} {l.x:5.0f} h{l.h:3.0f} {l.c:.2f}  {l.t}")
        f = d / (re.sub(r"[^\w.-]", "_", name) + ".txt")
        atomic_write(f, "\n".join(lines) + "\n")
        out.append(f)
    return out


def record_gaps(v: Path, docs_by_name: dict) -> None:
    """Add layouts we cannot parse yet to the gap register (once per layout)."""
    if not docs_by_name:
        return
    p = v / GAPS
    if not p.parent.exists():
        return
    text = p.read_text(encoding="utf-8") if p.exists() else "# Parser gap register\n\nLayouts the week engine could not parse. Written automatically; each row is a parser still to build.\n\n| First seen | Layout headings | Sample file | Times seen |\n|---|---|---|---|\n"
    lines = text.rstrip("\n").split("\n")
    for name, doc in docs_by_name.items():
        sig = signature(doc)
        for i, ln in enumerate(lines):
            if ln.startswith("|") and f"| {sig} |" in ln:
                cells = [c.strip() for c in ln.strip("|").split("|")]
                try:
                    cells[3] = str(int(cells[3]) + 1)
                except ValueError:
                    pass
                lines[i] = "| " + " | ".join(cells) + " |"
                break
        else:
            lines.append(f"| {time.strftime('%Y-%m-%d')} | {sig} | {name} | 1 |")
    atomic_write(p, "\n".join(lines) + "\n")


cross_check_checked = 0


def _digits(x: str) -> str:
    return re.sub(r"[^\d.]", "", str(x))


def cross_check(v: Path, paths_by_name: dict, recognized: dict) -> list:
    """paths_by_name: name -> path. Flags rows whose number the second reader did not see."""
    try:
        seen = vision.second_read(v, [paths_by_name[n] for n in recognized if n in paths_by_name])
    except Exception as e:
        note_problem(__name__, e)
        # the chat sandbox cannot run the reader; use whatever the Mac worker already cached
        seen, _ = vision.second_cached(v, [paths_by_name[n] for n in recognized if n in paths_by_name])
    flags = []
    cross_check.checked = len([1 for n in recognized if seen.get(paths_by_name.get(n))])
    for n, x in recognized.items():
        nums = seen.get(paths_by_name.get(n))
        if not nums:
            continue
        for r in x.rows:
            val = _digits(r["value"])
            if r.get("unreadable") or len(val.replace(".", "")) < 3 or r["unit"] in ("", "stars", "score", "months", "units") or r["field"].endswith("change"):
                continue
            if val in nums or val.lstrip("0") in nums:
                continue
            # only a near miss (same length, one character different) is a real disagreement;
            # a number the fast reader simply missed proves nothing
            near = [o for o in nums if len(o) == len(val) and sum(a != b for a, b in zip(o, val)) == 1]
            if near:
                flags.append(f"READERS DISAGREE on {n}: {r['field']} reads {r['value']} in the accurate pass but {near[0]} in the second pass")
    return flags


def staffing(n_screens: int, n_unknown: int, n_flags: int) -> list:
    """The hiring plan for this batch. Programs do the reading; people (agents) are hired only for judgment."""
    lines = ["STAFFING (who is needed for this batch):"]
    lines.append(f"  - Screen readers, bookkeepers, auditor, records clerk: programs, already done ({n_screens} screens).")
    rev = -(-n_unknown // 6)
    lines.append(f"  - Review desk: hire {rev} reviewer(s) for {n_unknown} unrecognized screen(s), 6 screens each, "
                 "in parallel, reading the text dumps first." if n_unknown else "  - Review desk: no one needed, every screen was recognized.")
    lines.append(f"  - Second-look auditor: {'hire 1 to settle ' + str(n_flags) + ' flagged number(s)' if n_flags else 'not needed, no flags'}.")
    return lines


def log_run(v: Path, screens: int, recognized: int, needs_eyes: int, flags: int, seconds: float) -> None:
    # `seconds` excludes the wait for iCloud uploads to settle, which is not engine speed
    """One line per run in the skill's run log, so the skill always shows current timings."""
    p = v / SKILL / "references" / "run-log.md"
    if not p.exists():
        return
    row = f"| {time.strftime('%Y-%m-%d %H:%M')} | {screens} | {recognized} | {needs_eyes} | {flags} | {seconds} |"
    atomic_write(p, p.read_text(encoding="utf-8").rstrip("\n") + "\n" + row + "\n")
