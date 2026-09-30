"""De-duplication for the week engine: what is already filed, and what changed since.

Menu changes are only recorded in the catalog when they matter (a new price, unit cost up or down 5% or more, margin
moved 3 points or more); smaller drift lives in the weekly menu record."""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

from . import digest, screens
from .ledger import ledger_dir

def _norm(s) -> str:
    return " ".join(str(s).lower().split())


def _existing(v: Path):
    """What is already filed, so nothing is filed twice."""
    cat = {(_norm(fm.get("category")), _norm(fm.get("name"))) for _, fm in digest._notes(ledger_dir(v) / "catalog")}
    ev = {_norm(fm.get("event")) for _, fm in digest._notes(ledger_dir(v) / "events")}
    cap = {(_norm(fm.get("opportunity")), str(fm.get("required_cash"))) for _, fm in digest._notes(ledger_dir(v) / "capital-allocation")}
    return cat, ev, cap, digest._merged_weeks(v)


def _as_num(x) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return screens.money_val(str(x))
    except ValueError:
        return float("nan")


def _pnum(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)))
    except ValueError:
        return None


def _menu_prior(v: Path) -> dict:
    """Latest known price, unit cost and margin per menu item, from old notes (which kept price and margin in the notes text) and new ones."""
    out = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "catalog")):
        if _norm(fm.get("category")) != "menu":
            continue
        notes = str(fm.get("notes", ""))
        price = fm.get("price") or (re.search(r"price\s*\$?([\d.]+)", notes, re.I) or [None, None])[1]
        unit = fm.get("unit_cost") or (fm.get("cost") if not fm.get("price") else None)
        margin = fm.get("margin") or (re.search(r"margin\s*(\d+)%", notes, re.I) or [None, None])[1]
        cur = out.get(("menu", _norm(fm.get("name"))), {})
        out[("menu", _norm(fm.get("name")))] = {**cur, **{k: val for k, val in (("price", price), ("unit_cost", unit), ("margin", margin)) if val not in (None, "")}}
    return out


MENU_COST_DRIFT = 0.05     # a unit cost that moves less than this share is drift; it lives in the weekly menu record, not a catalog amend


MENU_MARGIN_POINTS = 3


def _menu_diffs(prior: dict, f: dict) -> list:
    """Differences that matter: a new price, a unit cost that moved 5% or more, or a margin that moved 3 points or more."""
    d = []
    a, b = _pnum(prior.get("price")), _pnum(f.get("price"))
    if a is not None and b is not None and abs(a - b) > 0.004:
        d.append(f"price was ${a:.2f} (from the ledger) and is now {f.get('price')}")
    a, b = _pnum(prior.get("unit_cost")), _pnum(f.get("unit_cost"))
    if a and b is not None and abs(a - b) / a >= MENU_COST_DRIFT:
        d.append(f"unit cost was ${a:.2f} (from the ledger) and is now {f.get('unit_cost')}")
    a, b = _pnum(prior.get("margin")), _pnum(f.get("margin"))
    if a is not None and b is not None and abs(a - b) >= MENU_MARGIN_POINTS:
        d.append(f"margin was {a:.0f}% (from the ledger) and is now {f.get('margin')}")
    return d


def _same(a, b) -> bool:
    """Equal as numbers when both are numbers (14.00 and 14.0), otherwise as normalized text."""
    x, y = _pnum(a), _pnum(b)
    if x is not None and y is not None and re.fullmatch(r"[-+$\d.,%() ]+", str(a).strip()) and re.fullmatch(r"[-+$\d.,%() ]+", str(b).strip()):
        return abs(x - y) < 1e-9
    return _norm(a) == _norm(b)


def _dedupe(v: Path, parsed: dict, flags: list):
    cat, ev, cap, weeks = _existing(v)
    out, skipped = [], collections.Counter()
    seen_cat, seen_ev, seen_store = set(), set(), set()
    menu_prior, changes = _menu_prior(v), []
    store_notes = [(fm.get('name'), fm) for _, fm in digest._notes(ledger_dir(v) / 'stores')]
    menu_weeks = {('mw', str(fm.get('week')), _norm(fm.get('store')), json.dumps(fm.get('items'), sort_keys=True)) for _, fm in digest._notes(ledger_dir(v) / 'menu-weeks')}
    reviews_have = {(_norm(fm.get('review_text')), str(fm.get('week'))) for _, fm in digest._notes(ledger_dir(v) / 'reviews')}
    comp_base = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / 'competitors')):
        comp_base[_norm(fm.get('name'))] = fm
    comp_moves = {_norm(fm.get('recent_moves')) for _, fm in digest._notes(ledger_dir(v) / 'competitors')}
    stores = {(_norm(fm.get('name')), str(fm.get('week', '')), str(fm.get('sales')), str(fm.get('net_profit'))) for _, fm in digest._notes(ledger_dir(v) / 'stores')}
    for name, p in parsed.items():
        for up in p.updates:
            f, t = up["fields"], up["target"]
            if t == "catalog":
                key = (_norm(f.get("category")), _norm(f.get("name")))
                if key in seen_cat:
                    skipped["catalog"] += 1
                    continue
                seen_cat.add(key)
                if key in cat:
                    prior = menu_prior.get(key)
                    if key[0] == "menu" and prior and f.get("price"):
                        diffs = _menu_diffs(prior, f)
                        if diffs:
                            changes.append(f"{f['name']}: " + "; ".join(diffs))
                            up = {**up, "op": "amend", "reason": "Menu values on the screen differ from what was on file: " + "; ".join(diffs)}
                            out.append(up)
                            continue
                    skipped["catalog"] += 1
                    continue
            elif t == "event":
                key = _norm(f.get("event"))
                if key in ev or key in seen_ev:
                    skipped["event"] += 1
                    continue
                seen_ev.add(key)
            elif t == "competitor":
                mv = _norm(f.get("recent_moves"))
                if mv in comp_moves or ('c', mv) in seen_store:
                    skipped["competitor"] += 1
                    continue
                seen_store.add(('c', mv))
                base = comp_base.get(_norm(f.get("name")), {})
                keep = {k: base[k] for k in ("known_stores", "threat_level") if base.get(k) not in (None, "")}
                up = {**up, "fields": {**keep, **f}}
            elif t == "capital-allocation":
                key = (_norm(f.get("opportunity")), str(f.get("required_cash")).replace("$", "").replace(",", ""))
                if any(k[0] == key[0] and str(k[1]).replace(".0", "") == key[1] for k in cap):
                    skipped["capital"] += 1
                    continue
            elif t == "menu-week":
                key = ("mw", str(f.get("week")), _norm(f.get("store")), json.dumps(f.get("items"), sort_keys=True))
                if key in menu_weeks or key in seen_store:
                    skipped["menu week"] += 1
                    continue
                seen_store.add(key)
            elif t == "review":
                rk = (_norm(f.get("review_text")), str(f.get("week")))
                if rk in reviews_have or ("r", rk) in seen_store:
                    skipped["review"] += 1
                    continue
                seen_store.add(("r", rk))
            elif t == "store" and up.get("metric"):
                want = {k: val for k, val in f.items() if k not in ("name",)}
                if any(_norm(nm) == _norm(f["name"]) and all(_same(fm.get(k), val) for k, val in want.items()) for nm, fm in store_notes) \
                        or ("m", str(sorted(want.items()))) in seen_store:
                    skipped["store metrics"] += 1
                    continue
                seen_store.add(("m", str(sorted(want.items()))))
            elif t == "store":
                sig = (_norm(f.get("name")), str(f.get("week", "")), str(f.get("sales")), str(f.get("net_profit")))
                if sig in stores or sig in seen_store:
                    skipped["store"] += 1
                    continue
                seen_store.add(sig)
            elif t == "week":
                wk = str(f["week"])
                have = weeks.get(wk)
                new = {k: val for k, val in f.items() if k != "week"}
                if not have:
                    if any(u for u in out if u["target"] == "week" and str(u["fields"]["week"]) == wk):
                        skipped["week"] += 1     # same week read twice in this batch
                        continue
                else:
                    missing = {k: val for k, val in new.items() if k not in have["fields"]}
                    # values an earlier reading stored as text like "+$390": restate as plain numbers so the ledger is consistent
                    for k, val in new.items():
                        hv = have["fields"].get(k)
                        if isinstance(hv, str) and re.search(r"[$+,]", hv) and _as_num(hv) == _as_num(val):
                            missing[k] = val
                    for k, val in new.items():
                        if k in have["fields"] and screens.is_money(str(val)) and abs(screens.money_val(str(val)) - _as_num(have["fields"][k])) > 0.5:
                            flags.append(f"week {wk} {k}: the screen reads {val} but the record holds {have['fields'][k]} (left unchanged, please check)")
                    if not missing:
                        skipped["week"] += 1
                        continue
                    up = {**up, "op": "amend", "fields": {"week": wk, **missing},
                          "reason": "Values read from the weekly results screen that the earlier record did not hold, or restated as plain numbers."}
            out.append(up)
    flags.extend(f"MENU CHANGE {c}" for c in changes)
    return out, skipped
