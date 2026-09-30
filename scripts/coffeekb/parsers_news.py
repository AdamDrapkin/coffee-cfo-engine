"""Weekly results and the newspaper."""
from __future__ import annotations

import datetime as dt
import re

from .screens_core import (GAME_START, LOW_CONF, Doc, Parsed, is_money, money_val, row, _find, _row_value)

_DATE = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")


def _iso(date_text: str) -> str:
    m = _DATE.search(date_text or "")
    try:
        return dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date().isoformat() if m else ""
    except ValueError:
        return ""


def game_week(date_text: str):
    m = _DATE.search(date_text or "")
    if not m:
        return ""
    try:
        d = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
    except ValueError:
        return ""
    return str((d - GAME_START).days // 7)


_NAV = {"Top", "Retail", "Business", "Market", "Markets", "Politics", "Sports", "Coffee", "Finance", "Local", "World", "News"}


_CITY = r"(?P<city>[A-Z][a-z]+(?: [A-Z][a-z]+)?)(?![\w'\u2019])"


def _clean_who(who: str) -> str:
    """Drop navigation words that the reader placed just before a headline subject."""
    parts = who.split()
    while parts and parts[0] in _NAV:
        parts.pop(0)
    return " ".join(parts)


def _newsletter_events(d: Doc):
    """Headline patterns seen so far. Anything else is left for a person."""
    cols = {"L": [], "R": []}
    for l in sorted(d.lines, key=lambda l: (l.y, l.x)):
        if l.y > 1300 or True:
            cols["L" if l.cx < d.w / 2 else "R"].append(l.t)
    events = []
    for col in cols.values():
        text = " ".join(col)
        for m in re.finditer(r"(?P<who>(?:[A-Z][\w'’]* ){0,3}[A-Z][\w'’]*) Opened Business in " + _CITY, text):
            who = _clean_who(m.group("who"))
            if who and not who.startswith("Panda"):
                events.append((f"{who} opened business in {m.group('city')}", "competitor move", "competitor"))
        for m in re.finditer(r"New Store (?P<who>(?:[A-Z][\w'’]* ){0,3}[A-Z][\w'’]*) opened a new coffee shop in " + _CITY, text):
            who = _clean_who(m.group("who"))
            if who and not who.startswith("Panda"):
                events.append((f"{who} opened a new coffee shop in {m.group('city')}", "new store", "competitor"))
        for m in re.finditer(r"The (?P<bank>[A-Z][\w. ]*?) (?P<verb>maintained|decreased|increased|raised|lowered|cut) the (?P<what>[\w. ]*?)rate (?:at|to|by) (?P<rate>[\d.]+%)", text):
            events.append((f"The {m.group('bank').strip()} {m.group('verb')} the rate to {m.group('rate')}", "interest rate", "economy"))
        for m in re.finditer(r"(?P<co>(?:[A-Z][\w'’]* ){0,3}[A-Z][\w'’]*) Paid Quarterly Dividend .*?declared a cash dividend of (?P<amt>\$[\d.]+) \((?P<pct>[\d.]+%)\)", text):
            events.append((f"{_clean_who(m.group('co'))} paid a quarterly dividend of {m.group('amt')} per share ({m.group('pct')})", "dividend", "investment"))
        # a headline subject is at most a few capitalized words; never let it swallow the text before it
        for m in re.finditer(r"(?P<topic>(?:[A-Z][a-z]+ ){1,2})Bill Proposed", text):
            events.append((f"{m.group('topic').strip()} bill proposed", "legislation", "regulation"))
    seen, out = set(), []
    for e in events:
        if e[0] not in seen:
            seen.add(e[0])
            out.append(e)
    return out


def _events_updates(d: Doc, week: str):
    ups = []
    for text, cat, kind in _newsletter_events(d):
        ups.append({"target": "event", "op": "append", "confidence": "High", "evidence": [d.file.split("/")[-1]],
                    "fields": {"event": text, "category": cat, "severity": "Low",
                               "required_response": "None. Informational."}})
        m = re.match(r"(?P<who>.+?) opened (?:business|a new coffee shop) in (?P<city>.+)$", text)
        if kind == "competitor" and m:
            # the competitor's record gets the move too, so the dossier stays current (only what the paper says)
            ups.append({"target": "competitor", "op": "amend", "confidence": "High", "evidence": [d.file.split("/")[-1]],
                        "reason": "New store reported in the newspaper.",
                        "fields": {"name": m.group("who").strip(), "city": m.group("city").strip(), "recent_moves": text}})
    return ups


def parse_weekly(d: Doc, default_week: str = "") -> Parsed:
    p = Parsed("weekly_results")
    L = d.lines
    date = next((l.t for l in L if _DATE.search(l.t)), "")
    p.week = game_week(date) or default_week
    F = d.file
    vals = {}
    for label, key in (("WEEKLY REVENUE", "revenue"), ("WEEKLY NET INCOME", "net_income")):
        lab = _find(L, label)
        if lab:
            cands = [l for l in L if is_money(l.t) and lab.y + 25 < l.y < lab.y + 130 and abs(l.cx - lab.cx) < 170]
            if cands:
                v = min(cands, key=lambda l: l.y)
                vals[key] = v
    for label, key in (("Cash from Operations", "operating_cash_flow"), ("Investing", "investing_cash_flow"),
                       ("Financing", "financing_cash_flow"), ("Net Cash Flow", "cash_flow")):
        lab = _find(L, label)
        if lab:
            v = _row_value(L, lab)
            if v:
                vals[key] = v
    fields = {}
    for key, l in vals.items():
        p.rows.append(row(F, key, l.t, "USD", l.c))
        p.conf = min(p.conf, l.c)
        fields[key] = l.t
    if date:
        p.rows.append(row(F, "newsletter_date", date))
    if p.week:
        p.rows.append(row(F, "week", p.week))
    ks = ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "cash_flow")
    if all(k in vals for k in ks):
        total = sum(money_val(vals[k].t) for k in ks[:3])
        if abs(total - money_val(vals["cash_flow"].t)) > 0.5:
            p.flags.append(f"cash flow lines do not add up on {F.split('/')[-1]}: operating, investing and financing sum to {total:,.0f} but net cash flow reads {vals['cash_flow'].t}")
    if not p.week and fields:
        p.flags.append(f"no newsletter date on {F.split('/')[-1]}, so the game week is unknown")
    p.facts = {"week": p.week, **fields}
    if fields and p.week:
        clean = {k: (re.sub(r"[+$,]", "", val) if is_money(val) else val) for k, val in fields.items()}
        p.updates.append({"target": "week", "op": "append", "confidence": "High" if p.conf >= LOW_CONF else "Moderate",
                          "evidence": [F.split("/")[-1]], "fields": {"week": p.week, **clean, **({"game_date": _iso(date)} if _iso(date) else {})}})
    p.updates += _events_updates(d, p.week)
    for text, _, _ in _newsletter_events(d):
        p.rows.append(row(F, "headline", text))
    return p


def parse_newsletter(d: Doc, default_week: str = "") -> Parsed:
    p = Parsed("newsletter")
    date = next((l.t for l in d.lines if _DATE.search(l.t)), "")
    p.week = game_week(date) or default_week
    if date:
        p.rows.append(row(d.file, "newsletter_date", date))
    p.updates += _events_updates(d, p.week)
    for text, _, _ in _newsletter_events(d):
        p.rows.append(row(d.file, "headline", text))
    return p
