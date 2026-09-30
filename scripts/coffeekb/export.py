"""`coffee export`: regenerate the two master-prompt Markdown files from the wiki.

They are generated, never hand-edited. Headings match the master prompt. The one
deliberate change: no emdashes, so the title uses a plain hyphen.
"""
from __future__ import annotations
from pathlib import Path

from .digest import META, _merged_weeks, _notes
from .ledger import ledger_dir
from .seed import SECTIONS, kb_path
from .util import read_page, today

KB_FILE = "Pandas_Coffee_Coffee_Inc_2_Plus_Knowledge_Base.md"
MEM_FILE = "Pandas_Coffee_Company_Memory_and_Weekly_Ledger.md"
NR = "not recorded"

PLAYBOOKS = ["First Store Playbook", "Second and Third Store Playbook", "Scaling Playbook",
             "Store Turnaround Playbook", "City Expansion Playbook", "Marketing Playbook",
             "Competitor Response Playbook", "Cash Crisis Playbook", "Debt Playbook",
             "Investment Playbook", "Acquisition Playbook", "IPO Playbook",
             "Plantation / Supply Chain Playbook", "Tycoon Preparation Playbook"]
KPIS = [
    ("Revenue growth", "(current revenue - prior revenue) / prior revenue"),
    ("Gross margin", "(revenue - COGS) / revenue"),
    ("Operating margin", "operating profit / revenue"),
    ("Net margin", "net income / revenue"),
    ("Store payback period", "initial store investment / incremental periodic cash flow"),
    ("Marketing ROI", "(incremental profit from marketing - marketing cost) / marketing cost"),
    ("Acquisition payback period", "(price + integration cost) / incremental periodic cash flow"),
    ("Debt service coverage proxy", "operating cash flow / required debt payments"),
    ("Cash runway proxy", "cash on hand / average net cash burn per period"),
]


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def pick(fm, *keys):
    for k in keys:
        if fm.get(k) not in (None, ""):
            return fm[k]
    return NR


def _section_body(v: Path, section: str) -> str:
    p = kb_path(v, section)
    if not p.exists():
        return "Mechanic status: Unknown / requires testing"
    _, body = read_page(p)
    lines = body.splitlines()
    lines = [ln for ln in lines if not ln.startswith("# ")]
    return "\n".join(lines).strip().replace("\n## ", "\n#### ")


def _research_sources(v: Path):
    rows = []
    for p in sorted((v / "raw" / "research").glob("*.md")):
        fm, _ = read_page(p)
        for s in (fm or {}).get("sources", []) or []:
            rows.append([f"{p.stem}:{s.get('id', '')}", s.get("publisher", ""), s.get("url", ""),
                         s.get("date", ""), s.get("source_type", ""), s.get("topics", fm.get("topic", "")),
                         s.get("reliability", "unknown"), s.get("notes", "")])
    return rows


def export_kb(v: Path) -> Path:
    L = ["# Panda's Coffee - Coffee Inc. 2+ Knowledge Base", "",
         "## Document Control",
         f"- Created: 2026-09-29", f"- Last updated: {today()}",
         "- Game version / edition researched: Coffee Inc. 2+ (Apple Arcade), version not recorded",
         "- Research status: see Source Registry",
         "- Confidence summary: every mechanic is Unknown / requires testing unless labeled otherwise",
         "- Important known limitations: generated from wiki notes; nothing here is invented", "",
         "## Company Setup",
         "- Company name: Panda's Coffee", "- Difficulty: Normal", "- Competitor count: 2",
         "- Currency: USD", "- Starting capital: $800,000",
         "- Initial strategic objective: a profitable, repeatable multi-store company before unnecessary investment risk",
         "- Long-term objective: succeed on Tycoon difficulty with 5 competitors", "",
         "## Executive Summary",
         "- What Coffee Inc. 2+ is: a coffee-company business simulation on Apple Arcade",
         "- What the company is trying to accomplish: see Company Setup",
         "- The central operating philosophy: protect liquidity, fix high-return problems first, expand only with evidence",
         "- The biggest early-game risks: Unknown / requires testing",
         "- The biggest late-game risks: Unknown / requires testing", "",
         "## Source Registry",
         table(["Source ID", "Source / Publisher", "URL", "Date", "Source Type", "Topics Covered", "Reliability", "Notes"],
               _research_sources(v) or [["none", "", "", "", "", "", "", "no research run yet"]]), "",
         "## Mechanic Confidence Rules",
         "- Confirmed mechanic: official or reliable current-version source, or repeated controlled in-game test",
         "- Likely mechanic: strong partial evidence",
         "- Community-reported mechanic: player reports, not verified",
         "- Analytical inference: derived from the CEO's own screenshots and data",
         "- Unknown / requires testing: no adequate evidence", "",
         "## Game Systems"]
    for sec in SECTIONS:
        L += [f"### {sec}", _section_body(v, sec), ""]
    L += ["## Confirmed Formulas", "- None confirmed yet. Only formulas backed by official or reliable current-version sources belong here.", "",
          "## CFO Proxy Formulas", "Management tools, not necessarily game-engine formulas."]
    pm = v / "core" / "playbooks" / "reference-proxy-metrics.md"
    if pm.exists():
        L += [ln.replace("# 11. ", "### ") for ln in pm.read_text(encoding="utf-8").splitlines() if not ln.startswith("# ")]
    L += ["", "## KPI Dictionary",
          table(["KPI", "Formula / Method", "Purpose", "Good Signal", "Warning Signal", "Required Screenshot or Data"],
                [[k, f, "CFO proxy metric", "not recorded", "not recorded", "income statement or dashboard"] for k, f in KPIS]), "",
          "## Operating Playbooks"]
    for name in PLAYBOOKS:
        L += [f"### {name}", "Unknown / requires testing. Fill from evidence, not from assumption.", ""]
    L += ["## Scenario Prompt Library", "Reusable playbooks. Each states what to upload, what to extract, and how to answer.", ""]
    for p in sorted((v / "core" / "playbooks").glob("scenario-*.md")):
        L += [ln.replace("## Scenario", "### Scenario", 1) if ln.startswith("## Scenario") else ln
              for ln in p.read_text(encoding="utf-8").splitlines()] + [""]
    L += ["## Testing Log"]
    tests = _notes(v / "wiki" / "tests")
    if tests:
        for p, fm in tests:
            _, body = read_page(p)
            L += [f"### {fm.get('title', p.stem)}", body.strip(), ""]
    else:
        L += ["- No tests recorded yet.", ""]
    L += ["## Lessons Learned", "- Stable principles: none recorded yet",
          "- Version-specific observations: none recorded yet",
          "- CEO preferences: phone first, near-zero friction",
          "- Mistakes to avoid: none recorded yet"]
    out = v / "exports" / KB_FILE
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
    return out


def _rows(v: Path, folder: str, cols):
    rows = []
    for p, fm in _notes(ledger_dir(v) / folder):
        rows.append([pick(fm, *keys) for _, keys in cols] + [fm.get("confidence", NR)])
    return rows


def export_memory(v: Path) -> Path:
    weeks = _merged_weeks(v)
    keys = sorted(weeks, key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0))
    L = ["# Panda's Coffee - Company Memory and Weekly Ledger", "",
         "## Document Control", "- Company: Panda's Coffee", "- Game: Coffee Inc. 2+ (Apple Arcade)",
         "- Difficulty: Normal", "- Competitors: 2", "- Currency: USD", "- Starting capital: $800,000",
         f"- Current in-game date / week: {keys[-1] if keys else 'not recorded'}",
         f"- Last updated: {today()}", "- Data-quality status: every value comes from a screenshot or the CEO's note; unreadable values are marked",
         "- Screenshot archive reference: raw/screenshots/", "",
         "## CEO Strategic Mandate",
         "- Current company objective: build a profitable, repeatable multi-store company",
         "- Current phase: not recorded", "- Risk tolerance: not recorded", "- Current priorities: not recorded",
         "- Current restrictions: no paid services", "- Decisions awaiting CEO approval: see Decision Register", "",
         "## Current Company Snapshot"]
    if keys:
        last, prev = weeks[keys[-1]], (weeks[keys[-2]] if len(keys) > 1 else None)
        rows = []
        for k, val in last["fields"].items():
            pv = prev["fields"].get(k, NR) if prev else NR
            rows.append([k, val, pv, NR, NR, last["confidence"], f"week {keys[-1]}"])
        L.append(table(["Metric", "Latest Value", "Prior Week", "Change", "Trend", "Confidence", "Source"], rows))
    else:
        L.append("No week recorded yet.")
    L += ["", "## Current CFO Assessment"]
    from .render import load_latest
    lat = load_latest(v)
    if lat:
        s = lat["summary"]
        L += [f"- Latest decision: {s.get('decision')}", f"- Confidence: {s.get('confidence')}",
              "- Next actions: " + "; ".join(s.get("do_now", []))]
    else:
        L += ["- Company health: not assessed yet", "- Next three CEO actions: send the first screenshots"]

    def sec(title, headers, folder, cols):
        rows = _rows(v, folder, cols)
        return ["", f"## {title}", table(headers + ["Confidence"], rows) if rows else "No entries yet."]

    L += sec("Store Register", ["Store", "City / Area", "Sales", "COGS", "Payroll", "Operating Profit", "Status"], "stores",
             [("", ("name", "store", "store_name")), ("", ("city", "area")), ("", ("sales", "revenue")), ("", ("cogs",)),
              ("", ("payroll",)), ("", ("operating_profit",)), ("", ("status",))])
    L += sec("City Portfolio", ["City", "Panda's Stores", "Competitor Stores", "Total Revenue", "Total Profit", "Recommended Action"], "cities",
             [("", ("city", "name")), ("", ("panda_stores", "stores")), ("", ("competitor_stores",)), ("", ("total_revenue", "revenue")),
              ("", ("total_profit", "profit")), ("", ("recommended_action",))])
    L += sec("Competitor Register", ["Competitor", "Market", "Known Stores", "Threat Level", "Recent Moves"], "competitors",
             [("", ("name", "competitor")), ("", ("city", "market")), ("", ("known_stores", "stores")), ("", ("threat_level",)), ("", ("recent_moves",))])
    L += ["", "## Financial History"]
    if keys:
        cols = ["revenue", "cogs", "gross_profit", "payroll", "marketing", "net_income", "ending_cash", "debt"]
        rows = [[k] + [weeks[k]["fields"].get(c, NR) for c in cols] + [weeks[k]["confidence"]] for k in keys]
        L.append(table(["Week"] + cols + ["Confidence"], rows))
    else:
        L.append("No weeks recorded yet.")
    L += sec("Option Catalog", ["Category", "Name", "Cost", "Quality", "Productivity"], "catalog",
             [("", ("category",)), ("", ("name",)), ("", ("cost",)), ("", ("quality",)), ("", ("productivity",))])
    L += sec("Weekly Newsletter and Event Log", ["Event", "Category", "Severity", "Required Response", "Completed?"], "events",
             [("", ("event", "name", "title")), ("", ("category",)), ("", ("severity",)), ("", ("required_response",)), ("", ("completed",))])
    L += sec("Decision Register", ["Decision Requested", "Options Considered", "CFO Recommendation", "CEO Decision", "Actual Result"], "decisions",
             [("", ("decision", "name")), ("", ("options",)), ("", ("recommendation",)), ("", ("ceo_decision",)), ("", ("actual_result",))])
    L += sec("Capital Allocation Register", ["Opportunity", "Type", "Required Cash", "Recommendation", "CEO Decision"], "capital-allocation",
             [("", ("opportunity", "name")), ("", ("type",)), ("", ("required_cash", "cash")), ("", ("recommendation",)), ("", ("ceo_decision",))])
    L += sec("Loans and Debt Register", ["Lender", "Original Amount", "Interest Rate", "Payment", "Balance"], "loans",
             [("", ("lender", "name")), ("", ("original_amount", "amount")), ("", ("interest_rate", "rate")), ("", ("payment",)), ("", ("balance",))])
    L += sec("Investment Portfolio", ["Asset", "Type", "Cost Basis", "Current Value", "Recommendation"], "investments",
             [("", ("asset", "name")), ("", ("type",)), ("", ("cost_basis",)), ("", ("current_value", "value")), ("", ("recommendation",))])
    L += sec("Acquisition and M&A Pipeline", ["Target", "Purchase Price", "Stores / Assets", "Recommendation", "Status"], "acquisitions",
             [("", ("target", "name")), ("", ("purchase_price", "price")), ("", ("stores", "assets")), ("", ("recommendation",)), ("", ("status",))])
    for title, rel in (("Assumptions and Unknowns", "assumptions-and-unknowns.md"), ("Screenshot Intake Log", "screenshot-intake-log.md")):
        p = ledger_dir(v) / rel
        rows = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("|")] if p.exists() else []
        L += ["", f"## {title}"] + (rows if len(rows) > 2 else ["No entries yet."])
    L += ["", "## CFO Lessons and Pattern Log", "- none recorded yet", "",
          "## Next Review Checklist"]
    if lat:
        L += ["- Screenshots requested: " + "; ".join(lat["summary"].get("next_upload", []) or ["none"])]
    else:
        L += ["- Screenshots requested: dashboard, map, first-store options"]
    L += ["- Decisions pending: see Decision Register", "- Tests to run: see wiki/tests", "- Next weekly review trigger: end of the in-game week"]
    out = v / "exports" / MEM_FILE
    out.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
    return out


def export_all(v: Path):
    return [export_kb(v), export_memory(v)]
