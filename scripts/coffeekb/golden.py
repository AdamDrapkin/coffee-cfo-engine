"""Golden baseline: frozen answers and totals from the ledger, used as the acceptance test for the database migration.

`coffee golden save` records what 20 real questions return and the key counts and totals per table.
`coffee golden check` re-runs them and lists every difference. A migration step is done only when the check is clean
(or each difference is explained and the baseline is re-saved on purpose).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import analysis, decisions, digest, lookup
from .ledger import ledger_dir

BASELINE = "tests/golden/baseline.json"
QUESTIONS = ["iced coffee", "cold brew", "espresso", "muffin", "brewed coffee", "cold drinks", "hot drinks", "food items", "cups", "wage", "blend",
             "ratings", "reviews", "sales", "profit", "morale", "skill", "payroll", "beans", "training"]


def _folder_counts(v: Path) -> dict:
    out = {}
    for sub in ("weeks", "stores", "menu-weeks", "reviews", "decisions", "catalog", "events", "competitors", "corrections", "capital-allocation"):
        out[sub] = len(list((ledger_dir(v) / sub).glob("*.md")))
    return out


def totals(v: Path) -> dict:
    """Numbers a database backfill must reproduce exactly."""
    hist = analysis._store_by_week(v)
    weeks = digest._merged_weeks(v)
    mw = lookup.menu_weeks(v)
    dec = decisions.merged(v)
    return {
        "company_weeks": {wk: {k: weeks[wk]["fields"].get(k) for k in ("revenue", "net_income", "cash_flow")} for wk in sorted(weeks, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else 0))},
        "store_weeks": {str(w): {k: hist[w].get(k) for k in ("sales", "net_profit", "hot_beverage_cups", "cold_beverage_cups", "review_overall", "review_count", "staff_morale", "active_blend")} for w in sorted(hist)},
        "menu_week_units": {str(w): sum(int(i["sales"]) for i in its if str(i.get("sales", "")).isdigit()) for w, its in sorted(mw.items())},
        "menu_week_items": {str(w): len(its) for w, its in sorted(mw.items())},
        "decisions": {"total": len(dec), "by_status": _count(decisions.status_of(fm) for fm in dec.values())},
        "open_unknowns": len(decisions.open_unknowns(v)),
        "reviews_by_week": _count(str(fm.get("week")) for _, fm in digest._notes(ledger_dir(v) / "reviews")),
        "catalog_by_category": _count(c for c, _n in {(str(fm.get("category")), str(fm.get("name"))) for _, fm in digest._notes(ledger_dir(v) / "catalog")}),   # distinct options, not notes
        "folder_notes": _folder_counts(v),
    }


def _count(items) -> dict:
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return dict(sorted(out.items()))


def snapshot(v: Path) -> dict:
    return {"questions": {q: lookup.facts(v, q) for q in QUESTIONS}, "totals": totals(v)}


def save(v: Path) -> Path:
    p = v / BASELINE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot(v), indent=1, sort_keys=True, default=str), encoding="utf-8")
    return p


def _diff(a, b, path="") -> list:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f"{path}/{k}")
        return out
    return [] if a == b else [f"{path}: baseline {str(a)[:80]!r} now {str(b)[:80]!r}"]


def check(v: Path) -> list:
    p = v / BASELINE
    if not p.exists():
        return ["no baseline saved yet: run `coffee golden save`"]
    base = json.loads(p.read_text(encoding="utf-8"))
    now = json.loads(json.dumps(snapshot(v), sort_keys=True, default=str))
    return _diff(base, now)
