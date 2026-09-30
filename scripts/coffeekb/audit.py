"""Read-back audit: after filing, re-read the ledger and compare it with what the screens said.

The errors found in week 6 (a menu cost change that was never recorded, a stale competitor, cash flow stored
as text) all had one thing in common: nothing checked the ledger against the screens afterwards. This does.
Every check compares a value read from a screen (the bundle rows) with what the ledger now holds.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import digest
from .ledger import ledger_dir


def _n(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)))
    except ValueError:
        return None


def _norm(s) -> str:
    return " ".join(str(s).lower().split())


def run(v: Path, rows: list, week: str = "", current: bool = True) -> tuple:
    """Returns (checks_run, failures)."""
    checks, fails = 0, []
    # menu: every item on the screen matches the weekly menu record filed for this week
    from . import lookup
    by = {}
    file_store = {r["file"]: r["value"] for r in rows if r["field"] == "store"}
    default_store = next(iter(file_store.values()), "")
    for r in rows:
        if r["field"] in ("menu_item", "price", "unit_cost", "margin", "sales_last_week") and not r.get("unreadable"):
            by.setdefault(r["file"], {})[r["field"]] = r["value"]
    recs = {}
    for f_, d in (by.items() if current else []):
        name = d.get("menu_item")
        if not name:
            continue
        st = file_store.get(f_, default_store)
        if st not in recs:
            recs[st] = {i["name"]: i for i in lookup.menu_weeks(v, st).get(int(week), [])} if str(week).isdigit() else {}
        led = recs[st].get(name)
        for field, key in (("price", "price"), ("unit_cost", "unit_cost"), ("margin", "margin"), ("sales_last_week", "sales")):
            if field in d:
                checks += 1
                a_, b_ = _n(d[field]), _n((led or {}).get(key))
                if b_ is None or a_ is None or abs(a_ - b_) > 0.004:
                    fails.append(f"menu {name}: screen {field} {d[field]} but the weekly menu record holds {(led or {}).get(key, 'nothing')}")
    # store: latest store record for the screen's store matches the income statement
    stores = sorted(set(file_store.values()))
    for store in stores:
        cur = {r["field"]: r["value"] for r in rows if not r.get("unreadable") and (file_store.get(r["file"]) == store or (len(stores) == 1))}
        c2, f2 = _audit_store(v, store, cur, week, current)
        checks, fails = checks + c2, fails + f2
    cur = {r["field"]: r["value"] for r in rows if not r.get("unreadable")}
    return _finish(v, rows, cur, week, current, checks, fails)


def _audit_store(v: Path, store: str, cur: dict, week: str, current: bool) -> tuple:
    checks, fails = 0, []
    if store and "sales" in cur and "net_profit" in cur:
        notes = [fm for _, fm in digest.chron(digest._notes(ledger_dir(v) / "stores"))
                 if _norm(fm.get("name")) == _norm(store) and (not week or str(fm.get("week", "")) == str(week))]
        latest_any = {}          # newest value of each field on any record of this store, even one filed without a week tag
        for _, fm in digest.chron(digest._notes(ledger_dir(v) / "stores")):
            if _norm(fm.get("name")) == _norm(store):
                latest_any.update({k: val for k, val in fm.items() if val not in (None, "")})
        merged = {}
        for fm in notes:   # legacy notes without a week cannot be matched to this week, so a week with no dated record is skipped, not failed
            merged.update({k: val for k, val in fm.items() if val not in (None, "")})
        for k in ("sales", "net_profit", "payroll", "rent"):
            if k in cur and notes:
                if merged.get(k) is None and not current:
                    continue          # an older week recorded before weeks were tagged: nothing to compare with
                checks += 1
                if _n(merged.get(k)) != _n(cur[k]) and _n(latest_any.get(k)) != _n(cur[k]):
                    fails.append(f"store {store}: screen {k} {cur[k]} but ledger holds {merged.get(k, 'nothing')}")
    return checks, fails


def _finish(v: Path, rows: list, cur: dict, week: str, current: bool, checks: int, fails: list) -> tuple:
    # week: cash flow and revenue are plain numbers and equal to the screen
    weeks = digest._merged_weeks(v)
    have = weeks.get(str(week), {}).get("fields", {}) if week else {}
    for k in ("revenue", "net_income", "cash_flow", "operating_cash_flow"):
        if k in cur and have:
            checks += 1
            if not isinstance(have.get(k), (int, float)) or _n(have.get(k)) != _n(cur[k]):
                fails.append(f"week {week}: screen {k} {cur[k]} but ledger holds {have.get(k, 'nothing')!r} (must be a plain number)")
    # competitors: every "X opened ... in Y" headline is reflected in X's record
    comp = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "competitors")):
        comp.setdefault(_norm(fm.get("name")), {}).update({k: val for k, val in fm.items() if val not in (None, "")})
    for r in (rows if current else []):
        if r["field"] == "headline":
            m = re.match(r"(.+?) opened (?:business|a new coffee shop) in (.+)$", r["value"])
            if m:
                checks += 1
                rec = comp.get(_norm(m.group(1)))
                if not rec or _norm(rec.get("city")) != _norm(m.group(2)):
                    fails.append(f"competitor {m.group(1)}: newspaper says {m.group(2)} but the record says {(rec or {}).get('city', 'no record')}")
    return checks, fails
