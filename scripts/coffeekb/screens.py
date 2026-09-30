"""Turn OCR text and star counts into typed facts, deterministically.

Each parser knows one screen layout of Coffee Inc. 2+ and lives in a parsers_* module. This module classifies a screen
and dispatches to the right parser. Screens no parser recognizes are reported as "other" and left for a person.
Nothing here calls an AI model.
"""
from __future__ import annotations

import re

from .screens_core import *  # noqa: F401,F403
from .screens_core import _find, _row_value, _center, _num, _store_name  # noqa: F401
from .parsers_news import *  # noqa: F401,F403
from .parsers_news import _newsletter_events, _events_updates, _clean_who, _DATE, _NAV, _CITY  # noqa: F401
from .parsers_build import *  # noqa: F401,F403
from .parsers_menu import *  # noqa: F401,F403
from .parsers_menu import _FOOD  # noqa: F401
from .parsers_store import *  # noqa: F401,F403
from .parsers_company import *  # noqa: F401,F403
from . import learned


def classify(d: Doc) -> str:
    up = [l.t.upper() for l in d.lines]
    has = lambda s: any(t == s for t in up)  # noqa: E731
    if has("WEEKLY RESULTS"):
        return "weekly_results"
    if has("MARKETING AGENCY") and any(re.fullmatch(r"\d+(\.\d+)?% of Marketing Spend", l.t.strip()) for l in d.lines):
        return "agency_contract"
    if has("COMPANIES") and has("QUARTERLY REVENUE"):
        return "company_board"
    if has("COST SUMMARY"):
        return "cost_summary"
    if has("HIRE STORE MANAGER"):
        return "manager_card"
    modal = [l for l in d.lines if l.x <= 110 and l.y > 850 and l.t.isupper() and 4 <= len(l.t) <= 30 and l.h >= 30]
    if any(l.t in ("EXTERIOR", "INTERIOR") for l in modal):
        return "option_card"
    if any(l.t in ("ESPRESSO MACHINE", "BREWER", "BLENDER", "GRINDER") for l in modal) and d.stars:
        return "equipment_card"
    if has("BUILD STORE") and has("EXTERIOR") and has("INTERIOR"):
        return "build_overview"
    head = any(l.x <= 110 and 1200 <= l.y <= 1350 and l.t.isupper() and l.h >= 34 for l in d.lines)
    big_cost = any((is_money(l.t) or re.fullmatch(r"\d+(\.\d+)?%", l.t)) and l.h >= 55 and l.y > 2000 for l in d.lines)
    per = any(re.match(r"(per week|per unit cost|of revenue|per unit)", l.t) and l.y > 2100 for l in d.lines)
    if head and big_cost and per:
        return "marketing_option"
    if has("PACKAGED BLENDS"):
        return "roaster_blend"
    if any(t == "STORE INCOME STATEMENT" for t in up):
        return "income_statement"
    if any(t == "CUSTOMER REVIEWS" for t in up):
        return "customer_reviews"
    if any(re.fullmatch(r"(\d+ )?reviews?", t, re.I) for t in (l.t for l in d.lines)) and not has("MANAGER SKILLS"):
        return "review_detail"
    if has("MANAGER SKILLS") and has("FIRE MANAGER"):
        return "manager_detail"
    if has("HOT BEVERAGE") and has("COLD BEVERAGE") and any(re.fullmatch(r"[\d,]+( cups)?", l.t) and l.h >= 60 and 750 <= l.y <= 900 for l in d.lines):
        return "store_performance"
    if sum(1 for l in d.lines if l.t.lower() in ("on", "off") and l.h <= 45) >= 3 and sum(1 for l in d.lines if l.t.startswith("per ")) >= 3 and not has("MARKET SHARES IN AREA"):
        return "store_marketing"
    if has("MARKETING CAMPAIGNS") and has("MARKET SHARES IN AREA"):
        return "store_marketing"
    if has("COMPANY BLEND") and any(l.t.startswith("per") and l.x > 1000 for l in d.lines):
        return "store_blend"
    if any(t == "COMPANY BLEND" for t in up) and any(is_money(l.t) and l.h >= 60 and 1150 <= l.y <= 1300 for l in d.lines):
        return "company_blend"
    if has("SALES LAST WEEK") or any(t.startswith("UNIT COST") for t in up):
        return "menu_item"
    if any("CAFE STREET JOURNAL" in t or "CAFÉ STREET JOURNAL" in t for t in up):
        return "newsletter"
    if learned.find_rule(d):
        return "learned"
    return "other"


PARSERS = {
    "weekly_results": parse_weekly, "newsletter": parse_newsletter, "cost_summary": parse_cost_summary,
    "option_card": parse_option, "equipment_card": parse_equipment, "manager_card": parse_manager,
    "marketing_option": parse_marketing, "menu_item": parse_menu_item, "company_blend": parse_company_blend,
    "build_overview": parse_overview, "income_statement": parse_income_statement,
    "store_performance": parse_store_performance, "customer_reviews": parse_customer_reviews,
    "manager_detail": parse_manager_detail, "store_marketing": parse_store_marketing, "review_detail": parse_review_detail, "roaster_blend": parse_roaster_blend, "store_blend": parse_store_blend,
    "agency_contract": parse_agency, "company_board": parse_company_board,
    "learned": learned.parse_learned,
}


def generic_pairs(d: Doc):
    """Label and value pairs for a screen no parser knows: money on the right of a word label."""
    out = []
    for m in [l for l in d.lines if is_money(l.t)]:
        lab = [l for l in d.lines if l is not m and not is_money(l.t) and abs(l.cy - m.cy) <= 26 and l.x < m.x and re.search(r"[A-Za-z]{3}", l.t)]
        if lab:
            out.append((max(lab, key=lambda l: l.x).t, m.t, m.c))
    return out


def parse(d: Doc, default_week: str = "") -> Parsed:
    kind = classify(d)
    fn = PARSERS.get(kind)
    if fn:
        try:
            return fn(d, default_week) if kind in ("weekly_results", "newsletter", "income_statement") else fn(d)
        except StopIteration:
            p = Parsed(kind)
            p.flags.append(f"{d.file.split('/')[-1]}: the {kind} layout was not as expected")
            p.kind = "other"
            return p
    p = Parsed("other")
    for lab, val, c in generic_pairs(d)[:12]:
        p.rows.append(row(d.file, slug(lab), val, "USD", c))
    p.flags.append(f"{d.file.split('/')[-1]}: unknown screen, someone needs to look at it")
    return p
