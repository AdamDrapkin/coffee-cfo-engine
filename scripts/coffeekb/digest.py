"""State digest: the only ledger view ever sent to Gemini (150 lines max)."""
from __future__ import annotations
from pathlib import Path

from .ledger import ledger_dir
from .util import note_problem, page_fm, read_page, today, write_page  # noqa: F401

MAX_LINES = 400      # every section is capped on its own, so this is only a safety limit
META = {"title", "date_created", "date_modified", "summary", "tags", "type", "status",
        "kind", "op", "confidence", "extracted_by", "source_screenshot", "briefing",
        "reason", "amends"}


def _notes(folder: Path):
    out = []
    for p in sorted(folder.glob("*.md")):
        fm, _ = read_page(p)
        if fm:
            out.append((p, fm))
    return out


def _order(name: str):
    """File name -> sort key where 'x-amend' comes before 'x-amend-2' before 'x-amend-10'."""
    import re
    stem = name[:-3] if name.endswith(".md") else name
    m = re.match(r"^(.*?)(-amend)?(?:-(\d+))?$", stem)
    root, is_amend, n = m.group(1), bool(m.group(2)), int(m.group(3) or 1)
    return (root, 1 if is_amend else 0, n)


def chron(items):
    """Oldest first, and an amendment always after the record it amends (amend, amend-2, ... amend-10)."""
    return sorted(items, key=lambda t: (str(t[1].get("date_created")), 1 if t[1].get("op") == "amend" else 0, _order(t[0].name)))


def _facts(fm: dict, limit=14):
    items = [f"{k} {v}" for k, v in fm.items() if k not in META and v not in (None, "")]
    return "; ".join(items[:limit])


def _merged_weeks(v: Path):
    """week number -> merged fields (original then amendments in order)."""
    weeks = {}
    for p, fm in chron(_notes(ledger_dir(v) / "weeks")):
        wk = str(fm.get("week", ""))
        if not wk:
            continue
        entry = weeks.setdefault(wk, {"fields": {}, "confidence": fm.get("confidence")})
        entry["fields"].update({k: val for k, val in fm.items() if k not in META})
        entry["confidence"] = fm.get("confidence", entry["confidence"])
    return weeks


def build(v: Path) -> str:
    lines = ["# State digest", "",
             "Baseline: Panda's Coffee, Coffee Inc. 2+, Normal difficulty, 2 competitors, USD, $800,000 starting capital.",
             f"Generated: {today()}. Numbers below come from the ledger and were read from screenshots. Anything not listed is unknown.", ""]

    from . import corrections
    cmap = corrections.corrected_map(v)
    cn = corrections.notes(v)
    if cn:
        lines += ["## Corrections in force (these override anything older, including old briefings)"]
        for p, fm in cn[-10:]:
            lines.append(f"- Not true: \"{str(fm.get('claim'))[:110]}\". True: {str(fm.get('correction'))[:220]} ({fm.get('date_created')})")
        lines.append("")
    weeks = _merged_weeks(v)
    if not weeks:
        lines += ["## Company snapshot", "- No data yet. No screenshots have been ingested.",
                  "- Do not assume any store, cash figure, debt, or week.", ""]
    else:
        keys = sorted(weeks, key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0))
        lines += ["## Company snapshot"]
        for wk in keys[-2:][::-1]:
            e = weeks[wk]
            facts = "; ".join(f"{k} {val}" for k, val in e["fields"].items())
            lines.append(f"- Week {wk} (confidence {e['confidence']}): {facts}")
        lines.append("")

    stores = {}
    for p, fm in chron(_notes(ledger_dir(v) / "stores")):
        name = str(fm.get("name") or fm.get("store") or fm.get("store_name") or p.stem)
        merged = dict(stores[name][1]) if name in stores else {}
        merged.update({k: val for k, val in fm.items() if val not in (None, "")})
        stores[name] = (p, merged)
    lines.append("## Stores (latest record each)")
    if stores:
        for name, (p, fm) in list(stores.items())[:20]:
            lines.append(f"- {name}: {_facts(fm, 60)} (confidence {fm.get('confidence')})")
    else:
        lines.append("- none recorded")
    lines.append("")

    try:
        from . import analysis as _an
        dl = _an.decisions_in_force(v, 5)
        if dl:
            lines.append("## Recent decisions and what the CEO did (the reason a number may have moved)")
            lines += [x.strip() for x in dl]
            lines.append("")
    except Exception as _e:
        note_problem(__name__, _e)
        pass
    revs = _notes(ledger_dir(v) / "reviews")
    if revs:
        wks = [int(str(fm.get("week"))) for _, fm in revs if str(fm.get("week", "")).isdigit()]
        last = max(wks) if wks else None
        lines.append(f"## Customer voice (week {last}; {len(revs)} reviews recorded in all, see wiki/hubs/hub-reviews.md)")
        for _, fm in [t for t in revs if str(t[1].get("week")) == str(last)][:40]:
            lines.append(f"- \"{str(fm.get('review_text', ''))[:140]}\" ({fm.get('theme', 'untagged')})")
        lines.append("")

    cat = _notes(ledger_dir(v) / "catalog")
    lines.append("## Option catalog (details in wiki/ledger/catalog/)")
    if cat:
        by = {}
        for p_, fm in cat:
            by[str(fm.get("category", "other"))] = by.get(str(fm.get("category", "other")), 0) + 1
        lines += [f"- {k}: {n} options recorded" for k, n in sorted(by.items())]
    else:
        lines.append("- none recorded")
    lines.append("")

    for folder, heading, cap in (("decisions", "Recent decisions", 6),
                                 ("events", "Recent events", 6),
                                 ("loans", "Loans and debt", 6),
                                 ("competitors", "Competitors", 6)):
        notes = _notes(ledger_dir(v) / folder)[-cap:]
        lines.append(f"## {heading}")
        if notes:
            for p, fm in notes:
                mark = " [CORRECTED, see corrections above]" if p.stem in cmap else ""
                lines.append(f"- {fm.get('date_created')}: {_facts(fm, 8)} (confidence {fm.get('confidence')}){mark}")
        else:
            lines.append("- none recorded")
        lines.append("")

    a = v / "wiki" / "ledger" / "assumptions-and-unknowns.md"
    lines.append("## Open assumptions and unknowns")
    try:
        from . import decisions as _dc
        rows = ["| " + " | ".join(r) + " |" for r in _dc.open_unknowns(v)]
    except Exception as e:
        note_problem(__name__, e)
        rows = []
    lines += rows[-10:] or ["- none recorded"]

    text = "\n".join(lines[:MAX_LINES]).rstrip() + "\n"
    return text


def write(v: Path) -> Path:
    text = build(v)
    path = v / "wiki" / "outputs" / "state-digest.md"
    fm = page_fm("State digest", "Generated snapshot sent to Gemini instead of the full ledger.",
                 "index", ["digest"])
    write_page(path, fm, text)
    return path
