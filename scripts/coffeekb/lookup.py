"""`coffee facts <topic>`: structured answers from the ledger, so a question never needs an image.

Topics it understands: a menu item ("iced coffee"), a store metric ("cups", "wage", "blend", "morale", "ratings"),
a decision ("cups", "training"), or a group ("cold drinks", "hot", "food"). Anything else falls back to text search.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import analysis, digest, search
from .ledger import ledger_dir

METRICS = {
    "cups": ("hot_beverage_cups", "cold_beverage_cups"), "wage": ("floor_staff_hourly_wage",), "blend": ("active_blend", "blend_price_per_lb"),
    "morale": ("staff_morale",), "skill": ("staff_skill",), "rating": ("review_overall", "review_price", "review_product", "review_service", "review_atmosphere"),
    "ratings": ("review_overall", "review_price", "review_product", "review_service", "review_atmosphere"),
    "reviews": ("review_count",), "staff": ("floor_staff_count", "floor_staff_hourly_wage", "staff_skill", "staff_morale"), "sales": ("sales",), "profit": ("net_profit", "operating_profit"), "payroll": ("payroll",), "beans": ("coffee_beans",),
}


def menu_weeks(v: Path, store: str = "") -> dict:
    """week -> menu items for one store (default: the primary store)."""
    from .db import queries as dbq
    con = dbq.fresh_con(v)
    if con is not None:
        return dbq.menu_weeks(con, store)
    store = store or analysis.primary_store(v)
    out = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "menu-weeks")):
        if store and fm.get("store") and str(fm.get("store")) != store:
            continue
        wk = str(fm.get("week", ""))
        if wk.isdigit():
            out[int(wk)] = fm.get("items") or []
    return out


def _n(x):
    try:
        return int(str(x))
    except ValueError:
        return None


def item_history(v: Path, topic: str) -> list:
    mw = menu_weeks(v)
    t = topic.lower().strip()
    names = sorted({i["name"] for its in mw.values() for i in its if t in i["name"].lower() or i["name"].lower() in t})
    out = []
    for name in names:
        out += [f"{name}: week by week (units sold last week, price, unit cost, margin, rank in its group)", "| Week | Sold | Change | Price | Unit cost | Margin | Rank in group |", "|---|---:|---|---:|---:|---:|---|"]
        for wk in sorted(mw):
            it = next((i for i in mw[wk] if i["name"] == name), None)
            if not it:
                continue
            grp = sorted((i for i in mw[wk] if i.get("group") == it.get("group") and _n(i.get("sales")) is not None), key=lambda i: -_n(i["sales"]))
            rank = next((k for k, i in enumerate(grp, 1) if i["name"] == name), None)
            rk = f"{rank} of {len(grp)} {it.get('group', '')}" if rank else "n/a"
            out.append(f"| {wk} | {it.get('sales') or 'n/a'} | {it.get('sales_change') or ''} | {it.get('price')} | {it.get('unit_cost')} | {it.get('margin')}% | {rk} |")
        out.append("")
    return out


def group_ranking(v: Path, topic: str) -> list:
    t = topic.lower()
    grp = "cold" if "cold" in t or "iced" in t else "food" if "food" in t or "pastr" in t else "hot" if "hot" in t else None
    if not grp:
        return []
    mw = menu_weeks(v)
    if not mw:
        return []
    wk = max(w for w, its in mw.items() if any(_n(i.get("sales")) is not None for i in its))
    items = sorted((i for i in mw[wk] if i.get("group") == grp and _n(i.get("sales")) is not None), key=lambda i: -_n(i["sales"]))
    return [f"{grp} items, week {wk}, units sold last week:"] + [f"  {k}. {i['name']}: {i['sales']} ({i.get('sales_change') or 'n/a'}), price ${i['price']}, margin {i['margin']}%" for k, i in enumerate(items, 1)] + [""]


def metric_history(v: Path, topic: str) -> list:
    t = topic.lower()
    keys = next((ks for name, ks in METRICS.items() if name in t), None)
    if not keys:
        return []
    hist = analysis._store_by_week(v)
    weeks = digest._merged_weeks(v)
    out = [f"{topic}: by week", "| Week | " + " | ".join(k.replace("_", " ") for k in keys) + " |", "|---|" + "---|" * len(keys)]
    for wk in sorted(hist):
        vals = [str(hist[wk].get(k, weeks.get(str(wk), {}).get("fields", {}).get(k, ""))) for k in keys]
        out.append(f"| {wk} | " + " | ".join(vals) + " |")
    return out + [""]


def merged_decisions(v: Path) -> dict:
    from . import decisions
    return decisions.merged(v)


def decision_history(v: Path, topic: str) -> list:
    words = [w for w in re.findall(r"[a-z]{4,}", topic.lower())]
    out = []
    for name, fm in merged_decisions(v).items():
        # only the fields that describe the decision, not bookkeeping (dates, file names, amend reasons), so a topic like "sales" is not matched by noise
        blob = " ".join(str(fm.get(k, "")) for k in ("decision", "recommendation", "options", "ceo_decision", "do_not_yet", "risks")).lower()
        if words and all(re.search(rf"\b{w}", blob) for w in words):
            out.append(f"- {name} | status: {fm.get('ceo_decision', 'unknown')} | {str(fm.get('recommendation', ''))[:140]}")
    return (["decisions mentioning that:"] + out + [""]) if out else []


def facts(v: Path, topic: str) -> str:
    parts = item_history(v, topic) + group_ranking(v, topic) + metric_history(v, topic) + decision_history(v, topic)
    if not parts:
        hits = search.find(v, topic)
        return "\n".join(hits) if hits else "No record of that. Say so and ask the CEO; do not open images."
    return "\n".join(parts).rstrip() + "\n"


def claims_warnings(v: Path, text: str) -> list:
    """Check "top-selling / best seller" statements against the latest weekly menu record."""
    mw = menu_weeks(v)
    sold = [w for w, its in mw.items() if any(_n(i.get("sales")) is not None for i in its)]
    if not sold:
        return []
    wk = max(sold)
    items = [i for i in mw[wk] if _n(i.get("sales")) is not None]
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        if not re.search(r"top[- ]sell|best[- ]sell|best seller|most popular|top seller", sent, re.I):
            continue
        named = [i for i in items if i["name"].lower() in sent.lower()]
        for grp in {i["group"] for i in named}:
            ranked = sorted((i for i in items if i["group"] == grp), key=lambda i: -_n(i["sales"]))
            top = ranked[0]
            if top["name"] not in [i["name"] for i in named]:
                out.append(f"'{sent.strip()[:110]}' names {', '.join(i['name'] for i in named if i['group'] == grp)} as top sellers, "
                           f"but week {wk}'s best {grp} seller is {top['name']} ({top['sales']} units). Check with `sh scripts/run.sh facts {grp} items`.")
    return out
