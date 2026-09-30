"""The same totals as golden.totals, computed from the database, so `db compare` can prove the two agree."""
from __future__ import annotations

import json

from .conn import connect  # noqa: F401

QUESTION_COLS = {"active_blend": None}


def totals(con) -> dict:
    q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731
    store = q("select store_id from store order by (select count(*) from store_week w where w.store_id=store.store_id) desc limit 1")
    sid = store[0][0] if store else None
    out = {}
    out["company_weeks"] = {str(r["week"]): {"revenue": r["revenue"], "net_income": r["net_income"], "cash_flow": r["cash_flow"]} for r in q("select * from company_week order by week")}
    sw = {}
    for r in q("select w.*, b.name as blend from store_week w left join blend b using (blend_id) where store_id=? order by week", sid):
        sw[str(r["week"])] = {"sales": r["sales"], "net_profit": r["net_profit"], "hot_beverage_cups": r["cups_hot"], "cold_beverage_cups": r["cups_cold"],
                              "review_overall": r["rating_overall"], "review_count": r["review_count"], "staff_morale": r["staff_morale"], "active_blend": r["blend"]}
    out["store_weeks"] = sw
    out["menu_week_units"] = {str(r["week"]): r["u"] or 0 for r in q("select week, sum(units_sold) u from menu_week where store_id=? group by week order by week", sid)}
    out["menu_week_items"] = {str(r["week"]): r["n"] for r in q("select week, count(*) n from menu_week where store_id=? group by week order by week", sid)}
    by = {}
    for r in q("select status, count(*) n from decision group by status order by status"):
        by[r["status"]] = r["n"]
    out["decisions"] = {"total": sum(by.values()), "by_status": by}
    out["open_unknowns"] = q("select count(*) from unknown where resolved_at is null")[0][0]
    out["reviews_by_week"] = {str(r["week"]): r["n"] for r in q("select week, count(*) n from review group by week order by week")}
    out["catalog_by_category"] = {r["category"]: r["n"] for r in q("select category, count(*) n from option_catalog group by category order by category")}
    return out


def normalize(x):
    """Compare numbers as numbers (12268 == 12268.0 == '12268'), everything else as text."""
    if isinstance(x, dict):
        return {str(k): normalize(v) for k, v in x.items()}
    if x is None or x == "":
        return None
    try:
        f = float(str(x).replace(",", ""))
        return int(f) if f == int(f) else round(f, 4)
    except ValueError:
        return str(x)


def diff(a, b, path="") -> list:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += diff(a.get(k), b.get(k), f"{path}/{k}")
        return out
    return [] if a == b else [f"{path}: ledger {str(a)[:60]!r} database {str(b)[:60]!r}"]


def compare(v, con) -> list:
    """Differences between the ledger-derived totals and the database totals (empty = they agree)."""
    from .. import golden
    from .queries import ledger_only
    with ledger_only():
        led = normalize(golden.totals(v))
    led.pop("folder_notes", None)
    return diff(led, normalize(totals(con)))
