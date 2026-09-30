"""`coffee coverage`: screens archived versus records actually filed.

The archive shows what the CEO showed the AI. The ledger shows what was recorded.
When a kind of screen has been archived but its records are missing, that is a gap:
the information was seen and then lost. Filing prints these gaps so they get closed.
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

from .digest import META, _notes
from .ledger import ledger_dir

_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-wk([a-z0-9]+)-(.+?)-\d+(?:-\d+)?\.[A-Za-z]+$")
CASH_FIELDS = ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow")


def _screens(v: Path):
    by_type = collections.Counter()
    weeks = collections.defaultdict(set)
    d = v / "raw" / "screenshots"
    if d.exists():
        for p in d.iterdir():
            m = _NAME.match(p.name)
            if not m:
                continue
            wk, typ = m.group(1), m.group(2)
            by_type[typ] += 1
            weeks[wk].add(typ)
    return by_type, weeks


def _catalog(v: Path):
    c = collections.Counter()
    for _, fm in _notes(ledger_dir(v) / "catalog"):
        c[str(fm.get("category", "other"))] += 1
    return c


def gaps(v: Path):
    by_type, weeks = _screens(v)
    cat = _catalog(v)
    out = []

    def n(*keys):
        return sum(c for t, c in by_type.items() if any(k in t for k in keys))

    build = n("store-layout", "equipment", "build")
    built = cat["exterior"] + cat["interior"] + cat["equipment"]
    if build and built < build * 0.5:
        out.append(f"{build} build-store screens are archived but only {built} exterior, interior or equipment options are recorded "
                   "(file each option with target catalog).")
    for keys, cats, what in ((("menu", "pricing"), ("menu",), "menu and pricing"),
                             (("employees", "payroll", "staff"), ("staff",), "staff and payroll"),
                             (("marketing", "advertising"), ("marketing", "other"), "marketing")):
        shown = n(*keys)
        have = sum(cat[c] for c in cats)
        if shown and not have:
            out.append(f"{shown} {what} screens are archived but no {what} options are recorded in the catalog.")

    week_notes = {}
    for p, fm in _notes(ledger_dir(v) / "weeks"):
        wk = str(fm.get("week", ""))
        merged = week_notes.setdefault(wk, {})
        merged.update({k: val for k, val in fm.items() if k not in META})
    for wk, types in sorted(weeks.items()):
        if not any(("income" in t or "weekly" in t or "cash-flow" in t) for t in types) or not wk.isdigit():
            continue
        if wk not in week_notes:
            out.append(f"Week {wk} results screens are archived but there is no week {wk} record.")
        else:
            missing = [f for f in CASH_FIELDS if f not in week_notes[wk]]
            if missing and "net_income" in week_notes[wk]:
                out.append(f"Week {wk} record lacks {', '.join(missing)} (read them from the weekly results screen and file an amend).")
    return out
