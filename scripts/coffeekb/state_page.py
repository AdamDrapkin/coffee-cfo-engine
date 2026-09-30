"""references/company-state.md: the current situation in one page, rewritten by the engine after every run.

The chat reads this first so it never has to explore the vault to learn what the company looks like today:
the setup (blend, wage, staff, campaigns), the weekly history, decisions and what the CEO did about them,
open unknowns and corrections in force. Everything here comes from the ledger; nothing is typed by hand.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import analysis, digest
from .ledger import ledger_dir
from .util import note_problem, atomic_write, today

SKILL = ".agents/skills/coffee-week"


def _num(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)))
    except ValueError:
        return None


def build(v: Path) -> str:
    L = ["# Company state (written by the engine after every run; do not edit)", "",
         f"Updated {today()}. Read this before analyzing. Anything not listed here is not recorded.", ""]
    hist = analysis._store_by_week(v)
    weeks = digest._merged_weeks(v)
    stores = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "stores")):
        n = str(fm.get("name") or "")
        stores.setdefault(n, {}).update({k: val for k, val in fm.items() if val not in (None, "")})
    L.append("## Current setup")
    for name, f in stores.items():
        L.append(f"- Store: {name}, {f.get('city', 'San Francisco')}. Exterior {f.get('exterior', '?')}, interior {f.get('interior', '?')}; "
                 f"espresso {f.get('espresso_machine', '?')}, brewer {f.get('brewer', '?')}, blender {f.get('blender', '?')}.")
        L.append(f"- Manager: {f.get('manager', 'not recorded')} (salary {f.get('manager_annual_salary', '?')} a year).")
    if hist:
        last = max(hist)
        h = hist[last]
        L.append(f"- Latest store values (week {last}): coffee blend {h.get('active_blend', 'not recorded')} at ${h.get('blend_price_per_lb', '?')} per lb; "
                 f"{h.get('floor_staff_count', '?')} floor staff at ${h.get('floor_staff_hourly_wage', '?')} an hour, skill {h.get('staff_skill', '?')}, morale {h.get('staff_morale', '?')}.")
        camps = sorted(k[16:].replace("_", " ") + f" ${h[k]}/week" for k in h if k.startswith("active_campaign_"))
        if camps:
            L.append("- Marketing campaigns on: " + ", ".join(camps) + ".")
    L.append("")
    L.append("## Weekly history (screen values; ratings are out of 5)")
    L.append("| Week | Revenue | Net income | Cash flow | Blend | Overall | Price | Product | Service | Atmosphere | Cups hot / cold |")
    L.append("|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|")
    keys = sorted((k for k in weeks if k.isdigit()), key=int)
    for wk in keys[-10:]:
        f = weeks[wk]["fields"]
        s = hist.get(int(wk), {})
        L.append(f"| {wk} | {f.get('revenue', '')} | {f.get('net_income', '')} | {f.get('cash_flow', '')} | {s.get('active_blend', '')} | "
                 f"{s.get('review_overall', '')} | {s.get('review_price', '')} | {s.get('review_product', '')} | {s.get('review_service', '')} | "
                 f"{s.get('review_atmosphere', '')} | {s.get('hot_beverage_cups', '')} / {s.get('cold_beverage_cups', '')} |")
    L.append("")
    from . import lookup
    mw = lookup.menu_weeks(v)
    sold = sorted(w for w, its in mw.items() if any(lookup._n(i.get("sales")) is not None for i in its))[-4:]
    if sold:
        L.append(f"## Menu: units sold last week per item, weeks {sold[0]} to {sold[-1]} (ask `sh scripts/run.sh facts <item>` for the full history)")
        L.append("| Item | Group | " + " | ".join(f"Wk {w}" for w in sold) + " | Price | Margin |")
        L.append("|---|---|" + "---:|" * len(sold) + "---:|---:|")
        latest = {i["name"]: i for i in mw[sold[-1]]}
        for name, it in sorted(latest.items(), key=lambda kv: (kv[1].get("group", ""), -(lookup._n(kv[1].get("sales")) or 0))):
            cells = []
            for w in sold:
                m = next((i for i in mw[w] if i["name"] == name), {})
                cells.append(str(m.get("sales", "")))
            L.append(f"| {name} | {it.get('group', '')} | " + " | ".join(cells) + f" | ${it.get('price')} | {it.get('margin')}% |")
        L.append("")
    dl = analysis.decisions_in_force(v, 8)
    L.append("## Decisions and what the CEO did")
    L += [x.strip() for x in dl] or ["- none recorded"]
    L.append("")
    from . import decisions
    L.append("## Open unknowns (confirm on the next screens; close one with `sh scripts/run.sh resolve <words> <note>`)")
    for r in decisions.open_unknowns(v)[-8:]:
        L.append(f"- {r[1]}: {r[2][:160]}")
    L.append("")
    L.append("## Corrections in force (these override anything older)")
    try:
        from . import corrections
        for _, fm in corrections.notes(v)[-8:]:
            L.append(f"- Not true: \"{str(fm.get('claim'))[:100]}\". True: {str(fm.get('correction'))[:200]}")
    except Exception as _e:
        note_problem(__name__, _e)
        pass
    L.append("")
    L.append("## Where the rest lives")
    L.append("- Every customer review on record: wiki/hubs/hub-reviews.md, and wiki/ledger/reviews/ (search by keyword).")
    L.append("- Every earlier analysis: wiki/briefings/ (files ending in -analysis). Numbers by week: wiki/ledger/weeks/. Store values by week: wiki/ledger/stores/.")
    L.append("- The full text of every screen ever read: raw/ocr/.")
    return "\n".join(L) + "\n"


def write(v: Path) -> None:
    d = v / SKILL / "references"
    if d.exists():
        atomic_write(d / "company-state.md", build(v))
