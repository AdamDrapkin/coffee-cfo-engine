"""Confirmed game facts: what the game does and does not let the CEO do, as confirmed on screens or by the CEO.

wiki/knowledge-base/confirmed-game-facts.md is append-only. Rows of kind NOT AVAILABLE are used as a guard: an analysis
that recommends something listed there is flagged when it is filed. Rows come from the analysis section "Game facts learned".
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import atomic_write, page_fm, today, write_page

PAGE = "wiki/knowledge-base/confirmed-game-facts.md"
HEAD = ("# Confirmed game facts\n\nWhat the game does and does not allow, confirmed on screens or by the CEO. Rows are only appended. "
        "A NOT AVAILABLE row means the action does not exist; never recommend it.\n\n"
        "| Date | Kind | Keywords | Fact | Source |\n|---|---|---|---|---|\n")
SEED = [
    ("NOT AVAILABLE", "train, staff", "There is no operational training action for floor staff. Under the store manager the only controls are the four delegation switches (staffing and salary, products and pricing, store marketing, store troubles), the manager's salary and firing. Floor staff controls are the number of staff and their hourly wage; skill and morale are shown but cannot be set.", "CEO, 2026-09-30"),
    ("AVAILABLE", "levers", "Levers the CEO has on screens: floor staff count, floor staff hourly wage, manager salary, the four manager delegation switches, fire manager, menu prices, marketing campaigns and their options (Wi-Fi, power strips, catering, community sponsors, direct mail, local paid search, buy one get one, free music, social media, recyclable cups), coffee blend from a supplier, store exterior, interior and equipment.", "Screens weeks 3 to 10"),
]


def _cell(x: str) -> str:
    return str(x).replace("|", "/").replace("\n", " ").strip()


def ensure(v: Path) -> Path:
    p = v / PAGE
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        body = HEAD + "".join(f"| {today()} | {k} | {kw} | {_cell(f)} | {_cell(src)} |\n" for k, kw, f, src in SEED)
        write_page(p, page_fm("Confirmed game facts", "What the game does and does not allow, as confirmed.", "knowledge", ["knowledge-base", "facts"], status="final"), body)
    return p


def append(v: Path, kind: str, keywords: str, fact: str, source: str) -> None:
    p = ensure(v)
    t = p.read_text(encoding="utf-8").rstrip("\n")
    atomic_write(p, t + f"\n| {today()} | {_cell(kind)} | {_cell(keywords)} | {_cell(fact)} | {_cell(source)} |\n")


def rows(v: Path) -> list:
    p = v / PAGE
    if not p.exists():
        return []
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]


def guard_warnings(v: Path, text: str) -> list:
    low = text.lower()
    out = []
    try:
        from .db import queries as dbq
        con = dbq.fresh_con(v)
        if con is not None:            # levers that do not exist in the game, from the database
            for name, kws in dbq.levers_missing(con):
                if kws and all(re.search(r"\b" + re.escape(k), low) for k in kws):
                    out.append(f"The analysis mentions {', '.join(kws)}, but '{name}' does not exist in the game. Recommend only actions listed in references/game-levers.md.")
    except Exception as e:
        from .util import note_problem
        note_problem(__name__, e)
    for r in rows(v):
        if len(r) >= 4 and r[1].upper() == "NOT AVAILABLE":
            kws = [k.strip().lower() for k in r[2].split(",") if k.strip()]
            if kws and all(re.search(r"\b" + re.escape(k), low) for k in kws):
                out.append(f"The analysis mentions {', '.join(kws)}, which the CEO confirmed is NOT AVAILABLE in the game: {r[3][:160]} Recommend only actions listed in references/game-levers.md.")
    return out


def parse_learned(section: str) -> list:
    """Bullets like 'NOT AVAILABLE | train, staff | explanation' or 'FACT | keywords | explanation'."""
    out = []
    for ln in section.splitlines():
        item = re.sub(r"^[\s\-*\d.)]+", "", ln).strip()
        parts = [x.strip() for x in item.split("|")]
        if len(parts) >= 3 and parts[0].upper() in ("NOT AVAILABLE", "AVAILABLE", "FACT"):
            out.append((parts[0].upper(), parts[1], parts[2]))
    return out
