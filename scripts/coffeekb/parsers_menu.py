"""Menu item screens: price, unit cost, margin and sales last week."""
from __future__ import annotations

import re

from .screens_core import (LOW_CONF, Doc, Parsed, is_money, row, _find, _store_name)

_FOOD = {"muffin", "donuts", "loaf cake", "spring water"}


def menu_group(name: str) -> str:
    """hot drink, cold drink or food, from the item name (the game's HOT / COLD / FOOD tabs)."""
    n = name.lower()
    if n in _FOOD:
        return "food"
    if n.startswith("iced") or "cold brew" in n or "frappe" in n:
        return "cold"
    return "hot"


def parse_menu_item(d: Doc) -> Parsed:
    p = Parsed("menu_item")
    F = d.file
    L = d.lines
    name_l = next((l for l in sorted(L, key=lambda l: l.y) if 1200 <= l.y <= 1420 and l.h >= 42 and l.x > 300), None)
    unit = next((re.search(r"\$[\d.]+", l.t) for l in L if l.t.startswith("Unit Cost") and re.search(r"\$[\d.]+", l.t)), None)
    price_lab = _find(L, "PRICE")
    price = next((l for l in sorted(L, key=lambda l: l.y) if is_money(l.t) and price_lab and l.y > price_lab.y and 500 <= l.cx <= 1000), None)
    margin = next((l for l in L if re.fullmatch(r"\d+%", l.t)), None)
    if not (name_l and price):
        p.flags.append(f"menu screen {F.split('/')[-1]}: name or price not found")
        return p
    p.rows += [row(F, "menu_item", name_l.t, "", name_l.c), row(F, "price", price.t, "USD", price.c)]
    if unit:
        p.rows.append(row(F, "unit_cost", unit.group(0), "USD"))
    if margin:
        p.rows.append(row(F, "margin", margin.t, "percent", margin.c))
    sales_lab = _find(L, "SALES LAST WEEK")
    if sales_lab:
        sv = min((l for l in L if re.fullmatch(r"[\d,]+", l.t) and l.h >= 50 and l.y > sales_lab.y and l.y < sales_lab.y + 200 and abs(l.cx - sales_lab.cx) < 300),
                 key=lambda l: abs(l.cx - sales_lab.cx), default=None)
        if sv:
            p.rows.append(row(F, "sales_last_week", sv.t.replace(",", ""), "units", sv.c))
            ch = next((l for l in L if re.match(r"[+-]?[\d,]+ \(", l.t) and l.y > sv.y and l.y < sv.y + 200), None)
            if ch:
                p.rows.append(row(F, "sales_change", ch.t.rstrip(")") + ")", "units", ch.c))
    p.rows.append(row(F, "item_group", menu_group(name_l.t)))
    store = _store_name(d)
    if store:
        p.rows.append(row(F, "store", store))
    fields = {"category": "menu", "name": name_l.t, "cost": unit.group(0) if unit else price.t, "price": price.t}
    if unit:
        fields["unit_cost"] = unit.group(0)
    if margin:
        fields["margin"] = margin.t
    p.conf = min(price.c, name_l.c)
    p.facts = fields
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]], "fields": fields})
    return p
