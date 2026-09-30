"""Corrections: what to do when something already filed turns out to be wrong or out of date.

History is never rewritten. A correction is its own append-only record that says what was
claimed, what is true, and why. Filing one then:
- writes the correction note listing every affected document,
- puts a visible warning banner at the top of each affected briefing or knowledge page
  (their original text stays untouched below it),
- leaves ledger records alone (append-only) but flags them everywhere they are listed,
- shows the correction in the state digest that the AI reads first in every conversation,
- appears in the corrections hub, and lint checks that every affected briefing carries its banner.
"""
from __future__ import annotations

import re
from pathlib import Path

from .ledger import ledger_dir
from .util import _FM, read_page, today, write_page


def norm(s) -> str:
    return " ".join(str(s).lower().split())


def notes(v: Path):
    d = ledger_dir(v) / "corrections"
    out = []
    if d.exists():
        for p in sorted(d.glob("20*.md")):
            fm, body = read_page(p)
            if fm:
                out.append((p, fm))
    return out


def corrected_map(v: Path) -> dict:
    """stem of an affected note -> [stems of the corrections that concern it]."""
    m = {}
    for p, fm in notes(v):
        for stem in fm.get("affected") or []:
            m.setdefault(str(stem), []).append(p.stem)
    return m


def flag(stem: str, cmap: dict) -> str:
    c = cmap.get(stem)
    return f" (CORRECTED, see [[{c[-1]}]])" if c else ""


def _listify(x):
    if x in (None, ""):
        return []
    if isinstance(x, (list, tuple)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [i.strip() for i in re.split(r"[;,\n]", str(x)) if i.strip()]


def _candidates(v: Path):
    """Documents a correction can flag: briefings and knowledge pages (editable), ledger notes (read-only)."""
    for sub in ("wiki/briefings", "wiki/knowledge-base"):
        for p in sorted((v / sub).glob("*.md")):
            yield p, True
    for p in sorted(ledger_dir(v).rglob("20*.md")):
        if "corrections" not in p.parts:
            yield p, False
    for p in sorted((ledger_dir(v) / "weeks").glob("week-*.md")):
        yield p, False


def _banner(stem_corr: str, claim: str, correction: str) -> str:
    return (f"\n> [!warning] Corrected on {today()}\n"
            f"> This document says: \"{claim}\". Correction: {correction} See [[{stem_corr}]].\n")


def apply(v: Path, note_path: Path, skip_stems=()):
    """Flag everything a freshly written correction touches. Returns human-readable info lines."""
    fm, body = read_page(note_path)
    claim, corr = str(fm.get("claim", "")).strip(), str(fm.get("correction", "")).strip()
    stem = note_path.stem
    wanted = {norm(x) for x in _listify(fm.get("applies_to"))}
    key = norm(claim)
    affected = {}
    for p, editable in _candidates(v):
        if p.stem in skip_stems or p == note_path:
            continue
        hit = p.stem.lower() in wanted or norm(p.stem) in wanted
        if not hit and len(key) >= 12:
            hit = key in norm(p.read_text(encoding="utf-8", errors="replace"))
        if hit:
            affected[p.stem] = (p, editable)

    bannered, history = [], []
    for s, (p, editable) in sorted(affected.items()):
        if editable:
            text = p.read_text(encoding="utf-8")
            if f"[[{stem}]]" not in text:
                m = _FM.match(text)
                cut = m.end() if m else 0
                p.write_text(text[:cut] + _banner(stem, claim, corr) + text[cut:], encoding="utf-8")
            bannered.append(s)
        else:
            history.append(s)

    fm["affected"] = sorted(affected)
    lines = ["", "## Affected notes",
             "Briefings and knowledge pages carry a warning banner at the top and keep their original text below it."]
    lines += [f"- Banner added: [[{s}]]" for s in bannered] or ["- none"]
    lines += ["", "Ledger records are append-only, so they are left exactly as filed and flagged wherever they are listed:"]
    lines += [f"- History, left as filed: [[{s}]]" for s in history] or ["- none"]
    write_page(note_path, fm, body.rstrip() + "\n" + "\n".join(lines) + "\n")
    return [f"Correction filed: {len(bannered)} document(s) now carry a warning banner and {len(history)} ledger record(s) are flagged as history."]


def problems(v: Path):
    """Lint: every correction is complete and every affected editable document carries its banner."""
    out = []
    for p, fm in notes(v):
        rel = p.relative_to(v)
        if not str(fm.get("claim", "")).strip() or not str(fm.get("correction", "")).strip():
            out.append(f"{rel}: correction lacks a claim or the corrected fact")
        for s in fm.get("affected") or []:
            hits = [(q, ed) for q, ed in _candidates(v) if q.stem == s]
            if not hits:
                out.append(f"{rel}: lists {s} which does not exist")
                continue
            q, editable = hits[0]
            if editable and f"[[{p.stem}]]" not in q.read_text(encoding="utf-8", errors="replace"):
                out.append(f"{q.relative_to(v)}: affected by {p.stem} but has no correction banner")
    return out
