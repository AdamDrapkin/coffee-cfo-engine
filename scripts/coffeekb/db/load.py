"""Ledger -> database. The whole derived database is rebuilt in ONE transaction (all or nothing), so a half-loaded week can never exist.

Until the cutover (Sprint 8) the markdown ledger is authoritative and this rebuild runs after every filing.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .. import analysis, decisions, digest, facts, lookup
from ..ledger import ledger_dir, ASSUMPTIONS
from ..util import note_problem, read_page, today

STORE_COLS = {  # ledger store field -> store_week column
    "sales": "sales", "hot_beverage_sales": "hot_sales", "cold_beverage_sales": "cold_sales", "food_sales": "food_sales", "cogs": "cogs",
    "coffee_beans": "coffee_beans", "payroll": "payroll", "rent": "rent", "marketing": "marketing", "other_costs": "depreciation",
    "administrative_cost": "admin_cost", "total_expenses": "total_expenses", "operating_profit": "operating_profit", "net_profit": "net_profit",
    "hot_beverage_cups": "cups_hot", "cold_beverage_cups": "cups_cold", "floor_staff_count": "staff_count", "floor_staff_hourly_wage": "wage",
    "staff_skill": "staff_skill", "staff_morale": "staff_morale", "review_overall": "rating_overall", "review_price": "rating_price",
    "review_product": "rating_product", "review_service": "rating_service", "review_atmosphere": "rating_atmosphere", "review_count": "review_count",
}
INT_COLS = {"cups_hot", "cups_cold", "staff_count", "staff_skill", "staff_morale", "review_count"}
LEVERS = [  # name, keywords, exists_in_game, notes
    ("floor staff training", "train,staff", 0, "There is no operational training for floor staff (CEO confirmed 2026-09-30)."),
    ("floor staff count", "staff,count", 1, "Plus and minus on the store screen."), ("floor staff hourly wage", "wage,hourly", 1, "Plus and minus on the store screen."),
    ("manager delegation switches", "delegat", 1, "Staffing and salary, products and pricing, store marketing, store troubles."),
    ("manager salary and firing", "manager,salary,fire", 1, "On the manager screen."), ("menu prices", "price,menu", 1, "Per item."),
    ("marketing campaigns", "marketing,campaign", 1, "Wi-Fi, power strips, catering, community sponsors, direct mail, local paid search, buy one get one, free music, social media."),
    ("recyclable cups", "recyclable,cups", 1, "A marketing option (percent recyclable) that changes unit cost."), ("coffee blend", "blend", 1, "Default blend or a supplier's packaged blend."),
    ("store build and equipment", "equipment,exterior,interior", 1, "Exterior, interior, espresso machine, brewer, blender."),
]


def _f(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x))) if str(x).strip() not in ("", "None") else None
    except ValueError:
        return None


def _i(x):
    f = _f(x)
    return int(round(f)) if f is not None else None


def _week(x):
    s = str(x).strip()
    return int(s) if s.isdigit() else None


def signature(v: Path) -> str:
    """Fingerprint of the ledger: any new, removed or changed note (or the unknowns table) changes it."""
    h = hashlib.sha1()
    base = ledger_dir(v)
    for p in sorted(base.rglob("*.md")):
        st = p.stat()
        h.update(f"{p.relative_to(base)}|{st.st_size}|{st.st_mtime_ns}".encode())
    for extra in ("wiki/knowledge-base/confirmed-game-facts.md",):
        q = v / extra
        if q.exists():
            h.update(f"{extra}|{q.stat().st_size}".encode())
    return h.hexdigest()


CLEAR = ["review_rating", "review", "menu_week", "menu_item", "store_campaign_week", "campaign", "store_week", "blend_price", "blend", "company_week",
         "decision_event", "decision", "lever", "game_fact", "unknown", "correction", "competitor_move", "competitor", "event", "option_catalog",
         "capital_item", "reading", "source", "document", "store", "week"]


def rebuild(v: Path, con) -> dict:
    """Rebuild every table from the ledger inside one transaction. Returns row counts."""
    from .queries import ledger_only, reset
    reset()
    with ledger_only():          # the loader must read the LEDGER, never the database it is rewriting
        return _rebuild(v, con)


def _rebuild(v: Path, con) -> dict:
    counts = {}
    con.execute("begin")
    try:
        con.execute("pragma defer_foreign_keys=on")
        for t in CLEAR:
            con.execute(f"delete from {t}")
        for t in ("review_fts", "document_fts", "source_fts"):
            if con.execute("select 1 from sqlite_master where name=?", (t,)).fetchone():
                con.execute(f"delete from {t}")
        _stores_and_weeks(v, con)
        _menu(v, con)
        _reviews(v, con)
        _decisions(v, con)
        _unknowns(v, con)
        _misc(v, con)
        _sources_and_documents(v, con)
        if con.execute("select 1 from sqlite_master where name='review_fts'").fetchone():
            con.execute("insert into review_fts(rowid, text) select review_id, text from review")
            con.execute("insert into source_fts(rowid, text) select source_id, ocr_text from source where ocr_text is not null")
            con.execute("insert into document_fts(rowid, text) select doc_id, body from document")
        con.execute("insert or replace into meta values ('ledger_signature', ?)", (signature(v),))
        con.execute("insert or replace into meta values ('rebuilt_at', ?)", (today(),))
        bad = con.execute("pragma foreign_key_check").fetchall()
        if bad:
            raise ValueError(f"{len(bad)} foreign key violations while loading")
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '%fts%'").fetchall():
        counts[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
    return counts


def _stores_and_weeks(v, con):
    names = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "stores")):
        n = str(fm.get("name") or "").strip()
        if n:
            names.setdefault(n, {}).update({k: val for k, val in fm.items() if val not in (None, "")})
    weeks = digest._merged_weeks(v)
    all_weeks = {int(w) for w in weeks if str(w).isdigit()}
    store_hist = {n: analysis._store_by_week(v, n) for n in names}
    for h in store_hist.values():
        all_weeks |= set(h)
    all_weeks |= set(lookup.menu_weeks(v).keys())
    for w in sorted(all_weeks):
        con.execute("insert into week (week) values (?)", (w,))
    for n, fm in names.items():
        con.execute("insert into store (name, city, manager, manager_salary) values (?,?,?,?)", (n, fm.get("city"), fm.get("manager"), _f(fm.get("manager_annual_salary"))))
    for wk, e in weeks.items():
        if not str(wk).isdigit():
            continue
        f = e["fields"]
        con.execute("insert into company_week values (?,?,?,?,?,?,?,?,?)", (int(wk), _f(f.get("revenue")), _f(f.get("net_income")), _f(f.get("operating_cash_flow")),
                                                                            _f(f.get("investing_cash_flow")), _f(f.get("financing_cash_flow")), _f(f.get("cash_flow")),
                                                                            _f(f.get("ending_cash")), _f(f.get("debt"))))
    blends, camps = {}, {}
    for n, hist in store_hist.items():
        sid = con.execute("select store_id from store where name=?", (n,)).fetchone()[0]
        for w, f in hist.items():
            cols = {"store_id": sid, "week": w}
            for k, c in STORE_COLS.items():
                if k in f:
                    cols[c] = _i(f[k]) if c in INT_COLS else _f(f[k])
            bname = str(f.get("active_blend") or "").strip()
            if bname:
                if bname not in blends:
                    con.execute("insert into blend (name, supplier) values (?,?)", (bname, "Pacific Coffee Roaster Company" if bname.lower().startswith("pacific") else "Company default"))
                    blends[bname] = con.execute("select blend_id from blend where name=?", (bname,)).fetchone()[0]
                cols["blend_id"] = blends[bname]
                if _f(f.get("blend_price_per_lb")) is not None:
                    con.execute("insert or replace into blend_price values (?,?,?)", (blends[bname], w, _f(f["blend_price_per_lb"])))
            con.execute(f"insert into store_week ({','.join(cols)}) values ({','.join('?' * len(cols))})", list(cols.values()))
            for k, val in f.items():
                if k.startswith("active_campaign_"):
                    cname = k[len("active_campaign_"):].replace("_", " ")
                    if cname not in camps:
                        con.execute("insert into campaign (name) values (?)", (cname,))
                        camps[cname] = con.execute("select campaign_id from campaign where name=?", (cname,)).fetchone()[0]
                    con.execute("insert or replace into store_campaign_week values (?,?,?,?)", (sid, w, camps[cname], _f(val)))


def _menu(v, con):
    stores = {r["name"]: r["store_id"] for r in con.execute("select * from store")}
    seen_items = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "menu-weeks")):
        sname = str(fm.get("store") or "")
        sid = stores.get(sname) or (next(iter(stores.values())) if len(stores) == 1 else None)   # early screens carry no store line
        w = _week(fm.get("week"))
        if sid is None or w is None:
            continue
        for it in fm.get("items") or []:
            nm = str(it.get("name"))
            if nm not in seen_items:
                con.execute("insert into menu_item (name, grp) values (?,?)", (nm, it.get("group") or ""))
                seen_items[nm] = con.execute("select item_id from menu_item where name=?", (nm,)).fetchone()[0]
            con.execute("insert or replace into menu_week values (?,?,?,?,?,?,?,?)",
                        (sid, w, seen_items[nm], _f(it.get("price")), _f(it.get("unit_cost")), _f(it.get("margin")), _i(it.get("sales")), it.get("sales_change") or None))


def _reviews(v, con):
    stores = {r["name"]: r["store_id"] for r in con.execute("select * from store")}
    for _, fm in digest._notes(ledger_dir(v) / "reviews"):
        sid = stores.get(str(fm.get("store") or ""))
        if sid is None or not fm.get("review_text"):
            continue
        con.execute("insert or ignore into review (review_key, store_id, week, text, theme) values (?,?,?,?,?)",
                    (str(fm.get("review_id")), sid, _week(fm.get("week")), str(fm["review_text"]), fm.get("theme")))


def _decisions(v, con):
    merged = decisions.merged(v)
    for name, fm in merged.items():
        m = re.match(r"Week (\d+)", name)
        con.execute("insert into decision (decision_key, week, title, recommendation, options, status, ceo_note, detail_json) values (?,?,?,?,?,?,?,?)",
                    (name, int(m.group(1)) if m else None, name, fm.get("recommendation"), fm.get("options"), decisions.status_of(fm), fm.get("ceo_decision"),
                     json.dumps({k: val for k, val in fm.items() if k not in digest.META}, default=str, sort_keys=True)))
    ids = {r["decision_key"]: r["decision_id"] for r in con.execute("select decision_key, decision_id from decision")}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "decisions")):
        did = ids.get(str(fm.get("decision") or ""))
        if did is not None:
            con.execute("insert into decision_event (decision_id, at, status, note) values (?,?,?,?)",
                        (did, str(fm.get("date_created")), decisions.status_of(fm), fm.get("ceo_decision")))
    for name, kw, ex, notes in LEVERS:
        con.execute("insert into lever (name, keywords, exists_in_game, notes) values (?,?,?,?)", (name, kw, ex, notes))
    for r in facts.rows(v):
        if len(r) >= 5:
            con.execute("insert into game_fact (kind, keywords, fact, source, at) values (?,?,?,?,?)", (r[1], r[2], r[3], r[4], r[0]))


def _unknowns(v, con):
    p = v / ASSUMPTIONS
    if not p.exists():
        return
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]
    resolved = {decisions._key(r[1][len("RESOLVED:"):]): (r[0], r[2]) for r in rows if r[1].startswith("RESOLVED:")}
    seen = set()
    for r in rows:
        if r[1].startswith("RESOLVED:"):
            continue
        k = decisions._key(r[1])
        if k in seen:
            continue
        seen.add(k)
        at, why = resolved.get(k, (None, None))
        con.execute("insert into unknown (unknown_key, text, detail, opened_at, resolved_at, resolution) values (?,?,?,?,?,?)", (k, r[1], r[2], r[0], at, why))


def _misc(v, con):
    from .. import corrections
    for _, fm in corrections.notes(v):
        con.execute("insert or ignore into correction (claim, truth, applies_to, at) values (?,?,?,?)",
                    (str(fm.get("claim")), str(fm.get("correction")), ", ".join(str(x) for x in fm.get("affected") or []), str(fm.get("date_created"))))
    comps = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "competitors")):
        n = str(fm.get("name") or "").strip()
        if not n:
            continue
        comps.setdefault(n, {}).update({k: val for k, val in fm.items() if val not in (None, "")})
        con.execute("insert or ignore into competitor (name) values (?)", (n,))
        cid = con.execute("select competitor_id from competitor where name=?", (n,)).fetchone()[0]
        if fm.get("recent_moves"):
            con.execute("insert or ignore into competitor_move (competitor_id, city, move) values (?,?,?)", (cid, fm.get("city"), str(fm["recent_moves"])))
    for n, f in comps.items():
        con.execute("update competitor set city=?, known_stores=?, threat_level=? where name=?", (f.get("city"), _i(f.get("known_stores")), f.get("threat_level"), n))
    for _, fm in digest._notes(ledger_dir(v) / "events"):
        if fm.get("event"):
            con.execute("insert or ignore into event (headline, category, severity) values (?,?,?)", (str(fm["event"]), fm.get("category"), fm.get("severity")))
    cat = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "catalog")):
        k = (str(fm.get("category") or "other"), str(fm.get("name") or ""))
        if k[1]:
            cat.setdefault(k, {}).update({a: b for a, b in fm.items() if b not in (None, "")})
    meta = set(digest.META) | {"category", "name", "cost", "notes"}
    for (c, n), f in cat.items():
        con.execute("insert into option_catalog (category, name, cost, stats_json, notes) values (?,?,?,?,?)",
                    (c, n, None if f.get("cost") is None else str(f["cost"]), json.dumps({a: b for a, b in f.items() if a not in meta}, sort_keys=True, default=str), f.get("notes")))
    for _, fm in digest._notes(ledger_dir(v) / "capital-allocation"):
        con.execute("insert into capital_item (kind, name, amount, status, notes) values ('capital',?,?,?,?)",
                    (str(fm.get("opportunity") or "capital item"), _f(fm.get("required_cash")), fm.get("type"), fm.get("notes")))


def _sources_and_documents(v, con):
    d = v / "raw" / "ocr" / "screens"
    if d.exists():
        for p in sorted(d.glob("*.txt")):
            name = p.name[:-4]
            m = re.match(r"^\d{4}-\d{2}-\d{2}-wk([a-z0-9]+)-(.+?)-\d+(?:-\d+)?\.[A-Za-z]+$", name)
            text = "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[1:])
            con.execute("insert or ignore into source (file, week, kind, sha1, ocr_text) values (?,?,?,?,?)",
                        (name, _week(m.group(1)) if m else None, m.group(2) if m else None, hashlib.sha1(text.encode()).hexdigest(), text))
    for sub, kind in (("wiki/briefings", "briefing"), ("wiki/knowledge-base", "knowledge")):
        for p in sorted((v / sub).glob("*.md")):
            try:
                fm, body = read_page(p)
            except Exception as e:
                note_problem(__name__, e)
                continue
            m = re.search(r"Week (\d+)", str((fm or {}).get("title", "")) + " " + body[:200])
            con.execute("insert or replace into document (path, kind, title, week, body) values (?,?,?,?,?)",
                        (str(p.relative_to(v)), kind, (fm or {}).get("title"), int(m.group(1)) if m else None, body.split("## Machine block")[0]))   # the JSON block is data, not prose to search
