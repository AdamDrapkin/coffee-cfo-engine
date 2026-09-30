"""Store screens: income statement, cups, reviews, staff, campaigns, blend in use."""
from __future__ import annotations

import re

from .screens_core import (LOW_CONF, Doc, Parsed, is_money, money_val, slug, row, _find, _num, _store_name)

def parse_income_statement(d: Doc, default_week: str = "") -> Parsed:
    """Store income statement. The first value column (x 850 to 1000) is the current week; the second is the change."""
    p = Parsed("income_statement")
    F, L = d.file, d.lines
    store = _store_name(d)
    date = next((l.t for l in L if 850 <= l.x <= 960 and re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}", l.t) and l.y > 700 and l.h >= 30), "")
    p.week = default_week
    labels = {"Hot Beverage": "hot_beverage_sales", "Cold Beverage": "cold_beverage_sales", "Foods": "food_sales",
              "Total Revenues": "sales", "Coffee Beans": "coffee_beans", "Cost of Goods Sold": "cogs", "Rent": "rent",
              "Salaries": "payroll", "Depreciation": "other_costs", "Marketing": "marketing",
              "Administrative Cost": "administrative_cost", "Total Expenses": "total_expenses",
              "OPERATING INCOME": "operating_profit", "City Tax": "city_tax", "Recycling Tax": "recycling_tax",
              "Sugar Tax": "sugar_tax", "NET INCOME": "net_profit"}
    vals = {}
    for lab in L:
        key = labels.get(lab.t) or labels.get(lab.t.title() if lab.t.isupper() else lab.t)
        if not key or lab.x > 200 or lab.y < 800:
            continue
        v = next((l for l in sorted(L, key=lambda l: l.x) if abs(l.cy - lab.cy) <= 28 and 840 <= l.x <= 1000 and _num(l.t)), None)
        if v:
            vals[key] = v
    for key, l in vals.items():
        p.rows.append(row(F, key, l.t, "USD", l.c))
        p.conf = min(p.conf, l.c)
    if date:
        p.rows.append(row(F, "statement_column", date))
    if store:
        p.rows.append(row(F, "store", store))
    if all(k in vals for k in ("sales", "total_expenses", "operating_profit")):
        calc = money_val(vals["sales"].t) - money_val(vals["total_expenses"].t)
        if abs(calc - money_val(vals["operating_profit"].t)) > 1.5:
            p.flags.append(f"income statement {F.split('/')[-1]}: revenue minus expenses is {calc:,.0f} but operating income reads {vals['operating_profit'].t}")
    if "sales" in vals and "total_expenses" in vals and store:
        fields = {"name": store, "week": p.week or "", **{k: re.sub(r"[$,]", "", l.t) for k, l in vals.items() if k != "total_expenses"}}
        fields["total_expenses"] = re.sub(r"[$,]", "", vals["total_expenses"].t)
        p.facts = dict(fields)
        p.updates.append({"target": "store", "op": "amend", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                          "evidence": [F.split("/")[-1]], "fields": fields,
                          "reason": f"Income statement column {date or 'shown'} read from the store screen."})
    elif vals:
        p.flags.append(f"{F.split('/')[-1]}: top of the income statement only (revenue lines); the expense part is on another screen")
    return p


def parse_store_performance(d: Doc) -> Parsed:
    p = Parsed("store_performance")
    F, L = d.file, d.lines
    store = _store_name(d)
    for lab, key in (("HOT BEVERAGE", "hot_beverage_cups"), ("COLD BEVERAGE", "cold_beverage_cups")):
        l0 = _find(L, lab)
        cand = [l for l in L if l0 and re.fullmatch(r"[\d,]+( cups)?", l.t) and l.h >= 40 and abs(l.cx - l0.cx) < 320 and l.y > l0.y and l.y < l0.y + 200]
        v = min(cand, key=lambda l: abs(l.cx - l0.cx), default=None)
        if v:
            p.rows.append(row(F, key, v.t.replace(" cups", "").replace(",", ""), "cups", v.c))
            chg = next((l for l in L if re.match(r"[+-][\d,]+ \(", l.t) and abs(l.cx - l0.cx) < 260 and l.y > v.y), None)
            if chg:
                p.rows.append(row(F, key.replace("_cups", "_change_vs_prior_week"), chg.t.rstrip(")") + ")", "", chg.c))
    if store:
        p.rows.append(row(F, "store", store))
    if any(l.t.upper() == "COMPANY BLEND" for l in L):      # the same screen shows the blend in use
        p.rows += [r for r in parse_store_blend(d).rows if r["field"] in ("active_blend", "blend_price_per_lb")]
    if not p.rows:
        p.flags.append(f"{F.split('/')[-1]}: performance screen with no readable cup counts")
    return p


def review_comments(d: Doc) -> list:
    """The review cards under the ratings: text boxes grouped by card (two columns) and by line spacing."""
    L = d.lines
    n = next((l for l in L if re.fullmatch(r"\d+ reviews?", l.t)), None)
    top = (n.y + 120) if n else 1400
    end = next((l.y for l in L if l.t.upper() in ("STORE MANAGER", "MANAGER SKILLS") and l.y > top), 2450)
    out = []
    for lo, hi in ((0, 700), (700, 1300)):
        col = sorted([l for l in L if top <= l.y < end - 40 and lo <= l.x < hi and l.h < 45 and len(l.t) > 3
                      and not is_money(l.t) and not re.fullmatch(r"[\d.]+", l.t)], key=lambda l: l.y)
        card, last = [], None
        for l in col:
            if last is not None and l.y - last > 75:
                out.append(" ".join(card)); card = []
            card.append(l.t); last = l.y
        if card:
            out.append(" ".join(card))
    fixed = []
    for t in out:
        t = re.sub(r"I['’]Il\b", "I'll", t).replace("\u2019", "'")
        t = re.sub(r"\bl\b", "I", t)
        if len(t.split()) >= 3 and t not in fixed:
            fixed.append(t)
    return fixed


def parse_customer_reviews(d: Doc) -> Parsed:
    p = Parsed("customer_reviews")
    F, L = d.file, d.lines
    overall = next((l for l in L if re.fullmatch(r"\d\.\d", l.t) and l.h >= 60), None)
    if overall:
        p.rows.append(row(F, "review_overall", overall.t, "stars", overall.c))
    for cat in ("Price", "Product", "Service", "Atmosphere"):
        lab = next((l for l in L if l.t == cat and l.y > 1300 and l.x > 600), None)
        v = next((l for l in L if lab and re.fullmatch(r"\d\.\d", l.t) and abs(l.cy - lab.cy) <= 24 and l.x > lab.x), None)
        if v:
            p.rows.append(row(F, f"review_{cat.lower()}", v.t, "stars", v.c))
    for lab, key in (("Staff Skill", "staff_skill"), ("Staff Morale", "staff_morale")):
        l0 = next((l for l in L if l.t == lab), None)
        v = next((l for l in L if l0 and l.t.isdigit() and abs(l.cy - l0.cy) <= 30 and l.x > l0.x), None)
        if v:
            p.rows.append(row(F, key, v.t, "score", v.c))
    if _find(L, "FLOOR STAFF"):
        cnt = next((l for l in L if re.fullmatch(r"\d{1,3}", l.t) and 200 <= l.x <= 340 and 780 <= l.y <= 880 and l.h < 60), None)
        if cnt:
            p.rows.append(row(F, "floor_staff_count", cnt.t, "staff", cnt.c))
    if _find(L, "HOURLY SALARY"):
        wage = next((l for l in L if re.fullmatch(r"\$\d+(\.\d\d)?", l.t) and 750 <= l.y <= 950), None)
        if wage:
            p.rows.append(row(F, "floor_staff_hourly_wage", wage.t, "USD per hour", wage.c))
    ov = next((l for l in L if re.fullmatch(r"\d\.\d", l.t) and l.x < 120 and l.y > 1900), None)
    if ov and not any(r["field"] == "review_overall" for r in p.rows):
        p.rows.append(row(F, "review_overall", ov.t, "stars", ov.c))
    n = next((l for l in L if re.fullmatch(r"\d+ reviews?", l.t)), None)
    if n:
        p.rows.append(row(F, "review_count", n.t.split()[0]))
    store = _store_name(d)
    if store:
        p.rows.append(row(F, "store", store))
    for text in review_comments(d):
        p.rows.append(row(F, "review_comment", text))
    if len(p.rows) < 3:
        p.flags.append(f"{F.split('/')[-1]}: customer reviews screen not fully readable")
    return p


def parse_manager_detail(d: Doc) -> Parsed:
    """A hired manager's own screen (skills, salary, delegation). Recorded as extraction only; the hire card holds the catalog record."""
    p = Parsed("manager_detail")
    F, L = d.file, d.lines
    for sk in ("People", "Product", "Marketing", "Ethics"):
        lab = next((l for l in L if l.t == sk and 640 <= l.y <= 900), None)
        v = next((l for l in L if lab and l.t.isdigit() and abs(l.cy - lab.cy) <= 24 and l.x > 900), None)
        if v:
            p.rows.append(row(F, f"manager_{sk.lower()}", v.t, "score", v.c))
    sal = next((l for l in L if is_money(l.t) and 1050 <= l.y <= 1150 and l.h >= 40), None)
    if sal:
        p.rows.append(row(F, "manager_annual_salary", sal.t, "USD", sal.c))
    since = next((l for l in L if re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}, \d{4}", l.t)), None)
    if since:
        p.rows.append(row(F, "manager_since", since.t))
    if len(p.rows) < 5:
        p.flags.append(f"{F.split('/')[-1]}: manager screen not fully readable")
    return p


_CAMPAIGNS = (("free wifi", "free_wifi"), ("wifi", "free_wifi"), ("wi-fi", "free_wifi"), ("desk power strip", "desk_power_strip"), ("power strip", "desk_power_strip"),
              ("free music", "free_music"), ("buy 1 get 1", "buy_1_get_1_free"), ("recyclable cups", "recyclable_cups"), ("direct mail", "direct_mail"),
              ("catering", "catering"), ("community", "community_sponsors"), ("social media", "social_media"), ("local paid search", "local_paid_search"))
_STATES = ("on", "off", "faster speed", "regular speed", "fast speed", "standard speed")


def _board_states(L) -> list:
    """On/Off (or Wi-Fi speed) switches of the campaign board: small labels in the left or right column."""
    return [l for l in L if l.t.lower() in _STATES and l.h <= 45 and (l.x <= 220 or 700 <= l.x <= 820)]


def _parse_campaign_board(d: Doc, p: Parsed) -> Parsed:
    """The marketing campaigns board: each campaign has a name, a price per week and an On/Off switch (two columns).
    Only campaigns that are On are recorded, as active_campaign_<name> with their weekly price."""
    F, L = d.file, d.lines
    states = _board_states(L)
    seen = {}
    for s in states:
        right = s.x >= 600
        names = [(l, key) for l in L if (l.x >= 640) == right and s.y - 150 <= l.y <= s.y - 40
                 for frag, key in _CAMPAIGNS if frag in l.t.lower()]
        if not names:
            continue
        name, key = min(names, key=lambda nk: s.y - nk[0].y)
        if key in seen:
            continue
        on = s.t.lower() != "off"
        price = next((l for l in L if is_money(l.t) and abs(l.y - s.y) <= 45 and (l.x >= 640) == right and l.h >= 40), None)
        seen[key] = on
        if on and price:
            p.rows.append(row(F, f"active_campaign_{key}", price.t, "USD per week", price.c))
            if s.t.lower() not in ("on",):
                p.rows.append(row(F, f"campaign_option_{key}", s.t, "", s.c))
        elif on:
            p.flags.append(f"{F.split('/')[-1]}: campaign {key} is on but its price was not readable")
    if not seen:
        p.flags.append(f"{F.split('/')[-1]}: marketing board with no readable campaigns")
    return p



def parse_store_marketing(d: Doc) -> Parsed:
    """Active campaigns on the store screen: names with a per-week price under them."""
    p = Parsed("store_marketing")
    F, L = d.file, d.lines
    if _board_states(L):
        return _parse_campaign_board(d, p)
    y0 = next(l.y for l in L if l.t.upper() == "MARKETING CAMPAIGNS")
    prices = [l for l in L if is_money(l.t) and l.y > y0]
    for pr in prices:
        name = min((l for l in L if l.y > y0 and l.y < pr.y and abs(l.cx - pr.cx) < 260 and not is_money(l.t) and re.search(r"[A-Za-z]{3}", l.t)
                    and not l.t.startswith("per") and l.t not in ("On", "Off")), key=lambda l: pr.y - l.y, default=None)
        if name:
            p.rows.append(row(F, f"active_campaign_{slug(name.t)}", pr.t, "USD per week", pr.c))
    share = next((l for l in L if l.t.endswith("%") and 800 <= l.y <= 1500), None)
    if share:
        p.rows.append(row(F, "market_share", share.t, "%", share.c))
    if not p.rows:
        p.flags.append(f"{F.split('/')[-1]}: store marketing screen with no readable campaign prices")
    return p


def parse_store_blend(d: Doc) -> Parsed:
    """The blend currently in use on the store screen: its full name (default or a supplier's blend), price per lb and the chart start date."""
    p = Parsed("store_blend")
    F, L = d.file, d.lines
    head = next((l for l in L if l.t.upper() == "COMPANY BLEND"), None)
    aroma = next((l for l in L if l.t == "Aroma"), None)
    lo = (head.y + 40) if head else 1000
    hi = (aroma.y - 10) if aroma else lo + 500
    name_lines = sorted([l for l in L if lo <= l.y <= hi and l.x < 700 and re.search(r"[A-Za-z]{3}", l.t)
                         and not l.t.upper() in ("PRICE", "INVENTORY", "COMPANY BLEND")], key=lambda l: l.y)
    if any(l.x >= 200 for l in name_lines):          # a logo word at the far left is not part of the blend name
        name_lines = [l for l in name_lines if l.x >= 200]
    name = " ".join(l.t for l in name_lines[:2]).strip()
    price = next((l for l in L if is_money(l.t) and l.h >= 60 and l.x > 900 and lo <= l.y <= hi + 400), None)
    if name:
        p.rows.append(row(F, "active_blend", name))
    if price:
        p.rows.append(row(F, "blend_price_per_lb", price.t, "USD per lb", price.c))
    date = next((l.t for l in L if re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}", l.t) and l.x < 200), "")
    if date:
        p.rows.append(row(F, "chart_first_date", date))
    if not price:
        p.flags.append(f"{F.split('/')[-1]}: blend screen without a readable price")
    if not name:
        p.flags.append(f"{F.split('/')[-1]}: blend screen without a readable blend name, so a blend change cannot be detected")
    return p


def parse_review_detail(d: Doc) -> Parsed:
    """A screen that is about reviews but not the ratings summary: capture every review card's text.
    The per-review star layout has not been seen yet, so the first batch is flagged for a look against the text dump."""
    p = Parsed("review_detail")
    F = d.file
    L = d.lines
    cards = []
    for lo, hi in ((0, 650), (650, 1300)):
        col = sorted([l for l in L if 420 <= l.y <= 2560 and lo <= l.x < hi and l.h < 60 and len(l.t) > 3
                      and not is_money(l.t) and not re.fullmatch(r"[\d.]+", l.t) and l.t.upper() != l.t], key=lambda l: l.y)
        card, last = [], None
        for l in col:
            if last is not None and l.y - last > 80:
                cards.append(" ".join(card)); card = []
            card.append(l.t); last = l.y
        if card:
            cards.append(" ".join(card))
    seen = []
    for t in cards:
        t = re.sub(r"I['\u2019]Il\b", "I'll", t)
        t = re.sub(r"\bl\b", "I", t)
        if len(t.split()) >= 3 and t not in seen:
            seen.append(t)
    for t in seen:
        p.rows.append(row(F, "review_comment", t))
    store = _store_name(d)
    if store:
        p.rows.append(row(F, "store", store))
    p.flags.append(f"{F.split('/')[-1]}: review screen layout is new; text captured ({len(seen)} card(s)), check it against the text dump and the per-review stars")
    return p
