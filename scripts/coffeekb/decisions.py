"""Decisions and open unknowns: an explicit status, and one command to close each.

A decision is a recommendation plus what the CEO did. Its status is one of: open, done, not possible, superseded,
unknown. `coffee decide "<words from the decision>" done "what happened"` files an amendment (never an edit).
Unknowns are rows in the assumptions table; `coffee resolve "<words>" "how it was settled"` appends a RESOLVED row,
and resolved items stop appearing in the state page and the packet.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import digest, ledger
from .ledger import ASSUMPTIONS, ledger_dir

STATUSES = {"open": "Open (pending CEO confirmation)", "done": "Done", "not-possible": "Not possible", "superseded": "Superseded", "unknown": "Unknown, awaiting the CEO's answer"}


def merged(v: Path) -> dict:
    """decision name -> latest merged record (an amendment overrides the original)."""
    from .db import queries as dbq
    con = dbq.fresh_con(v)
    if con is not None:
        return dbq.decisions_merged(con)
    out = {}
    for _, fm in digest.chron(digest._notes(ledger_dir(v) / "decisions")):
        out.setdefault(str(fm.get("decision") or ""), {}).update({k: val for k, val in fm.items() if val not in (None, "")})
    return out


def status_of(fm: dict) -> str:
    t = str(fm.get("ceo_decision", "")).lower()
    if t.startswith("done"):
        return "done"
    if t.startswith("not possible"):
        return "not possible"
    if t.startswith("superseded"):
        return "superseded"
    if t.startswith("unknown"):
        return "unknown"
    if "pending" in t or not t:
        return "open"
    return "done" if t else "open"


def find_one(v: Path, fragment: str):
    words = [w for w in re.findall(r"[\w$.]+", fragment.lower()) if len(w) > 1]
    m = merged(v)
    exact = [(n, fm) for n, fm in m.items() if n.strip().lower() == fragment.strip().lower()]
    if exact:
        return exact
    return [(n, fm) for n, fm in m.items() if words and all(w in n.lower() for w in words)]


def _log_status(v: Path, line: str) -> None:
    """One running page that the status amendments cite as their source (a log, appended to)."""
    from .util import atomic_write, page_fm, write_page
    p = v / "wiki" / "briefings" / "manual-status.md"
    if not p.exists():
        write_page(p, page_fm("Manual status changes", "Log of decision statuses and unknowns set by hand, with the reason.", "briefing", ["briefing", "status"], status="final"),
                   "# Manual status changes\n\nEach line is one decision status set with `coffee decide`. The decision records hold the same information.\n")
    atomic_write(p, p.read_text(encoding="utf-8").rstrip("\n") + f"\n- {line}\n")


def decide(v: Path, fragment: str, status: str, note: str, by: str = "claude-code") -> str:
    if status not in STATUSES:
        return f"Unknown status '{status}'. Use one of: {', '.join(STATUSES)}."
    hits = find_one(v, fragment)
    if not hits:
        return f"No decision contains: {fragment}"
    if len(hits) > 1:
        return "More than one decision matches; be more specific:\n" + "\n".join(f"  - {n[:120]}" for n, _ in hits)
    name, fm = hits[0]
    label = STATUSES[status].split(" (")[0]
    up = {"target": "decision", "op": "amend", "confidence": "High", "evidence": ["ceo-message"],
          "reason": f"Status set to {status}: {note or 'no note'}",
          "fields": {"decision": name, "options": fm.get("options", "n/a"), "recommendation": fm.get("recommendation", "n/a"),
                     "ceo_decision": f"{label}: {note}".rstrip(": ")}}
    _log_status(v, f"{digest.today()}: {name[:110]} -> {status}. {note}")
    ledger.write_updates(v, {"ledger_updates": [up]}, by, "manual-status", {})
    digest.write(v)
    from . import index
    index.rebuild(v)          # new notes must be linked from the hubs
    from .db import sync as dbsync
    dbsync.refresh(v)
    return f"Decision marked {status}: {name[:100]}"


# ---- unknowns -----------------------------------------------------------------------------

def _rows(v: Path) -> list:
    p = v / ASSUMPTIONS
    if not p.exists():
        return []
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())[:90]


def open_unknowns(v: Path) -> list:
    """Rows not yet resolved and not repeats of the same item (latest wording kept)."""
    from .db import queries as dbq
    con = dbq.fresh_con(v)
    if con is not None:
        return dbq.open_unknowns(con)
    rows = _rows(v)
    resolved = {_key(r[1][len("RESOLVED:"):]) for r in rows if r[1].startswith("RESOLVED:")}
    out, seen = [], set()
    for r in reversed(rows):
        if r[1].startswith("RESOLVED:"):
            continue
        k = _key(r[1])
        if k in resolved or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return list(reversed(out))


def resolve(v: Path, fragment: str, note: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", fragment.lower()) if len(w) > 2]
    hits = [r for r in open_unknowns(v) if words and all(w in r[1].lower() or w in r[2].lower() for w in words)]
    if not hits:
        return f"No open unknown contains: {fragment}"
    for r in hits:
        with open(v / ASSUMPTIONS, "a", encoding="utf-8") as fh:
            fh.write(f"| {digest.today()} | RESOLVED: {r[1]} | {note or 'settled'} | Resolved | n/a | CEO |\n")
    from .db import sync as dbsync
    dbsync.refresh(v)
    return f"Resolved {len(hits)} unknown(s)."
