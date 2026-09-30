"""Seed the vault: one knowledge-base note per Game Systems section.

Nothing here states a game fact. Every mechanic starts as
'Unknown / requires testing' until a source or an in-game test supports it.
"""
from __future__ import annotations
from pathlib import Path

from . import absorb, index, ledger, render
from .util import append_log, ensure_quota_log, page_fm, slugify, write_page

SECTIONS = [
    "Starting Conditions and Difficulty", "Competitors", "Store Locations and Leases",
    "Store Design and Equipment", "Products, Menu, Pricing, and Quality", "Staffing and Operations",
    "Brand, Marketing, and Demand", "Store-Level Profitability", "City-Level Strategy",
    "Competition and Market Share", "Corporate Departments and Executives",
    "Finance and Financial Statements", "Cash, Debt, and Liquidity", "Investments and Securities",
    "Real Estate", "Acquisitions and Mergers", "IPO, Equity, Ownership, and Dividends",
    "Plantations / Supply Chain / Vertical Integration", "Events, Newsletters, and Random Events",
    "Endgame and Tycoon Strategy",
]


def kb_path(v: Path, section: str) -> Path:
    return v / "wiki" / "knowledge-base" / f"{slugify(section)}.md"


def seed(v: Path):
    made = 0
    for sec in SECTIONS:
        p = kb_path(v, sec)
        if p.exists():
            continue
        fm = page_fm(sec, f"Game systems note: {sec}. Every mechanic is Unknown / requires testing until sourced or tested.",
                     "knowledge", ["knowledge-base"], status="draft", section=sec)
        body = (f"# {sec}\n\n"
                "Mechanic status: **Unknown / requires testing**\n\n"
                "## Confirmed\n- none yet\n\n## Community\n- none yet\n\n"
                "## Inference\n- none yet\n\n## Unknown\n- everything in this section\n\n"
                "## Sources\n- none yet\n\n## Research updates\n")
        write_page(p, fm, body)
        made += 1
    ledger.ensure_seed(v)
    ensure_quota_log(v)
    absorb.seed(v)
    from . import research
    rp = v / "inbox" / "research-paste.md"
    if not rp.exists():
        rp.write_text(research.TEMPLATE, encoding="utf-8")
    for d in ("wiki/decisions", "wiki/tests", "wiki/briefings", "raw/screenshots", "raw/research", "raw/notes", "inbox", "exports"):
        (v / d).mkdir(parents=True, exist_ok=True)
    if not (v / "HOME.md").exists():
        render.render_home(v)
    if not (v / "STATUS.md").exists():
        render.render_status(v, queue=0)
    index.rebuild(v)
    if made:
        append_log(v, "init", f"seeded {made} knowledge-base notes")
    return made
