"""Marketing agency contract screens and the company comparison board (store counts, quarterly revenue and net income)."""
from __future__ import annotations

import re

from .screens_core import LOW_CONF, Doc, Parsed, is_money, row

CITIES = ("San Francisco", "Chicago", "New York", "Tokyo", "London", "Paris", "Berlin", "Osaka", "Amsterdam", "Seattle", "Rome", "Sydney", "Madrid")


def parse_agency(d: Doc) -> Parsed:
    """One agency channel: agency name, channel (Billboard, Radio, TV, Online) and its commission on marketing spend."""
    p = Parsed("agency_contract")
    F, L = d.file, d.lines
    anchor = next(l for l in L if l.t.upper() == "MARKETING AGENCY")
    name = next((l for l in sorted(L, key=lambda l: anchor.y - l.y) if 0 < anchor.y - l.y < 120 and re.search(r"[A-Za-z]{3}", l.t) and l.t != "X"), None)
    chan = next((l for l in L if re.fullmatch(r"[A-Z][A-Za-z]* Ads", l.t.strip()) and l.h >= 40), None)
    rate = next((l for l in L if re.fullmatch(r"\d+(\.\d+)?% of Marketing Spend", l.t.strip())), None)
    aware = next((l for l in L if re.fullmatch(r"\d+%?", l.t.strip()) and 800 <= l.y <= 900 and l.x > 1000), None)
    if not (name and chan and rate):
        p.flags.append(f"{F.split('/')[-1]}: agency screen without a readable name, channel or commission rate")
        return p
    pct = rate.t.split("%")[0]
    p.rows += [row(F, "agency_name", name.t, "", name.c), row(F, "agency_channel", chan.t, "", chan.c), row(F, "commission_rate", pct + "%", "percent of marketing spend", rate.c)]
    notes = "Commission on marketing spend; the agency runs the channel for the city." + (f" Brand awareness in San Francisco: {aware.t.rstrip('%')}%." if aware else "")
    fields = {"category": "marketing agency", "name": f"{name.t} - {chan.t}", "cost": pct, "cost_unit": "% of marketing spend", "notes": notes}
    p.updates.append({"target": "catalog", "op": "append", "confidence": "High" if rate.c >= LOW_CONF else "Moderate",
                      "evidence": [F.split("/")[-1]], "fields": fields, "metric": True})
    return p


def parse_company_board(d: Doc) -> Parsed:
    """One company on the comparison board: stores per city, quarterly revenue and quarterly net income."""
    p = Parsed("company_board")
    F, L = d.file, d.lines
    head = next(l for l in L if l.t.upper() == "COMPANIES")
    name = next((l for l in sorted(L, key=lambda l: l.y - head.y) if 0 < l.y - head.y < 400 and l.h >= 45 and re.search(r"[A-Za-z]{3}", l.t)), None)
    cities = [l for l in L if l.t in CITIES]
    counts = {}
    for n in (l for l in L if re.fullmatch(r"\d{1,2}", l.t.strip()) and l.h >= 45 and l.y > 900):
        above = [c for c in cities if 0 < n.y - c.y < 140 and abs(c.cx - n.cx) < 200]
        if above:
            counts[min(above, key=lambda c: n.y - c.y).t] = int(n.t)
    rev_l = next((l for l in L if l.t.upper() == "QUARTERLY REVENUE"), None)
    net_l = next((l for l in L if l.t.upper() == "NET INCOME" and l.y > 2000), None)
    def value_under(lab):
        c = [l for l in L if is_money(l.t) and 0 < l.y - lab.y < 120 and abs(l.cx - lab.cx) < 420]
        return min(c, key=lambda l: abs(l.cx - lab.cx), default=None)
    rev, net = (value_under(rev_l) if rev_l else None), (value_under(net_l) if net_l else None)
    if not (name and rev and net):
        p.flags.append(f"{F.split('/')[-1]}: company board without a readable name, quarterly revenue or net income")
        return p
    p.rows.append(row(F, "company", name.t, "", name.c))
    for c, n in counts.items():
        p.rows.append(row(F, "stores_" + c.lower().replace(" ", "_"), n, "stores"))
    p.rows += [row(F, "quarterly_revenue", rev.t, "USD", rev.c), row(F, "quarterly_net_income", net.t, "USD", net.c)]
    by_city = ", ".join(f"{c} {n}" for c, n in counts.items())
    fields = {"name": name.t, "known_stores": sum(counts.values()), "stores_by_city": by_city, "quarterly_revenue": re.sub(r"[$,]", "", rev.t),
              "quarterly_net_income": re.sub(r"[$,]", "", net.t)}
    if re.match(r"panda", name.t, re.I):        # the CEO's own company is not a competitor; its figures stay in the briefing rows
        return p
    p.updates.append({"target": "competitor", "op": "amend", "confidence": "High" if min(rev.c, net.c) >= LOW_CONF else "Moderate", "metric": True,
                      "evidence": [F.split("/")[-1]], "reason": "Company comparison board: store counts, quarterly revenue and net income.", "fields": fields})
    return p
