"""Append-only ledger writer. Python writes; Gemini never does.

Every ledger update is a NEW note. Existing ledger files are never modified
(except the two running tables, which only ever get rows appended).
Corrections are amendment notes that carry a reason and point at the record
they correct.
"""
from __future__ import annotations
import re
from pathlib import Path

from .util import (note_problem, atomic_write, now_iso, norm_number, page_fm, slugify, today,
                   write_page)

FOLDERS = {
    "week": "weeks",
    "store": "stores",
    "city": "cities",
    "competitor": "competitors",
    "decision": "decisions",
    "capital-allocation": "capital-allocation",
    "loan": "loans",
    "investment": "investments",
    "acquisition": "acquisitions",
    "event": "events",
    "catalog": "catalog",
    "correction": "corrections",
    "review": "reviews",
    "menu-week": "menu-weeks",
}
NAME_KEYS = ("menu_week_id", "review_id", "claim", "name", "store", "store_name", "city", "competitor", "opportunity",
             "lender", "asset", "target", "event", "title", "decision")

ASSUMPTIONS = "wiki/ledger/assumptions-and-unknowns.md"
INTAKE_LOG = "wiki/ledger/screenshot-intake-log.md"


def ledger_dir(v: Path) -> Path:
    return v / "wiki" / "ledger"


def week_key(wk) -> str:
    s = str(wk).strip()
    return f"{int(s):03d}" if s.isdigit() else slugify(s)


def week_exists(v: Path, wk) -> bool:
    return (ledger_dir(v) / "weeks" / f"week-{week_key(wk)}.md").exists()


def _coerce(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        s = val.strip()
        if re.fullmatch(r"[-(]?\$?-?\d[\d,]*\.?\d*\)?", s):
            n = norm_number(s)
            if n is not None:
                return float(n) if "." in n else int(n)
    return val


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, n = path.stem, 2
    while True:
        cand = path.with_name(f"{stem}-{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


WEEK_ALIASES = {"cash": "ending_cash", "cash_on_hand": "ending_cash", "ending_cash_balance": "ending_cash",
                "sales": "revenue", "total_revenue": "revenue", "net_profit": "net_income",
                "net_earnings": "net_income", "total_debt": "debt", "cost_of_goods_sold": "cogs"}


def _normalize(target: str, fields: dict) -> dict:
    if target != "week":
        return fields
    out = {}
    for k, val in fields.items():
        key = WEEK_ALIASES.get(slugify(k).replace("-", "_"), k)
        out[key] = val if key not in out else out[key]
    return out


def _name_for(target: str, fields: dict) -> str:
    for k in NAME_KEYS:
        if fields.get(k):
            return slugify(fields[k])
    return target


def ensure_seed(v: Path):
    """Create the two running tables and folder markers if missing."""
    for sub in list(FOLDERS.values()):
        d = ledger_dir(v) / sub
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists() and not any(d.glob("*.md")):
            keep.touch()
    a = v / ASSUMPTIONS
    if not a.exists():
        fm = page_fm("Assumptions and unknowns",
                     "Running list of assumptions and open unknowns. Rows are only appended.",
                     "ledger", ["ledger", "assumptions"])
        write_page(a, fm, "# Assumptions and unknowns\n\n"
                   "| Date | Item | Current assumption | Confidence | How to verify | Source |\n"
                   "|---|---|---|---|---|---|\n")
    s = v / INTAKE_LOG
    if not s.exists():
        fm = page_fm("Screenshot intake log",
                     "One row per screenshot or note processed. Rows are only appended.",
                     "ledger", ["ledger", "intake"])
        write_page(s, fm, "# Screenshot intake log\n\n"
                   "| Intake ID | Date | Type | What was read | Unreadable or missing | Confidence | Backend |\n"
                   "|---|---|---|---|---|---|---|\n")


def _append_row(path: Path, row: str):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(row.rstrip("\n") + "\n")


def _cell(x) -> str:
    return str(x).replace("|", "/").replace("\n", " ").strip()


def log_intake(v: Path, data: dict, extracted_by: str, id_prefix: str):
    ensure_seed(v)
    by_file = {}
    for row in data.get("extraction", []):
        by_file.setdefault(row.get("file", ""), []).append(row)
    n = 0
    for item in data.get("intake", []):
        n += 1
        rows = by_file.get(item.get("file", ""), [])
        read = ", ".join(_cell(r.get("field", "")) for r in rows if not r.get("unreadable"))[:200] or "nothing"
        miss = ", ".join(_cell(r.get("field", "")) for r in rows if r.get("unreadable")) or "none"
        _append_row(v / INTAKE_LOG,
                    f"| {id_prefix}-{n} | {today()} | {_cell(item.get('type', ''))} | {read} | {miss} | "
                    f"{_cell(item.get('confidence', ''))} | {extracted_by} |")


def _akey(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(text).lower()).split())[:90]


def _recent_items(v: Path, n: int = 80) -> list:
    p = v / ASSUMPTIONS
    if not p.exists():
        return []
    rows = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")][-n:]
    return [[c.strip() for c in ln.strip("|").split("|")][1] for ln in rows if len(ln.split("|")) > 2]


def _render_fields(fields: dict) -> str:
    """Bullet list of fields; a list of records (like a week's menu) becomes a table."""
    out = []
    for k, v_ in fields.items():
        if isinstance(v_, list) and v_ and all(isinstance(x, dict) for x in v_):
            cols = list(v_[0].keys())
            out += [f"- **{k}**:", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
            out += ["| " + " | ".join(str(x.get(c, "")) for c in cols) + " |" for x in v_]
            out.append("")
        else:
            out.append(f"- **{k}**: {v_}")
    return "\n".join(out) or "- (no fields)"


def _existing(folder: Path, label: str):
    """An earlier record of the same thing (any date): names look like YYYY-MM-DD-<label>[-amend][-n].md"""
    for p in folder.glob("20??-??-??-*.md"):
        rest = p.name[11:-3]
        if rest == label or rest.startswith(label + "-") and not rest.startswith(label + "-amend"):
            return p
    return None


def write_updates(v: Path, data: dict, extracted_by: str, briefing_link: str,
                  evidence_map: dict | None = None, warnings: list | None = None) -> list:
    """Write every ledger update as a new note. Returns the list of written paths."""
    ensure_seed(v)
    evidence_map = evidence_map or {}
    written = []
    from . import hubs
    try:
        registry = hubs.Registry(v) if data.get("ledger_updates") else None      # built once per filing, not once per note
    except Exception as e:
        note_problem(__name__, e)
        registry = None
    for up in data.get("ledger_updates", []):
        target, op = up["target"], up["op"]
        fields = _normalize(target, dict(up.get("fields", {})))
        evidence = [evidence_map.get(e, e) for e in up.get("evidence", [])]

        if target == "assumption":
            item = fields.get("item") or fields.get("name") or "unnamed"
            if any(_akey(item) == _akey(r) for r in _recent_items(v)):
                continue          # the same unknown is already open; do not add a repeat
            _append_row(v / ASSUMPTIONS,
                        f"| {today()} | {_cell(item)} | {_cell(fields.get('assumption') or fields.get('current_assumption') or fields.get('value') or 'Unknown / requires testing')} | "
                        f"{_cell(up['confidence'])} | {_cell(fields.get('how_to_verify', 'in-game check'))} | {_cell(', '.join(evidence))} |")
            written.append(v / ASSUMPTIONS)
            continue

        if target == "test":
            folder = v / "wiki" / "tests"
        else:
            folder = ledger_dir(v) / FOLDERS[target]
        folder.mkdir(parents=True, exist_ok=True)

        label = None
        if target == "week":
            wk = week_key(fields.get("week", "unknown"))
            base = f"week-{wk}" if op == "append" else f"week-{wk}-amend"
            path = folder / f"{base}.md"
        else:
            label = (slugify(fields["category"]) + "-" if target == "catalog" and fields.get("category") else "") + _name_for(target, fields)
            if target == "correction":
                label = "correction-" + label      # never share a file name with the record it corrects
            path = folder / f"{today()}-{label}{'-amend' if op == 'amend' else ''}.md"
        if warnings is not None and op == "append" and target not in ("week",):
            same = _existing(folder, label if target == "catalog" else _name_for(target, fields))
            if same is not None:
                warnings.append(f"{target} '{same.name[11:-3]}' is already recorded ({same.name}). "
                                "If this is a correction it should be an amend with a reason; otherwise skip the copy.")
        path = _unique(path) if (op == "amend" or target != "week") else path
        if path.exists():  # append-only guard, belt and braces
            raise FileExistsError(f"refusing to overwrite {path}")

        if target == "week":
            title = f"Week {fields.get('week', '?')}" + (" amendment" if op == "amend" else "")
        else:
            title = f"{target} {op}: {_name_for(target, fields)}"
        fm = page_fm(title, f"{op} record for {target}.", "ledger", ["ledger", target], status="final")
        fm["kind"] = target
        fm["op"] = op
        fm["confidence"] = up["confidence"]
        fm["extracted_by"] = extracted_by
        fm["source_screenshot"] = evidence
        fm["briefing"] = briefing_link
        if op == "amend":
            fm["reason"] = up["reason"]
            if target == "week":
                fm["amends"] = f"week-{week_key(fields.get('week', ''))}"
        for k, val in fields.items():
            key = slugify(k).replace("-", "_")
            if key in fm:
                key += "_field"
            fm[key] = _coerce(val)

        hub_stem, rel_stems = hubs.related(v, target, fields, registry)
        prev_note = _existing(folder, label if target == "catalog" else _name_for(target, fields)) if (op == "amend" and target != "week") else None
        link_lines = f"- Part of: [[{hub_stem}]]\n"
        if rel_stems:
            link_lines += "- Related: " + ", ".join(f"[[{x}]]" for x in rel_stems) + "\n"
        if op == "amend":
            if target == "week":
                link_lines += f"- Amends: [[week-{week_key(fields.get('week', ''))}]]\n"
            elif prev_note is not None:
                link_lines += f"- Amends: [[{prev_note.stem}]]\n"
        rows = _render_fields(fields)
        body = (f"# {title}\n\n{rows}\n\n"
                f"- Confidence: {up['confidence']}\n- Extracted by: {extracted_by}\n"
                f"- Evidence: {', '.join(evidence) or 'none'}\n- Briefing: [[{briefing_link}]]\n" + link_lines
                + (f"- Reason: {up['reason']}\n" if op == 'amend' else ""))
        write_page(path, fm, body)
        written.append(path)
    return written
