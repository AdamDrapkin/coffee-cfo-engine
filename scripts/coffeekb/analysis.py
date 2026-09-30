"""ANALYSIS INPUTS: everything the CFO needs to write a rich answer, computed here so the chat does no arithmetic.

Every figure is read from this run's screens (the rows saved in the bundle) or from the previous run's bundle,
or computed from them. Computed figures are labeled "computed" so nothing is mistaken for a screen value.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .util import note_problem


def _n(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)).replace("--", "-"))
    except ValueError:
        return None


def _metrics(rows) -> dict:
    m = {}
    for r in rows:
        if r.get("unreadable"):
            continue
        v = _n(r["value"]) if r["field"] not in ("store", "blend", "statement_column", "manager_name", "campaign", "option") else None
        if v is not None and not r["field"].endswith("change_vs_prior_week"):
            m[r["field"]] = v
    return m


def _store_history(v: Path):
    return _store_by_week(v)


def previous_and_older(v: Path, week):
    """(values of the week BEFORE `week`, {metric: (older week, value)} for metrics missing from it).

    A comparison is only ever made with the week immediately before. A metric that was not recorded that week is
    reported as missing (with the last week it was seen), never silently compared with an older week."""
    if not str(week).isdigit():
        return {}, {}
    wk = int(week)
    hist = _store_history(v)
    prev = {k: _n(val) for k, val in hist.get(wk - 1, {}).items() if _n(val) is not None and not isinstance(val, str) or (isinstance(val, str) and _n(val) is not None and k not in ("name", "active_blend"))}
    older = {}
    for w in sorted((w for w in hist if w < wk - 1), reverse=True):
        for k, val in hist[w].items():
            n = _n(val)
            if n is not None and k not in prev and k not in older and k not in ("week", "name", "active_blend"):
                older[k] = (w, n)
    return prev, older


def _previous(v: Path, current_id: str, cur_sales=None, week=""):
    return previous_and_older(v, week)[0]


def _fmt(x, money=False):
    if x is None:
        return "n/a"
    s = f"{abs(x):,.2f}".rstrip("0").rstrip(".") if abs(x) < 100 and x != int(x) else f"{abs(x):,.0f}"
    return ("-" if x < 0 else "") + ("$" if money else "") + s


def _cmp(name, cur, prev, money=False, unit=""):
    if cur is None:
        return None
    if prev is None or prev == 0:
        return f"  - {name}: {_fmt(cur, money)}{unit}"
    pct = (cur - prev) / abs(prev) * 100
    diff = cur - prev
    if diff == 0:
        return f"  - {name}: {_fmt(cur, money)}{unit} (unchanged from last week)"
    sign = "up" if diff > 0 else "down"
    return f"  - {name}: {_fmt(cur, money)}{unit} (previous {_fmt(prev, money)}{unit}; {sign} {_fmt(abs(diff), money)}{unit}, {abs(pct):.0f}%)"


def build(v: Path, rows, bundle_id: str, week: str = "") -> list:
    cur = _metrics(rows)
    cur_text = {r['field']: r['value'] for r in rows if r['field'] in ('active_blend',) and not r.get('unreadable')}
    prev, older = previous_and_older(v, week)
    L = []
    sales = cur.get("sales")
    if sales:
        L.append("ANALYSIS INPUTS. Screen values are exact; anything marked computed was calculated here. Use these in your answer:")
        L.append("Store results (screen values):")
        for k, name in (("sales", "sales"), ("hot_beverage_sales", "hot beverage sales"), ("cold_beverage_sales", "cold beverage sales"),
                        ("food_sales", "food sales"), ("net_profit", "net profit"), ("operating_profit", "operating profit")):
            x = _cmp(name, cur.get(k), prev.get(k), money=True)
            if x:
                L.append(x)
        L.append("Where the money goes (computed as a share of sales; previous week in brackets when known):")
        exp_keys = (("coffee_beans", "coffee beans"), ("cogs", "cost of goods sold"), ("payroll", "salaries"), ("rent", "rent"),
                    ("marketing", "marketing"), ("other_costs", "depreciation"))
        for k, name in exp_keys:
            if cur.get(k) is not None:
                share = cur[k] / sales * 100
                ps = f" [{prev[k] / prev['sales'] * 100:.0f}% before]" if prev.get(k) is not None and prev.get("sales") else ""
                L.append(f"  - {name}: {_fmt(cur[k], True)}, {share:.0f}% of sales{ps}")
        if cur.get("total_expenses"):
            L.append(f"  - total expenses: {_fmt(cur['total_expenses'], True)}, {cur['total_expenses'] / sales * 100:.0f}% of sales (computed)")
        var = (cur.get("coffee_beans") or 0) + (cur.get("cogs") or 0)
        fixed = sum(cur.get(k) or 0 for k in ("payroll", "rent", "marketing", "other_costs"))
        if var and fixed and var < sales:
            be = fixed / (1 - var / sales)
            L.append(f"  - break-even sales (computed, treating beans and cost of goods as variable and salaries, rent, marketing and depreciation as fixed): about {_fmt(be, True)}; this week's sales are {sales / be * 100:.0f}% of that. This is an estimate, say so.")
    cups = [(k, cur[k]) for k in ("hot_beverage_cups", "cold_beverage_cups") if k in cur]
    if cups:
        L.append("Customers and cups (screen values):")
        for k, name in (("hot_beverage_cups", "hot beverage cups"), ("cold_beverage_cups", "cold beverage cups")):
            x = _cmp(name, cur.get(k), prev.get(k))
            if x:
                L.append(x)
        total = sum(c for _, c in cups)
        if sales and len(cups) == 2:
            L.append(f"  - total cups: {total:,.0f} (computed); sales per cup about {sales / total:.2f} dollars (computed, includes food sales)")
    rev = [(k, n) for k, n in (("review_overall", "overall rating"), ("review_price", "price rating"), ("review_product", "product rating"),
                               ("review_service", "service rating"), ("review_atmosphere", "atmosphere rating"), ("review_count", "number of reviews"),
                               ("staff_skill", "floor staff skill"), ("staff_morale", "floor staff morale"), ("floor_staff_hourly_wage", "floor staff hourly wage"),
                               ("blend_price_per_lb", "blend price per lb")) if k in cur]
    if rev:
        L.append("Ratings, staff and supplies (screen values, 5 is best for ratings):")
        for k, name in rev:
            if k == "blend_price_per_lb":
                L.append(f"  - blend price per lb: {_fmt(cur[k], True)} (compare only with the same blend's earlier price; see CHANGES SINCE LAST WEEK for whether the blend changed)")
            else:
                L.append(_cmp(name, cur[k], prev.get(k), money=k.endswith(("wage", "per_lb"))))
    from .briefing import customer_voice
    voice, themes = customer_voice(rows)
    if voice:
        total = cur.get("review_count")
        try:
            from . import digest
            from .ledger import ledger_dir
            have = sum(1 for _, fm in digest._notes(ledger_dir(v) / "reviews") if str(fm.get("week")) == str(week))
        except Exception as e:
            note_problem(__name__, e)
            have = len(voice)
        L.append("What customers are saying (verbatim" + (f"; {have} of {_fmt(total)} reviews captured" if total else "") + "):")
        L += [f'  - "{c}"' for c in voice]
        L += [f"  - theme {n}: {len(cs)} of {len(voice)}" for n, cs in themes.items()]
    camps = sorted(k for k in cur if k.startswith("active_campaign_"))
    if camps:
        L.append("Active store campaigns (screen values, per week): " + ", ".join(f"{k[16:].replace('_', ' ')} {_fmt(cur[k], True)}" for k in camps))
    if "active_blend" in cur_text:
        L.append(f"Coffee blend in use this week (screen value): {cur_text['active_blend']}")
    gaps = [f"{k.replace('_', ' ')} (last recorded in week {w}: {_fmt(val)})" for k, (w, val) in older.items()
            if k in cur and k not in prev and not k.endswith("change_vs_prior_week")]
    if str(week).isdigit() and gaps:
        L.append(f"NOT COMPARED: week {int(week) - 1} has no record of: " + "; ".join(gaps[:8]) + ". Say the comparison is unavailable; do not compare with an older week as if it were last week.")
    return L


# ---------------------------------------------------------------------------- memory across weeks

WATCH = (("floor_staff_count", "number of floor staff"), ("active_blend", "coffee blend in use"), ("blend_price_per_lb", "blend price per lb"), ("floor_staff_hourly_wage", "floor staff hourly wage"),
         ("staff_skill", "floor staff skill"), ("staff_morale", "floor staff morale"))


def primary_store(v: Path) -> str:
    """The store with the most records (the one the weekly comparisons follow until more stores exist)."""
    from . import digest
    from .db import queries as dbq
    from .ledger import ledger_dir
    con = dbq.fresh_con(v)
    if con is not None:
        return dbq.primary_store(con)
    counts = {}
    for _, fm in digest._notes(ledger_dir(v) / "stores"):
        n = str(fm.get("name") or "")
        if n:
            counts[n] = counts.get(n, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def _store_by_week(v: Path, store: str = "") -> dict:
    """week -> merged store fields for one store (default: the primary store), from records that carry a week."""
    from . import digest
    from .db import queries as dbq
    from .ledger import ledger_dir
    con = dbq.fresh_con(v)
    if con is not None:
        return dbq.store_by_week(con, store)
    store = store or primary_store(v)
    out = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "stores")):
        if store and str(fm.get("name") or "") != store:
            continue
        wk = str(fm.get("week", "")).strip()
        if wk.isdigit():
            out.setdefault(int(wk), {}).update({k: val for k, val in fm.items() if val not in (None, "")})
    return out


def identical_to_last_week(v: Path, week: str) -> list:
    """Figures that match last week to the dollar or unit. A real business rarely repeats a category exactly, so say it may be stale."""
    if not str(week).isdigit() or int(week) < 2:
        return []
    hist = _store_by_week(v)
    cur, prev = hist.get(int(week)), hist.get(int(week) - 1)
    out = []
    if cur and prev:
        for k, name in (("hot_beverage_sales", "hot beverage sales"), ("cold_beverage_sales", "cold beverage sales"), ("food_sales", "food sales")):
            if cur.get(k) not in (None, "") and str(cur.get(k)) == str(prev.get(k)):
                out.append(f"  - {name} ${cur[k]} is identical to last week to the dollar")
    try:
        from .calendar import mix_history
        m = {w: (h, c) for w, h, c in mix_history(v, int(week), 3)}
        if int(week) in m and int(week) - 1 in m:
            for i, name in ((0, "hot"), (1, "cold")):
                if m[int(week)][i] == m[int(week) - 1][i]:
                    out.append(f"  - total {name} units ({m[int(week)][i]}) are identical to last week")
    except Exception as e:
        note_problem(__name__, e)
    if out:
        out.insert(0, "IDENTICAL TO LAST WEEK (this has happened in more than one week, and a real business rarely repeats a category exactly; it may be how the game reports or an old screen):")
        out.append("  - Say in the analysis that these are unverified; do not call them 'steady' or 'rock-solid' and do not build a recommendation on them. Ask the CEO to re-check those screens if the conclusion depends on them.")
    return out


def changes(v: Path, week: str) -> list:
    """What is different from last week on the screens: the blend, wages, campaigns. Also what the CEO decided to change."""
    if not str(week).isdigit():
        return []
    hist = _store_by_week(v)
    wk = int(week)
    prev_keys = [k for k in hist if k < wk]
    cur = hist.get(wk, {})
    out = []
    if cur and prev_keys:
        pw = max(prev_keys)
        prev = hist[pw]
        for key, label in WATCH:
            a, b = prev.get(key), cur.get(key)
            if b is None:
                continue
            if a is None:
                out.append(f"  - {label}: {b} (last week's value was not recorded, so do not compare it with older weeks)")
            elif str(a) != str(b):
                out.append(f"  - {label} CHANGED: {a} in week {pw}, {b} in week {wk}")
        camps = {k for k in cur if k.startswith("active_campaign_")}
        pcamps = {k for k in prev if k.startswith("active_campaign_")}
        for k in sorted(camps - pcamps):
            out.append(f"  - campaign started: {k[16:].replace('_', ' ')} {cur[k]} per week")
        if camps:                      # only when this week's marketing screens were uploaded; no screen means unknown, not removed
            for k in sorted(pcamps - camps):
                out.append(f"  - campaign no longer shown: {k[16:].replace('_', ' ')}")
        elif pcamps:
            out.append("  - campaigns: no marketing screen this week, so campaign changes are unknown (do not say any campaign was removed)")
    elif cur:
        out.append("  - no earlier week with recorded store values to compare against")
    return out


def decisions_in_force(v: Path, n=3) -> list:
    """Latest n decisions (by week), each with its explicit status and what the CEO did."""
    import re as _re
    from . import decisions as dc
    items = list(dc.merged(v).items())
    def wk(item):
        m = _re.match(r"Week (\d+)", item[0])
        return int(m.group(1)) if m else 0
    items = [t for _, t in sorted(enumerate(items), key=lambda it: (wk(it[1]), it[0]))]
    out = []
    for name, fm in items[-n:]:
        out.append(f"  - [{dc.status_of(fm)}] {name} | recommendation: {str(fm.get('recommendation', ''))[:160]} | CEO: {fm.get('ceo_decision', 'unknown')}")
    return out


def reviews_on_record(v: Path, week: str) -> list:
    from . import digest
    from .ledger import ledger_dir
    from .briefing import THEMES
    import re as _re
    notes = digest._notes(ledger_dir(v) / "reviews")
    if not notes:
        return []
    by = {}
    for _, fm in notes:
        wk = str(fm.get("week", "?"))
        by.setdefault(wk, []).append(fm)
    wks = sorted(by, key=lambda k: int(k) if k.isdigit() else 0)
    out = [f"  - {len(notes)} individual reviews are recorded across weeks {wks[0]} to {wks[-1]}: read wiki/hubs/hub-reviews.md (all of them, by week) and search wiki/ledger/reviews/ for keywords such as beans, staff, price, wifi.",
           "  - The game shows more reviews in total than the cards visible on screens; that is normal and is not a reason to hedge. Describe what is on record and how it changed week to week."]
    for name, _pat in THEMES:
        cnt = []
        for wk in wks[-5:]:
            n = sum(1 for fm in by[wk] if fm.get("theme") == name)
            cnt.append(f"wk{wk}:{n}")
        if any(not c.endswith(":0") for c in cnt):
            out.append(f"  - theme '{name}' by week: " + ", ".join(cnt))
    return out


def menu_ranking(rows) -> list:
    """Best sellers per group (hot, cold, food) from this week's menu screens, with change from the week before."""
    from .week import _menu_items
    items = [i for i in _menu_items(rows) if str(i["sales"]).isdigit()]
    if not items:
        return []
    out = ["MENU SALES RANKING (units sold last week per item, from the screens; use this, not memory, when naming top sellers):"]
    for g in ("hot", "cold", "food"):
        grp = sorted((i for i in items if i["group"] == g), key=lambda i: -int(i["sales"]))
        if grp:
            out.append(f"  {g} ({sum(int(i['sales']) for i in grp)} units): " + "; ".join(
                f"{k}. {i['name']} {i['sales']} ({i['sales_change'] or 'change n/a'}, margin {i['margin'] or '?'}%)" for k, i in enumerate(grp, 1)))
    return out


TYPICAL_KINDS = (("weekly_results", "the weekly results screen (revenue, cash flow, newspaper)"), ("income_statement", "the store income statement"),
                 ("store_performance", "the store performance screen (cups sold, blend in use)"), ("customer_reviews", "the customer reviews screens"),
                 ("menu_item", "the menu item screens (units sold per item)"))


def failure_audit(kinds: dict, n_recognized: int, needs_eyes: int, flags: list, second_checked: int) -> list:
    """WHAT COULD BE WRONG THIS WEEK: the weak points of this batch, so the analysis states its limits instead of hiding them."""
    out = []
    for kind, label in TYPICAL_KINDS:
        n = kinds.get(kind, 0)
        if n == 0:
            out.append(f"  - No {label} arrived. Anything that depends on it (see the packet sections that are missing) is unavailable this week; do not fill the gap from memory.")
        elif kind == "menu_item" and n < 13:
            out.append(f"  - Only {n} of 16 menu items were read, so rankings and margins cover part of the menu.")
    if needs_eyes:
        out.append(f"  - {needs_eyes} screen(s) are not recognized; whatever they show is not in these numbers until it is recorded.")
    if n_recognized and second_checked < n_recognized * 0.8:
        out.append(f"  - Only {second_checked} of {n_recognized} screens were confirmed by the second reader; digits on the others rest on one reading.")
    bad = [f for f in flags if f.startswith(("AUDIT FAIL", "READERS DISAGREE"))]
    if bad:
        out.append(f"  - {len(bad)} value(s) disagree between readers or with the ledger (listed under CHECK THESE); treat them as unconfirmed.")
    if not out:
        out.append("  - Nothing stands out: every usual screen arrived, all were recognized, and the readers agree. Estimates are still labeled as estimates.")
    return out
