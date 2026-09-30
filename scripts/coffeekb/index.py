"""wiki/index.md rebuild and the page inventory used by lint."""
from __future__ import annotations
from pathlib import Path

from .util import page_fm, read_page, today, write_page

SECTIONS = [
    ("Knowledge base", "wiki/knowledge-base"),
    ("Ledger", "wiki/ledger"),
    ("Briefings", "wiki/briefings"),
    ("Tests", "wiki/tests"),
    ("Decisions", "wiki/decisions"),
    ("Outputs", "wiki/outputs"),
]


def wiki_pages(v: Path):
    """All wiki markdown pages except the index and log themselves."""
    out = []
    for p in sorted((v / "wiki").rglob("*.md")):
        if p.name in ("index.md", "log.md") and p.parent == v / "wiki":
            continue
        out.append(p)
    return out


def _title(p: Path) -> str:
    fm, _ = read_page(p)
    return (fm or {}).get("title") or p.stem


def build(v: Path) -> str:
    from .hubs import HUB_TITLES
    n = len(list(wiki_pages(v)))
    L = ["# Index", "", f"Start at [[map]]. {n} pages are organized under these hubs:", ""]
    L += [f"- [[{stem}]]: {title}" for stem, title in HUB_TITLES.items()]
    L += ["", "See also [[HOME]], [[STATUS]] and [[log]].", ""]
    return "\n".join(L)


def rebuild(v: Path):
    old = (v / "wiki" / "index.md")
    created = today()
    if old.exists():
        fm, _ = read_page(old)
        created = (fm or {}).get("date_created", created)
    from . import hubs
    hubs.rebuild(v)
    fm = page_fm("Index", "Master index of the Coffee Inc. knowledge base.", "index", ["index"])
    fm["date_created"] = created
    write_page(old, fm, build(v))


def indexed_stems(v: Path):
    import re
    text = (v / "wiki" / "index.md").read_text(encoding="utf-8") if (v / "wiki" / "index.md").exists() else ""
    return set(re.findall(r"\[\[([^\]|#]+)", text))
