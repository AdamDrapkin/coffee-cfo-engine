"""`coffee find`: answer questions from saved text, never from re-reading images.

Every screenshot ever archived has its full text saved in raw/ocr/screens/<archived name>.txt (written by the
worker). Every analysis, decision, review and record is a markdown page. `find` searches all of it in well under a
second and prints where each hit is, so a question is answered from saved context instead of opening a PNG.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import vision
from .util import atomic_write

SCREEN_DIR = "raw/ocr/screens"
PRIORITY = ("wiki/ledger/decisions", "wiki/briefings", "wiki/ledger/reviews", "wiki/knowledge-base", "wiki/ledger", "wiki/hubs", "raw/ocr/screens")


def _text_of(doc: dict, name: str) -> str:
    lines = [f"# {name}  {doc.get('w')}x{doc.get('h')}  (y x height confidence text)"]
    for l in sorted(doc.get("lines", []), key=lambda l: (round(l["y"] / 20), l["x"])):
        lines.append(f"{l['y']:5.0f} {l['x']:5.0f} h{l['h']:3.0f} {l['c']:.2f}  {l['t']}")
    return "\n".join(lines) + "\n"


def archive_ocr(v: Path, limit: int = 60) -> int:
    """Save the text of archived screenshots that do not have it yet. Returns how many were written."""
    shots = v / "raw" / "screenshots"
    if not shots.exists():
        return 0
    out = v / SCREEN_DIR
    out.mkdir(parents=True, exist_ok=True)
    todo = [p for p in sorted(shots.iterdir()) if p.suffix.lower() in (".png", ".jpg", ".jpeg") and not (out / (p.name + ".txt")).exists()][:limit]
    if not todo:
        return 0
    docs = vision.read_files(v, todo)
    for p, d in docs.items():
        atomic_write(out / (p.name + ".txt"), _text_of(d, p.name))
    return len(docs)


def _files(v: Path):
    seen = set()
    for pref in PRIORITY:
        base = v / pref
        if not base.exists():
            continue
        pat = "*.txt" if pref.startswith("raw") else "*.md"
        for p in sorted(base.rglob(pat)):
            if p not in seen and not any(part.startswith(".") for part in p.relative_to(v).parts):
                seen.add(p)
                yield p


def find(v: Path, query: str, limit: int = 30) -> list:
    from .db import queries as dbq
    con = dbq.fresh_con(v)
    if con is not None:
        hits = dbq.search(con, query, limit)
        if hits:
            return hits
    words = [w for w in re.findall(r"[\w'$%.\-]+", query.lower()) if len(w) > 1]
    if not words:
        return []
    hits = []
    for p in _files(v):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            low = ln.lower()
            if all(w in low for w in words):
                hits.append(f"{p.relative_to(v)}:{i}: {ln.strip()[:220]}")
                if len(hits) >= limit:
                    return hits
    if not hits and len(words) > 1:          # nothing has every word: fall back to files that contain all of them anywhere
        for p in _files(v):
            try:
                low = p.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            if all(w in low for w in words):
                hits.append(f"{p.relative_to(v)}: contains every word (open the file)")
                if len(hits) >= limit:
                    break
    return hits
