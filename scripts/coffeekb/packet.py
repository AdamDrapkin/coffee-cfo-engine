"""The packet the chat reads after `coffee week`: what was filed, what to check, and every number computed."""
from __future__ import annotations

import collections
from pathlib import Path

from . import analysis, coverage, digest, health
from .week_store import KIND_LABEL

def _week_state(v: Path):
    weeks = digest._merged_weeks(v)
    keys = sorted((k for k in weeks if k.isdigit()), key=int)
    return weeks, keys


def build_packet(v, recognized, needs_eyes, flags, updates, skipped, filed, timing, batch_week, bundle_id, lines, rows=(), menu_changes=(), audit_checks=0, second_checked=0):
    L = list(lines)
    n = len(recognized) + len(needs_eyes)
    L.append(f"WEEK ENGINE: {n} screens in {timing.get('total', '?')} s "
             f"(sync check {timing.get('gate')} s, read {timing.get('read')} s, parse {timing.get('parse')} s, file {timing.get('file')} s).")
    if not isinstance(filed, dict):
        if filed.status == "failed":
            L.append(f"FILING REJECTED: {filed.message}")
        else:
            adds = collections.Counter(u["target"] + (" amend" if u["op"] == "amend" else "") for u in updates)
            L.append("Filed: " + (", ".join(f"{c} {k}" for k, c in adds.most_common()) or "nothing new") + ". Already on file and skipped: " +
                     (", ".join(f"{c} {k}" for k, c in skipped.items()) or "none") + ".")
            for w in filed.warnings:
                L.append(f"CHECKER WARNING: {w}")
    else:
        L.append("Nothing was filed.")
    if audit_checks:
        L.append(f"AUDIT: {audit_checks} values read back from the ledger and compared with the screens" + (" and all match." if not any(f.startswith("AUDIT FAIL") for f in flags) else "; failures are listed under CHECK THESE."))
    kinds = collections.Counter(KIND_LABEL.get(x.kind, x.kind) for x in recognized.values())
    if kinds:
        L.append("Recognized: " + ", ".join(f"{c} {k}" for k, c in kinds.most_common()) + ".")
    if flags:
        L.append("CHECK THESE (numbers that did not cross-check or read with low confidence):")
        L += [f"  - {f}" for f in flags[:12]]
    if needs_eyes:
        L.append(f"NEEDS EYES: {len(needs_eyes)} screen(s) were not recognized. Open ONLY these, in one batch, and read their text first:")
        L += [f"  - {n_}  " + (f"(text: raw/ocr/{bundle_id}/{n_.replace('/', '_')}.txt)" if (v / "raw" / "ocr" / bundle_id / (n_.replace('/', '_') + ".txt")).exists()
                                 else "(the reader had not read it yet, so no text exists; run week again and it will)") for n_ in needs_eyes[:20]]
        L.append("  To record what they show: write one line per value to inbox/review-paste.md as  FILE | field | value | unit  , then run sh scripts/run.sh review-file . "
                 "No JSON is needed. See .agents/skills/coffee-week/references/filing-cookbook.md.")
    # what changed this week
    weeks, keys = _week_state(v)
    if keys:
        cur = keys[-1]
        prev = keys[-2] if len(keys) > 1 else None
        L.append(f"WEEK {cur} FIGURES (from the ledger):")
        fields = weeks[cur]["fields"]
        for k in ("revenue", "net_income", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "cash_flow", "ending_cash", "debt"):
            if k in fields:
                pv = weeks[prev]["fields"].get(k) if prev else None
                L.append(f"  - {k.replace('_', ' ')}: {fields[k]}" + (f" (week {prev}: {pv})" if pv is not None else ""))
        cash = None
        try:
            cash = float(fields.get("ending_cash")) if fields.get("ending_cash") is not None else None
        except (TypeError, ValueError):
            pass
        if cash is None and prev is not None:
            pass
    # state highlights for the analysis
    state = digest.build(v).splitlines()
    keep = [ln for ln in state if ln.startswith(("## Corrections in force", "- Not true"))]
    if keep:
        L.append("CORRECTIONS IN FORCE (override anything older):")
        L += [f"  {ln}" for ln in keep if ln.startswith("- Not true")][:5]
    store_lines = [ln for ln in state if ln.startswith("- ") and "city" in ln and "name" in ln][:2]
    if store_lines:
        L.append("STORE STATE:")
        L += [f"  {ln[:260]}" for ln in store_lines]
    gaps = coverage.gaps(v)
    L += [f"COVERAGE GAP: {g}" for g in gaps]
    if menu_changes:
        L.append(f"MENU CHANGES ({len(menu_changes)} items differ from what was on file; these move margins, so analyze them):")
        L += [f"  - {c}" for c in menu_changes]
    from . import calendar as gamecal
    L += gamecal.section(v, batch_week)
    L += analysis.menu_ranking(rows)
    L += analysis.build(v, rows, bundle_id, batch_week)
    ch = analysis.changes(v, batch_week)
    L.append("CHANGES SINCE LAST WEEK (from the store values on the screens; check these before explaining any number that moved):")
    L += ch or ["  - none detected among blend, wage, staff and campaigns"]
    if not menu_changes and rows:
        L.append("  - menu prices: NO price changed versus what was on file. If the CEO said he raised prices, they did not show on these screens yet; say so and do not credit any price effect.")
    L += analysis.identical_to_last_week(v, batch_week)
    dec = analysis.decisions_in_force(v)
    if dec:
        L.append("DECISIONS AND COMMITMENTS FROM EARLIER WEEKS (what you recommended and what the CEO did; a number that moved may be the result of one of these):")
        L += dec
    rv = analysis.reviews_on_record(v, batch_week)
    if rv:
        L.append("REVIEWS ON RECORD:")
        L += rv
    kinds = collections.Counter(x.kind for x in recognized.values())
    L.append("WHAT COULD BE WRONG THIS WEEK (state these limits in the analysis; do not hide them):")
    L += analysis.failure_audit(kinds, len(recognized), len(needs_eyes), flags, second_checked)
    L.append("NEXT: (1) Write your full analysis in plain markdown to inbox/analysis-paste.md using the exact headings in .agents/skills/coffee-week/SKILL.md step 5 "
             "(The call, What happened, What customers are saying, Why it happened, Do this first, Runner-up and what would change my mind, Do not do yet, Weak spots and risks, What I could not read or verify, Send next), at least 250 words, no JSON. "
             "(2) Run: sh scripts/run.sh analysis-absorb. It files the analysis as a briefing beside the data briefing and refuses a thin one. "
             "(3) Then give the CEO that same analysis in the chat. Only file a decision record with absorb if you are making a formal decision; if you do, put "
             f"\"bundle\": \"{bundle_id}\" in its JSON.")
    level, msg = health.report(v)
    L.append(f"SESSION HEALTH [{level}]: {msg}")
    return "\n".join(L) + "\n"
