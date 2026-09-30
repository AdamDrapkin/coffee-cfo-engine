"""`coffee upkeep --fix`: the maintainer the chat can summon. Runs vetted, deterministic repairs and escalates the rest.

Nothing here writes code or asks a model anything. It does what a careful person would do with the upkeep queue:
refresh the database and its export, delete old screenshots, clear harmless noise from the problem log, prove that the
skill docs still match the program (every command and file they name exists) and stamp them reviewed, and record anything
it cannot fix in wiki/outputs/engine-issues.md (append-only) so it is never lost and is visible in one place.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .util import atomic_write, note_problem

SKILL = ".agents/skills/coffee-week"
ISSUES = "wiki/outputs/engine-issues.md"
BENIGN = ("authorization denied",)            # the chat sandbox cannot open the database; the Mac worker can


def _header() -> str:
    d = time.strftime("%Y-%m-%d")
    return (f"---\ntitle: Engine issues\ndate_created: '{d}'\ndate_modified: '{d}'\nsummary: Problems the automatic upkeep could not fix.\n"
            "tags:\n- outputs\ntype: index\nstatus: final\n---\n\n# Engine issues\n\nThings the automatic upkeep could not fix. Append-only. Closed ones are marked [closed].\n\n")


def report_issue(v: Path, text: str, source: str = "antigravity") -> bool:
    """Append an issue once (same text is not repeated). Returns True when it was new."""
    p = v / ISSUES
    body = p.read_text(encoding="utf-8") if p.exists() else _header()
    key = re.sub(r"\s+", " ", text.strip())[:200]
    if key in re.sub(r"\s+", " ", body):
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, body.rstrip("\n") + f"\n- [open] {time.strftime('%Y-%m-%d %H:%M')} ({source}): {text.strip()}\n")
    return True


def open_issues(v: Path) -> list:
    p = v / ISSUES
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("- [open]")] if p.exists() else []


def docs_mismatches(v: Path) -> list:
    """Commands and files named in the skill docs and AGENTS.md that do not exist in the program."""
    coffee = (v / "scripts" / "coffee.py").read_text(encoding="utf-8")
    cmds = set(re.findall(r'add_parser\("([\w-]+)"', coffee))
    skill = v / SKILL
    bad = []
    docs = list(skill.rglob("*.md")) + [v / "AGENTS.md"]
    for d in docs:
        if not d.exists() or d.name in ("run-postmortem.md", "upkeep-log.md"):
            continue
        t = d.read_text(encoding="utf-8")
        for c in set(re.findall(r"scripts/run\.sh ([a-z][\w-]*)", t)):
            if c not in cmds:
                bad.append(f"{d.name} names the command '{c}', which does not exist")
        for ref in set(re.findall(r"`references/([\w.-]+\.md)`", t)):
            if not (skill / "references" / ref).exists():
                bad.append(f"{d.name} names references/{ref}, which does not exist")
    return bad


def run(v: Path) -> list:
    from . import retention, upkeep
    out = []
    try:                                                    # 1. database and its text export
        from . import dbhealth
        if dbhealth.db_path().exists():
            from .db import cli as dbcli, export, sync
            if "STALE" in dbcli.status(v):
                out.append(f"database refresh: {sync.refresh(v)}")
            exp = v / "wiki" / "db-export" / "store_week.csv"
            if not exp.exists() or time.time() - exp.stat().st_mtime > 3 * 86400:
                if sync.refresh(v) == "ok":
                    out.append(f"database export: {export.export(v)} rows")
    except Exception as e:
        note_problem(__name__, e)
    n = retention.purge_screenshots(v)                     # 2. old screenshots
    if n:
        out.append(f"deleted {n} screenshots older than {retention.KEEP_DAYS} days")
    prob = v / ".coffee-work" / "problems.log"              # 3. problem log: drop known noise, escalate the rest
    if prob.exists() and prob.stat().st_size:
        lines = prob.read_text(encoding="utf-8").splitlines()
        real = [ln for ln in lines if not any(b in ln for b in BENIGN)]
        for ln in real[-5:]:
            report_issue(v, f"problem log: {ln[:200]}", "auto-upkeep")
        arch = v / ".coffee-work" / "problems-archive.log"
        arch.write_text((arch.read_text(encoding="utf-8") if arch.exists() else "") + "\n".join(lines) + "\n", encoding="utf-8")
        prob.write_text("", encoding="utf-8")
        out.append(f"problem log cleared ({len(lines) - len(real)} harmless, {len(real)} escalated)")
    bad = docs_mismatches(v)                                # 4. prove the docs match the program, then stamp them reviewed
    if bad:
        for b in bad[:5]:
            report_issue(v, "skill docs out of date: " + b, "auto-upkeep")
        out.append(f"skill docs out of date ({len(bad)}); escalated")
    else:
        if any("engine code changed" in i for i in upkeep.items(v)):
            upkeep.done(v, "automatic check: every command and file named in the skill docs exists in the program")
            out.append("skill docs checked against the program and stamped reviewed")
    for i in upkeep.items(v):                               # 5. what remains needs a person or a maintenance session
        if i.startswith("Build a parser for the layout"):
            out.append("a layout is seen repeatedly: teach it with learn-layout (references/self-repair.md)")
        else:
            report_issue(v, i, "auto-upkeep")
    q = upkeep.refresh(v)
    n_open = len(open_issues(v))
    out.append(f"upkeep queue now: {len(q)} item(s); open engine issues: {n_open}" + (f" (see {ISSUES})" if n_open else ""))
    return out
