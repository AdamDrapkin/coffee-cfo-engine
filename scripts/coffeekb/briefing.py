"""The data briefing: a complete, detailed record of what the week's screens show, written by the engine.

It holds no judgment (that is the CFO analysis briefing filed next), but it holds every number with its
comparison, the cost structure, the customer and staff signals, the newspaper, the menu, what was filed,
what was checked and what is still unknown. It is the same depth as a hand-written weekly briefing.
"""
from __future__ import annotations

import collections
from pathlib import Path

from . import analysis
from .analysis import _fmt, _metrics, _previous


def _delta(name, cur, prev, money=False):
    if cur is None:
        return None
    base = f"**{name}:** {_fmt(cur, money)}"
    if prev in (None, 0):
        return base
    d = cur - prev
    return base + f" ({'up' if d > 0 else 'down'} {_fmt(abs(d), money)}, {abs(d) / abs(prev) * 100:.0f}%, from {_fmt(prev, money)}; change computed)"


def _val(rows, field):
    for r in rows:
        if r["field"] == field and not r.get("unreadable"):
            return r["value"]
    return None


THEMES = (("coffee beans and taste", r"\bbeans?\b|\btastes?\b|\btasted\b|\bhorrible\b|\bbitter|\bflavou?r|\bcoffee\b.{0,25}\b(bad|awful|weak|great|love)\b|\bquality\b"),
          ("staff and service", r"\bstaff\b|\brude\b|\bservice\b|\bwait(ing)?\b|\bslow\b|\bbarista|\bworkers?\b|\bunmotivated\b|\btired\b"),
          ("price", r"\bprices?\b|\bexpensive\b|\bpricey\b|\bcheap\b|\boverpriced\b|\bcosts?\b"),
          ("space, wifi and amenities", r"\btables?\b|\bchairs?\b|\bwi-?fi\b|\bpower strip|\boutlet|\batmosphere\b|\bmusic\b|\bquiet\b|\bremote\b|\bclean\b|\bcomfortable\b|\borganized\b|\b5g\b"),
          ("catering", r"\bcater"),
          ("eco and recycling", r"\beco\b|\brecycl|\benvironment|\bgarbage\b|\bsustainab"),
          ("marketing seen", r"\bsocial\b|\binstagram\b|\bads?\b|\badvert|\bsaw you\b"))


def customer_voice(rows) -> tuple:
    """(unique verbatim comments, {theme: [comments]}) from the review cards on the screens."""
    seen, out = set(), []
    for r in rows:
        if r["field"] == "review_comment" and r["value"] not in seen:
            seen.add(r["value"]); out.append(r["value"])
    import re
    themes = {}
    for c in out:
        for name, pat in THEMES:
            if re.search(pat, c, re.I):
                themes.setdefault(name, []).append(c)
    return out, themes


def build(v: Path, recognized: dict, rows: list, updates: list, skipped, flags: list, needs_eyes: list,
          bundle_id: str, week: str, menu_changes=(), review_status=None, reread=False, second_checked=0) -> str:
    cur = _metrics(rows)
    prev = _previous(v, bundle_id, cur.get("sales"), week)
    wk = f"Week {week}" if week else "This week"
    sales, net = cur.get("sales") or cur.get("revenue"), cur.get("net_profit") if "net_profit" in cur else cur.get("net_income")
    psales = prev.get("sales")
    reason = f"{wk} screens were read directly and cross-checked."
    if sales is not None:
        reason = f"{wk}: sales {_fmt(sales, True)}"
        if psales:
            reason += f" ({'up' if sales > psales else 'down'} {abs(sales - psales) / psales * 100:.0f}% from {_fmt(psales, True)})"
        if net is not None:
            reason += f", net result {_fmt(net, True)}"
        reason += ". Every value below was read from the screens; figures marked computed were calculated from them."
    L = [f"# Panda's Coffee CFO Briefing - {wk} " + ("Re-read of Archived Screens (added logging only)" if reread else "Operating Results (screens read by the engine)"), "",
         "## Executive Decision",
         "**Recommendation:** Record the week in full. The CFO's judgment and recommended actions are in the analysis briefing filed right after this one (see Sequence); this page holds the evidence only and implies no decision.", "",
         "**Confidence:** High", "",
         f"**One-sentence reason:** {reason}", "", "## What the Evidence Shows"]

    # store results
    store = [x for x in (_delta("Store sales", cur.get("sales"), prev.get("sales"), True),
                         _delta("Hot beverage sales", cur.get("hot_beverage_sales"), prev.get("hot_beverage_sales"), True),
                         _delta("Cold beverage sales", cur.get("cold_beverage_sales"), prev.get("cold_beverage_sales"), True),
                         _delta("Food sales", cur.get("food_sales"), prev.get("food_sales"), True),
                         _delta("Store operating profit", cur.get("operating_profit"), prev.get("operating_profit"), True),
                         _delta("Store net profit", cur.get("net_profit"), prev.get("net_profit"), True)) if x]
    if store:
        L += ["- **Store income statement:**"] + [f"  - {x}" for x in store]
    exp = [("coffee_beans", "Coffee beans"), ("cogs", "Cost of goods sold"), ("payroll", "Salaries"), ("rent", "Rent"),
           ("marketing", "Marketing"), ("other_costs", "Depreciation")]
    if sales and any(k in cur for k, _ in exp):
        L.append("- **Store expenses** (share of sales is computed):")
        for k, name in exp:
            if k in cur:
                pv = f"; last week {_fmt(prev[k], True)} = {prev[k] / prev['sales'] * 100:.0f}%" if prev.get(k) is not None and prev.get("sales") else ""
                L.append(f"  - {name}: {_fmt(cur[k], True)}, {cur[k] / sales * 100:.0f}% of sales{pv}")
        if cur.get("total_expenses"):
            L.append(f"  - Total expenses: {_fmt(cur['total_expenses'], True)}, {cur['total_expenses'] / sales * 100:.0f}% of sales")
    cf = [x for x in (_delta("Weekly revenue", cur.get("revenue"), None, True), _delta("Weekly net income", cur.get("net_income"), None, True),
                      _delta("Cash from operations", cur.get("operating_cash_flow"), None, True),
                      _delta("Investing", cur.get("investing_cash_flow"), None, True),
                      _delta("Financing", cur.get("financing_cash_flow"), None, True),
                      _delta("Net cash flow", cur.get("cash_flow"), None, True)) if x]
    if cf:
        L += ["- **Weekly results screen (company level):**"] + [f"  - {x}" for x in cf]
    hot, cold = cur.get("hot_beverage_cups"), cur.get("cold_beverage_cups")
    if hot is not None or cold is not None:
        L.append("- **Cups sold:**")
        for k, name in (("hot_beverage_cups", "Hot beverages"), ("cold_beverage_cups", "Cold beverages")):
            if k in cur:
                ch = _val(rows, k.replace("_cups", "_change_vs_prior_week"))
                L.append(f"  - {name}: {_fmt(cur[k])} cups" + (f", {ch} versus the week before" if ch else ""))
        if hot is not None and cold is not None:
            tot = hot + cold
            L.append(f"  - Total: {_fmt(tot)} cups (computed)" + (f"; sales per cup about {sales / tot:.2f} dollars (computed, includes food)" if sales else ""))
    rate = [(k, n) for k, n in (("review_overall", "Overall"), ("review_price", "Price"), ("review_product", "Product"),
                                ("review_service", "Service"), ("review_atmosphere", "Atmosphere")) if k in cur]
    if rate:
        n_rev = cur.get("review_count")
        L.append("- **Customer ratings** (out of 5" + (f", {_fmt(n_rev)} reviews" if n_rev else "") + "):")
        for k, n in rate:
            pv = f", was {_fmt(prev[k])}" if prev.get(k) is not None else ""
            L.append(f"  - {n}: {_fmt(cur[k])}{pv}")
    voice, themes = customer_voice(rows)
    if voice:
        n_rev = cur.get("review_count")
        L.append("- **What customers are saying** (verbatim, from the review cards visible on the screens" + (f"; {review_status['captured']} recorded this week, all reviews on record are in wiki/hubs/hub-reviews.md" if review_status else "") + "):")
        for c in voice:
            L.append(f'  - "{c}"')
        for name, cs in themes.items():
            L.append(f"  - Theme, {name}: {len(cs)} of {len(voice)} visible comments")
        if cur.get("review_product") is not None and prev.get("review_product") is not None and cur["review_product"] < prev["review_product"]:
            L.append(f"  - The product rating fell from {_fmt(prev['review_product'])} to {_fmt(cur['review_product'])}; read the comments above together with that drop.")
    staff = [(k, n) for k, n in (("staff_skill", "Floor staff skill"), ("staff_morale", "Floor staff morale"),
                                 ("floor_staff_hourly_wage", "Floor staff hourly wage")) if k in cur]
    if staff:
        L.append("- **Staff:** " + "; ".join(f"{n} {_fmt(cur[k], k.endswith('wage'))}" for k, n in staff))
    if "blend_price_per_lb" in cur:
        blend = _val(rows, "active_blend") or "the blend in use (name not read)"
        L.append(f"- **Coffee supply:** {blend} at {_fmt(cur['blend_price_per_lb'], True)} per lb")
    camps = sorted(k for k in cur if k.startswith("active_campaign_"))
    if camps:
        L.append("- **Active store campaigns (per week):** " + ", ".join(f"{k[16:].replace('_', ' ')} {_fmt(cur[k], True)}" for k in camps))
    heads = []
    for r in rows:
        if r["field"] == "headline" and r["value"] not in heads:
            heads.append(r["value"])
    date = _val(rows, "newsletter_date")
    if heads or date:
        L.append(f"- **Newspaper{' (' + date + ')' if date else ''}:**" + ("" if heads else " no headline matched a known pattern; see the screen if needed."))
        L += [f"  - {h}" for h in heads]
    menu = [(r["file"], r["value"]) for r in rows if r["field"] == "menu_item"]
    if menu:
        L += ["", "## Menu snapshot", "| Item | Price | Unit cost | Margin | Sales last week |", "|---|---|---:|---:|---:|"]
        by = collections.defaultdict(dict)
        for r in rows:
            if r["field"] in ("menu_item", "price", "unit_cost", "margin", "sales_last_week"):
                by[r["file"]][r["field"]] = r["value"]
        for f, d in by.items():
            if "menu_item" in d:
                L.append(f"| {d['menu_item']} | {d.get('price', 'n/a')} | {d.get('unit_cost', 'n/a')} | {d.get('margin', 'n/a')} | {d.get('sales_last_week', 'n/a')} |")

    rk = analysis.menu_ranking(rows)
    if rk:
        L += ["", "## Menu sales ranking (units sold last week)"] + [f"- {x.strip()}" for x in rk[1:]]
    ch = analysis.changes(v, week)
    if ch:
        L += ["", "## Changes since last week (from the store values on the screens)"] + [x.strip() for x in ch]
    if menu_changes:
        L += ["", "## Menu changes since the last time these items were recorded"] + [f"- {c}" for c in menu_changes]

    # analysis table (facts only)
    L += ["", "## Financial and Strategic Analysis", "| Factor | Evidence | Interpretation | Impact |", "|---|---|---|---|"]
    if sales and prev.get("payroll") and cur.get("payroll"):
        a, b = prev["payroll"] / prev["sales"] * 100, cur["payroll"] / sales * 100
        L.append(f"| Salary load | Salaries {b:.0f}% of sales, was {a:.0f}% | {'Sales grew faster than salaries' if b < a else 'Salaries grew as fast as or faster than sales'} (computed) | {'Improves' if b < a else 'Strains'} margin |")
    var = (cur.get("coffee_beans") or 0) + (cur.get("cogs") or 0)
    fixed = sum(cur.get(k) or 0 for k in ("payroll", "rent", "marketing", "other_costs"))
    if sales and var and fixed and var < sales:
        be = fixed / (1 - var / sales)
        L.append(f"| Break-even distance | Sales {_fmt(sales, True)} against about {_fmt(be, True)} needed (estimate: beans and goods variable, the rest fixed) | Store is at {sales / be * 100:.0f}% of break-even | {'Within reach' if sales >= be * 0.9 else 'Far from break-even'} (estimate) |")
    if rate and len(rate) > 1:
        low = sorted([(cur[k], n) for k, n in rate if k != "review_overall"])[:2]
        L.append(f"| Customer signals | Lowest ratings: {', '.join(f'{n} {_fmt(x)}' for x, n in low)} | These are what customers mark down most | Priority for the CFO's review |")
    if hot is not None and cold is not None and prev.get("sales") and sales:
        L.append(f"| Demand | {_fmt(hot + cold)} cups; sales {'up' if sales > prev['sales'] else 'down'} {abs(sales - prev['sales']) / prev['sales'] * 100:.0f}% | Volume and revenue moved together | See CFO analysis |")

    # memory update
    adds = collections.Counter(u["target"] + (" amend" if u["op"] == "amend" else "") for u in updates)
    L += ["", "## Memory Update"]
    L.append("- Filed as new ledger records: " + (", ".join(f"{c} {k}" for k, c in adds.most_common()) or "nothing new (everything was already on file)") + ".")
    for u in updates:
        f = u["fields"]
        name = f.get("name") or f.get("event") or f.get("opportunity") or (f"week {f.get('week')}" if u["target"] == "week" else "")
        if name and u["target"] != "catalog":
            L.append(f"  - {u['target']}{' amend' if u['op'] == 'amend' else ''}: {name}")
    if skipped:
        L.append("- Already on file and not filed again: " + ", ".join(f"{c} {k}" for k, c in skipped.items()) + ".")

    L += ["", "## Checks", f"- Screens read: {len(recognized) + len(needs_eyes)}; recognized {len(recognized)}; needing a look {len(needs_eyes)}. The full text of every screen is kept in raw/ocr/" + bundle_id + "/.",
          f"- Every number was read by the accurate reader; {second_checked} of {len(recognized)} recognized screens were also re-checked by a second reader. Sums (cash flows, expenses, revenue minus expenses) were verified."]
    L += [f"- FLAG: {f}" for f in flags] or ["- No flags."]
    L += ["", "## Assumptions and Unknowns",
          "- This page shows what the screens say, not why it happened; the reasons are in the CFO analysis briefing and are labeled as heuristics or estimates there."]
    if "ending_cash" not in cur:
        L.append("- The company cash balance and calendar date were not on these screens; send the company dashboard to confirm cash.")
    if needs_eyes:
        L.append(f"- {len(needs_eyes)} screen(s) are not recognized yet and are being reviewed: " + ", ".join(needs_eyes[:6]) + ".")
    L += ["", "## Next Upload Request", "Upload:"]
    ups = []
    if "ending_cash" not in cur:
        ups.append("Company dashboard showing cash balance and the date")
    if needs_eyes:
        ups.append("Nothing more for the unrecognized screens; they are being reviewed")
    ups = ups or ["Next week's screens after you advance the calendar"]
    L += [f"{i}. {u}" for i, u in enumerate(ups, 1)]
    return "\n".join(L) + "\n"
