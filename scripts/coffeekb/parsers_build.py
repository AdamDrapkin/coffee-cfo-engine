"""Build-store screens, staff hiring, marketing options, supplier blends."""
from __future__ import annotations

import re

from .screens_core import (LOW_CONF, Doc, Parsed, is_money, money_val, slug, row, _find, _row_value, _center)

def parse_cost_summary(d: Doc) -> Parsed:
    p = Parsed("cost_summary")
    F = d.file
    labels = ("Exterior", "Interior", "Espresso Machine", "Brewer", "Blender", "Security Deposit", "Total Cost")
    got = {}
    for lab_text in labels:
        lab = _find(d.lines, lab_text)
        if lab:
            v = _row_value(d.lines, lab)
            if v:
                got[slug(lab_text)] = v
                p.rows.append(row(F, slug(lab_text), v.t, "USD", v.c))
                p.conf = min(p.conf, v.c)
    avail = next((l for l in d.lines if l.t.startswith("Available Cash")), None)
    if avail:
        m = re.search(r"\$[\d,]+(?:\.\d+)?", avail.t)
        if m:
            p.rows.append(row(F, "available_cash", m.group(0), "USD", avail.c))
    if "total_cost" in got:
        parts = sum(money_val(v.t) for k, v in got.items() if k != "total_cost")
        if abs(parts - money_val(got["total_cost"].t)) > 0.5:
            p.flags.append(f"cost summary parts add to {parts:,.0f} but the total reads {got['total_cost'].t}")
        p.updates.append({"target": "capital-allocation", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                          "evidence": [F.split("/")[-1]],
                          "fields": {"opportunity": "Store buildout (cost summary as shown)", "type": "store buildout",
                                     "required_cash": got["total_cost"].t.lstrip("+")}})
    p.facts = {k: v.t for k, v in got.items()}
    return p


def parse_option(d: Doc) -> Parsed:
    p = Parsed("option_card")
    modal = next(l for l in d.lines if l.x <= 110 and l.y > 850 and l.t in ("EXTERIOR", "INTERIOR"))
    cat = modal.t.lower()
    below = [l for l in _center(d.lines, 180, 760) if l.y > modal.y + 250]
    price = next((l for l in sorted(below, key=lambda l: l.y) if is_money(l.t) or l.t in ("-", "—", "–")), None)
    design_own = any("DESIGN OWN" in l.t.upper() for l in d.lines)
    if not price and design_own:
        names = [l for l in below if l.h >= 20 and not is_money(l.t) and "DESIGN" not in l.t.upper() and "SELECT" not in l.t.upper()]
        if names:
            F = d.file
            name = max(names, key=lambda l: l.y).t
            p.rows += [row(F, f"{cat}_name", name), {"file": F.split("/")[-1], "field": f"{cat}_cost", "value": "not_shown", "unit": "USD", "confidence": "High", "unreadable": False}]
            p.facts = {"category": cat, "name": name, "cost": "not_shown"}
            p.updates.append({"target": "catalog", "op": "append", "confidence": "High", "evidence": [F.split("/")[-1]],
                              "fields": {"category": cat, "name": name, "cost": "not_shown", "notes": "Design your own option; price shown as a dash"}})
            return p
    if not price:
        p.flags.append(f"{cat} card on {d.file.split('/')[-1]}: no price found")
        return p
    names = [l for l in below if l.y < price.y and price.y - l.y < 150 and not is_money(l.t)]
    if not names:
        p.flags.append(f"{cat} card on {d.file.split('/')[-1]}: no name found")
        return p
    name = max(names, key=lambda l: l.y).t
    F = d.file
    cost = price.t if is_money(price.t) else "not_shown"
    p.rows += [row(F, f"{cat}_name", name, "", price.c), row(F, f"{cat}_cost", cost if cost != "not_shown" else "not_shown", "USD", price.c)]
    if cost == "not_shown":
        p.rows[-1]["value"] = "not_shown"
    p.conf = min(price.c, 1.0)
    p.facts = {"category": cat, "name": name, "cost": cost}
    fields = {"category": cat, "name": name, "cost": cost}
    if cost == "not_shown":
        fields["notes"] = "Design your own option; price shown as a dash"
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]], "fields": fields})
    return p


def parse_equipment(d: Doc) -> Parsed:
    p = Parsed("equipment_card")
    F = d.file
    title = next(l for l in d.lines if l.x <= 110 and l.y > 850 and l.t in ("ESPRESSO MACHINE", "BREWER", "BLENDER", "GRINDER"))
    kind = title.t.lower()
    ctr = _center(d.lines, 250, 800)
    qlab = _find(ctr, "QUALITY")
    price_lab = _find(ctr, "PRICE")
    if not (qlab and price_lab):
        p.flags.append(f"{kind} card on {F.split('/')[-1]} is missing its labels")
        return p
    body = [l for l in ctr if title.y + 150 < l.y < qlab.y - 15]
    body.sort(key=lambda l: l.y)
    if not body:
        p.flags.append(f"{kind} card on {F.split('/')[-1]}: no name found")
        return p
    name_line = max(body[:2], key=lambda l: l.h)
    desc = " ".join(l.t for l in body if l is not name_line and l.y > name_line.y)
    price = next((l for l in sorted(ctr, key=lambda l: l.y) if is_money(l.t) and l.y > price_lab.y), None)
    if not price:
        p.flags.append(f"{kind} {name_line.t}: no price found")
        return p
    stars = {s["label"]: s["filled"] for s in d.stars if 250 <= s["x"] <= 800}
    q, pr = stars.get("QUALITY"), stars.get("PRODUCTIVITY")
    name = name_line.t
    p.rows += [row(F, f"{kind}_name", name, "", name_line.c), row(F, f"{kind}_price", price.t, "USD", price.c)]
    if q is not None:
        p.rows.append(row(F, f"{kind}_quality", f"{q} of 5 stars", "stars"))
    if pr is not None:
        p.rows.append(row(F, f"{kind}_productivity", f"{pr} of 5 stars", "stars"))
    p.conf = min(price.c, name_line.c)
    fields = {"category": "equipment", "name": name, "cost": price.t, "equipment_type": kind, "notes": desc}
    if q is not None:
        fields["quality"] = str(q)
    if pr is not None:
        fields["productivity"] = str(pr)
    p.facts = fields
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]], "fields": fields})
    return p


def parse_manager(d: Doc) -> Parsed:
    p = Parsed("manager_card")
    F = d.file
    L = d.lines
    head = next(l for l in L if l.t.upper() == "HIRE STORE MANAGER")
    staff_lab = _find(L, "STAFF EXPERIENCES")
    mgr_lab = _find(L, "MANAGER EXPERIENCES")
    ctr = _center(L, 380, 900)
    if not staff_lab:
        p.flags.append(f"manager card on {F.split('/')[-1]} has no experience labels")
        return p
    names = [l for l in ctr if head.y + 150 < l.y < staff_lab.y - 20 and l.h >= 45]
    name = max(names, key=lambda l: l.h).t if names else ""
    months = [l for l in ctr if re.fullmatch(r"\d+ months", l.t)]
    staff_m = next((l for l in sorted(months, key=lambda l: l.y) if l.y > staff_lab.y), None)
    mgr_m = next((l for l in sorted(months, key=lambda l: l.y) if mgr_lab and l.y > mgr_lab.y), None)
    skills = {}
    for sk in ("People", "Product", "Marketing", "Ethics"):
        lab = next((l for l in ctr if l.t == sk), None)
        if lab:
            val = [l for l in L if l.t.isdigit() and 860 <= l.cx <= 1010 and abs(l.cy - lab.cy) <= 24]
            if val:
                skills[sk.lower()] = val[0].t
    sal_lab = _find(L, "CURRENT SALARY")
    salary = next((l for l in sorted(ctr, key=lambda l: l.y) if is_money(l.t) and sal_lab and l.y > sal_lab.y), None)
    if not (name and salary and len(skills) == 4):
        p.flags.append(f"manager card on {F.split('/')[-1]} is incomplete (name {name or '?'}, skills {len(skills)} of 4, salary {'ok' if salary else 'missing'})")
        return p
    p.rows += [row(F, "manager_name", name), row(F, "manager_annual_salary", salary.t, "USD", salary.c)]
    if staff_m:
        p.rows.append(row(F, "staff_experience", staff_m.t, "months"))
    if mgr_m:
        p.rows.append(row(F, "manager_experience", mgr_m.t, "months"))
    for k, v in skills.items():
        p.rows.append(row(F, f"manager_{k}", v, "score"))
    notes = f"Staff {staff_m.t if staff_m else 'not_shown'}, manager {mgr_m.t if mgr_m else 'not_shown'}; " + ", ".join(f"{k.title()} {v}" for k, v in skills.items())
    p.conf = min(salary.c, 1.0)
    p.facts = {"name": name, "cost": salary.t, "notes": notes}
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]],
                      "fields": {"category": "staff", "name": name, "cost": salary.t, "notes": notes}})
    return p


def parse_marketing(d: Doc) -> Parsed:
    p = Parsed("marketing_option")
    F = d.file
    L = d.lines
    head = next(l for l in L if l.x <= 110 and 1200 <= l.y <= 1350 and l.t.isupper())
    cost = next((l for l in L if (is_money(l.t) or re.fullmatch(r"\d+(\.\d+)?%", l.t)) and l.h >= 55 and l.y > 2000), None)
    unit = next((l for l in L if re.match(r"(per |of revenue)", l.t) and l.y > 2100), None)
    option = next((l for l in sorted(L, key=lambda l: l.y) if 2330 <= l.y <= 2470 and l.h >= 38 and 350 <= l.cx <= 950
                   and not l.t.startswith(("→", "←"))), None)
    desc = " ".join(l.t for l in sorted(L, key=lambda l: l.y) if l.x <= 110 and 2120 <= l.y <= 2340 and not is_money(l.t))
    if not cost:
        p.flags.append(f"marketing screen '{head.t}' on {F.split('/')[-1]}: no cost found")
        return p
    name = head.t.title() + (f" {option.t}" if option and option.t.lower() != head.t.lower() else "")
    unit_t = unit.t if unit else "not_shown"
    p.rows += [row(F, "campaign", head.t.title()), row(F, "cost", cost.t, "USD", cost.c), row(F, "cost_unit", unit_t)]
    if option:
        p.rows.append(row(F, "option", option.t, "", option.c))
    p.conf = cost.c
    fields = {"category": "marketing", "name": name, "cost": cost.t.lstrip("+"), "cost_unit": unit_t, "notes": desc}
    p.facts = fields
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]], "fields": fields})
    return p


def parse_company_blend(d: Doc) -> Parsed:
    p = Parsed("company_blend")
    F = d.file
    L = d.lines
    name_l = next((l for l in sorted(L, key=lambda l: l.y) if 800 <= l.y <= 950 and l.h >= 45), None)
    price = next((l for l in L if is_money(l.t) and l.h >= 60 and 1150 <= l.y <= 1300), None)
    unit = next((l for l in L if l.t.startswith("per ") and 1250 <= l.y <= 1350), None)
    if not (name_l and price):
        p.flags.append(f"company blend screen {F.split('/')[-1]}: name or price not found")
        return p
    p.rows += [row(F, "blend", name_l.t, "", name_l.c), row(F, "blend_price", price.t, "USD", price.c)]
    p.facts = {"category": "menu", "name": name_l.t, "cost": price.t, "cost_unit": unit.t if unit else "not_shown"}
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if price.c >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]],
                      "fields": {"category": "menu", "name": f"Company blend: {name_l.t}", "cost": price.t,
                                 "cost_unit": unit.t if unit else "not_shown"}})
    return p


def parse_overview(d: Doc) -> Parsed:
    p = Parsed("build_overview")
    for cat in ("EXTERIOR", "INTERIOR"):
        lab = _find(d.lines, cat)
        val = next((l for l in d.lines if lab and is_money(l.t) and abs(l.cx - lab.cx) < 200 and l.y > lab.y), None)
        if val:
            p.rows.append(row(d.file, f"default_{cat.lower()}_cost", val.t, "USD", val.c))
    return p


def parse_roaster_blend(d: Doc) -> Parsed:
    """A supplier's packaged blend card: name and price are text. The flavor icon (aroma, flavor, acidity, bitterness, body) is a picture,
    so the screen is also flagged for an image look; the price is filed now."""
    p = Parsed("roaster_blend")
    F, L = d.file, d.lines
    supplier = next((l.t for l in L if 180 <= l.y <= 320 and re.search(r"[A-Za-z]{4}", l.t) and "roaster" not in l.t.lower()), "")
    blend = next((l for l in L if 1750 <= l.y <= 2050 and l.t.lower().endswith("blend") and l.x > 300 and l.h < 45 and not l.t.upper().startswith("BUY")), None)
    price = next((l for l in L if is_money(l.t) and l.h >= 55 and 2000 <= l.y <= 2300), None)
    unit = next((l.t for l in L if l.t.startswith("per ") and 2100 <= l.y <= 2300), "per lb")
    default = next((l for l in L if is_money(l.t) and l.y > 2500), None)
    if not (blend and price):
        p.flags.append(f"{F.split('/')[-1]}: roaster screen without a readable blend name or price")
        return p
    name = f"{'Pacific Coffee' if 'pacific' in supplier.lower() else supplier} {blend.t}".strip()
    p.rows += [row(F, "blend", name), row(F, "blend_price_per_lb", price.t, "USD per lb", price.c)]
    if default:
        p.rows.append(row(F, "default_blend_price_per_lb", default.t, "USD per lb", default.c))
    p.conf = price.c
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate", "evidence": [F.split("/")[-1]],
                      "fields": {"category": "supply", "name": name, "cost": price.t, "cost_unit": unit,
                                 "notes": "Packaged blend from the supplier screen. Flavor icon (aroma, flavor, acidity, bitterness, body) not yet read."}})
    p.flags.append(f"{F.split('/')[-1]}: {name} price read; its flavor icon is a picture and needs an image look")
    return p
