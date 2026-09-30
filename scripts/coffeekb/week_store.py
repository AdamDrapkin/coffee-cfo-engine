"""Turning parsed screens into store, review and weekly menu records, and archiving the screen text."""
from __future__ import annotations

import collections
import re
from pathlib import Path

from . import briefing as briefing_mod, digest, screens
from .ledger import ledger_dir
from .util import atomic_write
from .week_dedupe import _as_num, _norm

KIND_LABEL = {
    "weekly_results": "weekly results", "newsletter": "newsletter", "cost_summary": "cost summary",
    "option_card": "exterior/interior options", "equipment_card": "equipment", "manager_card": "manager candidates",
    "marketing_option": "marketing options", "menu_item": "menu items", "company_blend": "company blend",
    "build_overview": "build overview", "income_statement": "store income statement",
    "store_performance": "store performance", "customer_reviews": "customer reviews", "manager_detail": "manager screen", "store_marketing": "store marketing", "learned": "learned layout", "agency_contract": "marketing agency contract", "company_board": "company comparison board", "review_detail": "review details", "roaster_blend": "roaster blends", "store_blend": "store blend view",
}


STORE_METRIC_KINDS = ("customer_reviews", "review_detail", "store_performance", "store_blend", "store_marketing", "manager_detail", "learned")


_SKIP_METRIC = {"store", "review_comment", "headline", "statement_column", "blend", "chart_first_date"}


def _theme(text: str) -> str:
    for name, pat in briefing_mod.THEMES:
        if re.search(pat, text, re.I):
            return name
    return "other"


def _store_of(x) -> str:
    return next((r["value"] for r in x.rows if r["field"] == "store"), "")


def _add_store_logging(recognized: dict, batch_week: str) -> list:
    """Everything shown on the store screens goes into the ledger: ratings, staff, cups, blend, campaigns, and every review."""
    import hashlib
    by_kind = collections.defaultdict(list)
    default_store = next((st for x in recognized.values() for st in [_store_of(x)] if st), "")   # screens without a store line belong to the batch's store
    for n, x in recognized.items():
        if x.kind in STORE_METRIC_KINDS:
            by_kind[(x.kind, _store_of(x) or default_store)].append(x)
    reviews, seen = [], set()
    for (kind, group_store), xs in by_kind.items():
        fields, store, files = {}, group_store, [] 
        for x in xs:
            store = _store_of(x) or store
            for r in x.rows:
                if r["field"] == "review_comment" and r["value"] not in seen:
                    seen.add(r["value"])
                    reviews.append((r["value"], r["file"], store))
                elif r["field"] not in _SKIP_METRIC and not r.get("unreadable"):
                    fields[r["field"]] = re.sub(r"[+$,]", "", r["value"]) if screens.is_money(r["value"]) else r["value"]
                    files.append(r["file"])
        if fields and store and batch_week:
            xs[0].updates.append({"target": "store", "op": "amend", "confidence": "High", "evidence": sorted(set(files))[:6], "metric": True,
                                  "reason": f"{KIND_LABEL.get(kind, kind)} screen values for week {batch_week}.",
                                  "fields": {"name": store, "week": batch_week, **fields}})
    host_groups = [xs for (k, _s), xs in by_kind.items() if k in ("customer_reviews", "review_detail")]
    if reviews and host_groups:
        host = host_groups[0][0]
        for text, f, store in reviews:
            rid = f"wk{batch_week or 'x'}-" + hashlib.sha1(_norm(text).encode()).hexdigest()[:6]
            host.updates.append({"target": "review", "op": "append", "confidence": "High", "evidence": [f],
                                 "fields": {"review_id": rid, "store": store, "week": batch_week, "review_text": text, "theme": _theme(text)}})
    return [t for t, _, _ in reviews]


def _menu_items(rows: list) -> list:
    """One dict per menu item from the extraction rows (grouped by screen file)."""
    by = collections.OrderedDict()
    for r in rows:
        if r["field"] in ("menu_item", "price", "unit_cost", "margin", "sales_last_week", "sales_change", "item_group") and not r.get("unreadable"):
            by.setdefault(r["file"], {})[r["field"]] = r["value"]
    items, seen_names = [], set()
    for d in by.values():
        if "menu_item" in d and d["menu_item"] not in seen_names:
            seen_names.add(d["menu_item"])
            items.append({"name": d["menu_item"], "group": d.get("item_group", ""), "price": d.get("price", "").lstrip("$"),
                          "unit_cost": d.get("unit_cost", "").lstrip("$"), "margin": d.get("margin", "").rstrip("%"),
                          "sales": d.get("sales_last_week", ""), "sales_change": d.get("sales_change", "")})
    return items


def _add_menu_week(recognized: dict, rows: list, batch_week: str) -> None:
    """One weekly menu record per store with every item, so item history is a lookup and not a re-read of screens."""
    if not batch_week:
        return
    host = next((x for x in recognized.values() if x.kind == "menu_item"), None)
    if host is None:
        return
    file_store, default_store = {}, ""
    for r in rows:
        if r["field"] == "store":
            file_store[r["file"]] = r["value"]
            default_store = default_store or r["value"]
    by_store = collections.OrderedDict()
    for r in rows:
        if r["field"] == "menu_item" and not r.get("unreadable"):
            by_store.setdefault(file_store.get(r["file"], default_store), []).append(r["file"])
    for store, files in by_store.items():
        items = _menu_items([r for r in rows if r["file"] in set(files)])
        if not items:
            continue
        suffix = "" if len(by_store) == 1 else "-" + re.sub(r"[^a-z0-9]+", "-", store.lower()).strip("-")
        host.updates.append({"target": "menu-week", "op": "append", "confidence": "High", "evidence": sorted(set(files))[:6], "menu": True,
                             "fields": {"menu_week_id": f"week-{int(batch_week):03d}{suffix}", "week": batch_week, "store": store, "items": items}})


def _review_status(v: Path, store: str, week: str, texts: list, total) -> dict:
    have = {_norm(fm.get("review_text")) for _, fm in digest._notes(ledger_dir(v) / "reviews")
            if str(fm.get("week")) == str(week) and _norm(fm.get("store")) == _norm(store)}
    have |= {_norm(t) for t in texts}
    n = int(_as_num(total)) if total not in (None, "") and _as_num(total) == _as_num(total) else 0
    return {"captured": len(have), "total": n}


def _archive_ocr(v: Path, bundle: str, docs: dict, name_of: dict) -> int:
    """Keep the full text of every screen read (recognized or not) in raw/ocr, so nothing shown is ever lost."""
    d = v / "raw" / "ocr" / bundle
    d.mkdir(parents=True, exist_ok=True)
    for p, doc in docs.items():
        lines = [f"# {name_of.get(p, p.name)}  {doc.get('w')}x{doc.get('h')}  (y x height confidence text)"]
        for l in sorted(doc.get("lines", []), key=lambda l: (round(l["y"] / 20), l["x"])):
            lines.append(f"{l['y']:5.0f} {l['x']:5.0f} h{l['h']:3.0f} {l['c']:.2f}  {l['t']}")
        atomic_write(d / (re.sub(r"[^\w.-]", "_", name_of.get(p, p.name)) + ".txt"), "\n".join(lines) + "\n")
    return len(docs)
