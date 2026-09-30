"""Read side: the same shapes the ledger readers return, served from SQL. Used only while the database is FRESH
(its ledger signature matches the ledger); otherwise callers fall back to the ledger and say so."""
from __future__ import annotations

import json
import os
import sys  # noqa: F401
from contextlib import contextmanager
from pathlib import Path

from .. import dbhealth
from ..util import note_problem
from .load import INT_COLS, STORE_COLS, signature
from . import conn as _conn

_cache = {"sig": None, "ok": None, "con": None}
_INVERSE = {c: k for k, c in STORE_COLS.items()}


def _num(x):
    if x is None:
        return None
    return int(x) if isinstance(x, float) and x == int(x) else x


STALE_NOTE = "[db] the database was behind the ledger, so this answer came from the ledger. Fix: sh scripts/run.sh db refresh"


def reset() -> None:
    if _cache.get("con"):
        try:
            _cache["con"].close()
        except Exception as e:
            note_problem(__name__, e)
    _cache.update({"sig": None, "ok": None, "con": None, "unreachable": False})


def stale_note() -> str:
    """Text for the reader commands to print when an answer had to fall back to the ledger."""
    return STALE_NOTE if _cache.get("stale_seen") else ""


@contextmanager
def ledger_only():
    """Force the ledger readers (used by `db compare`, which must not compare the database with itself)."""
    old = os.environ.get("COFFEE_DB")
    os.environ["COFFEE_DB"] = "0"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("COFFEE_DB", None)
        else:
            os.environ["COFFEE_DB"] = old


def fresh_con(v: Path):
    """A connection when the database exists, is healthy and matches the ledger; otherwise None."""
    if os.environ.get("COFFEE_DB") == "0":
        return None
    path = dbhealth.db_path()
    if not path.exists() or "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("COFFEE_DB_TEST") or _cache.get("unreachable"):
        return None
    try:
        sig = signature(v)
        if _cache["sig"] == sig and _cache["ok"] is not None:
            return _cache["con"] if _cache["ok"] else None
        con = _conn.connect(path)
        row = con.execute("select value from meta where key='ledger_signature'").fetchone()
        ok = bool(row) and row[0] == sig
        _cache.update({"sig": sig, "ok": ok, "con": con if ok else None})
        if not ok:
            con.close()
            _cache["stale_seen"] = True
        return con if ok else None
    except Exception as e:
        # unreachable from this process (for example a sandbox): remember it, log it once, and answer from the ledger
        if not _cache.get("unreachable"):
            note_problem(__name__, e)
        _cache.update({"sig": None, "ok": None, "con": None, "unreachable": True})
        return None


def primary_store(con) -> str:
    r = con.execute("select s.name from store s left join store_week w using (store_id) group by s.store_id order by count(w.week) desc, s.store_id limit 1").fetchone()
    return r[0] if r else ""


def store_by_week(con, store: str = "") -> dict:
    store = store or primary_store(con)
    out = {}
    rows = con.execute("select w.*, b.name blend, s.name sname from store_week w join store s using (store_id) left join blend b using (blend_id) where s.name=? order by w.week", (store,)).fetchall()
    for r in rows:
        f = {"name": r["sname"], "week": r["week"]}
        for col, key in _INVERSE.items():
            if r[col] is not None:
                f[key] = r[col] if col in INT_COLS else _num(r[col])
        if r["blend"]:
            f["active_blend"] = r["blend"]
            p = con.execute("select price_per_lb from blend_price where blend_id=? and week=?", (r["blend_id"], r["week"])).fetchone()
            if p:
                f["blend_price_per_lb"] = _num(p[0])
        for c in con.execute("select c.name, s.cost_per_week from store_campaign_week s join campaign c using (campaign_id) where s.store_id=? and s.week=?", (r["store_id"], r["week"])):
            f["active_campaign_" + c[0].replace(" ", "_")] = _num(c[1])
        out[r["week"]] = f
    return out


def menu_weeks(con, store: str = "") -> dict:
    store = store or primary_store(con)
    out = {}
    for r in con.execute("select w.week, i.name, i.grp, w.price, w.unit_cost, w.margin, w.units_sold, w.units_change from menu_week w join menu_item i using (item_id) "
                         "join store s using (store_id) where s.name=? order by w.week, i.item_id", (store,)):
        out.setdefault(r["week"], []).append({
            "name": r["name"], "group": r["grp"], "price": "" if r["price"] is None else f"{r['price']:.2f}",
            "unit_cost": "" if r["unit_cost"] is None else f"{r['unit_cost']:.2f}", "margin": "" if r["margin"] is None else str(int(round(r["margin"]))),
            "sales": "" if r["units_sold"] is None else str(r["units_sold"]), "sales_change": r["units_change"] or ""})
    return out


def decisions_merged(con) -> dict:
    out = {}
    for r in con.execute("select * from decision order by decision_id"):
        fm = json.loads(r["detail_json"]) if r["detail_json"] else {}
        fm.setdefault("decision", r["title"])
        fm.setdefault("ceo_decision", r["ceo_note"])
        fm.setdefault("recommendation", r["recommendation"])
        fm.setdefault("options", r["options"])
        out[r["decision_key"]] = fm
    return out


def open_unknowns(con) -> list:
    return [[r["opened_at"] or "", r["text"], r["detail"] or "", "Low", "", ""] for r in
            con.execute("select * from unknown where resolved_at is null order by opened_at, unknown_id")]


def levers_missing(con) -> list:
    """Levers that do not exist in the game: (name, [keywords])."""
    return [(r["name"], [k.strip() for k in (r["keywords"] or "").split(",") if k.strip()]) for r in con.execute("select * from lever where exists_in_game=0")]


def search(con, query: str, limit: int = 30) -> list:
    """Ranked keyword search: reviews, briefings and knowledge pages, every screen's text, and decisions."""
    import re
    toks = [t.replace('"', "") for t in re.findall(r"[\w$'.\-]+", query.lower()) if len(t) > 1]
    if not toks:
        return []
    match = " ".join(f'"{t}"*' for t in toks)
    out = []
    plans = (("reviews", "select r.week, snippet(review_fts, 0, '[', ']', ' ... ', 14) sn from review_fts f join review r on r.review_id = f.rowid where review_fts match ? order by rank limit ?",
              lambda r: f"review (week {r['week']}): {r['sn']}"),
             ("documents", "select d.path, snippet(document_fts, 0, '[', ']', ' ... ', 14) sn from document_fts f join document d on d.doc_id = f.rowid where document_fts match ? order by rank limit ?",
              lambda r: f"{r['path']}: {r['sn']}"),
             ("screens", "select s.file, snippet(source_fts, 0, '[', ']', ' ... ', 14) sn from source_fts f join source s on s.source_id = f.rowid where source_fts match ? order by rank limit ?",
              lambda r: f"raw/ocr/screens/{r['file']}.txt: {r['sn']}"))
    for _name, sql, fmt in plans:
        try:
            out += [fmt(r) for r in con.execute(sql, (match, limit))]
        except Exception as e:
            note_problem(__name__, e)
    like = " and ".join("lower(coalesce(detail_json,'') || ' ' || title) like ?" for _ in toks)
    for r in con.execute(f"select title, status from decision where {like} limit 8", [f"%{t}%" for t in toks]):
        out.insert(0, f"decision [{r['status']}]: {r['title']}")
    return out[:limit]
