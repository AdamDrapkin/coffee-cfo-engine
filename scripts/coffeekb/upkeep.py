"""Skill upkeep: notices when the hand-written skill files need redoing and queues the work.

It cannot rewrite the docs itself (they hold judgment). It watches four signals, writes the queue to
references/upkeep-queue.md, and prints a one-line notice at the end of every `coffee week`.

Signals
1. A layout in parser-gaps.md seen 2 or more times: build that parser.
2. Speed regression: the last 5 runs of 60 screens or fewer have a median over the pipeline budget (45 s).
3. Recognition drift: 3 of the last 5 runs had screens needing eyes.
4. Doc drift: the engine's code changed since the docs were last reviewed (a hash of the engine files is
   stored at review time; `coffee upkeep --done "what changed"` stores a new one and clears the queue).
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from .util import atomic_write, note_problem

SKILL = ".agents/skills/coffee-week"
ENGINE = ["scripts/coffeekb/week.py", "scripts/coffeekb/week_store.py", "scripts/coffeekb/week_dedupe.py", "scripts/coffeekb/packet.py", "scripts/coffeekb/screens.py", "scripts/coffeekb/parsers_menu.py", "scripts/coffeekb/parsers_store.py", "scripts/coffeekb/parsers_news.py", "scripts/coffeekb/parsers_build.py", "scripts/coffeekb/review.py",
          "scripts/coffeekb/vision.py", "scripts/coffeekb/absorb.py", "scripts/coffeekb/validate.py", "scripts/native/ocr.swift",
          "scripts/coffeekb/db/load.py", "scripts/coffeekb/db/queries.py", "scripts/coffeekb/db/sync.py", "scripts/coffeekb/db/totals.py", "scripts/coffeekb/db/conn.py", "scripts/coffeekb/db/export.py"]
BUDGET_S = 45


def _hash(v: Path) -> str:
    h = hashlib.sha1()
    for f in ENGINE:
        p = v / f
        h.update(p.read_bytes() if p.exists() else b"-")
    return h.hexdigest()


def _rows(v: Path, name: str):
    p = v / SKILL / "references" / name
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("| 20"):
            out.append([c.strip() for c in ln.strip("|").split("|")])
    return out


def items(v: Path) -> list:
    q = []
    for r in _rows(v, "parser-gaps.md"):
        try:
            if int(r[3]) >= 2:
                q.append(f"Build a parser for the layout '{r[1]}' (seen {r[3]} times, sample {r[2]}), add a test in tests/test_screens.py, then move it to built in parser-gaps.md.")
        except (ValueError, IndexError):
            pass
    runs = _rows(v, "run-log.md")[-5:]
    small = [float(r[5]) for r in runs if r[1].isdigit() and int(r[1]) <= 60]
    if len(small) >= 3 and statistics.median(small) > BUDGET_S:
        q.append(f"Speed regression: median of the last runs is {statistics.median(small):.0f} s against a {BUDGET_S} s budget. Find the slow phase in the packet timings and update pipeline.md.")
    if len(runs) >= 3 and sum(1 for r in runs if r[3].isdigit() and int(r[3]) > 0) >= 3:
        q.append("Recognition drift: 3 of the last 5 runs had screens needing eyes. Read parser-gaps.md and build the parsers.")
    try:
        from . import codecheck
        drift = codecheck.big_files() + codecheck.import_cycles()
        if drift:
            q.append("Code drift (Vibe Persona architecture rules): " + "; ".join(drift[:4]) + ". Split or fix at the next natural opportunity.")
    except Exception as e:
        note_problem(__name__, e)
    try:
        from . import dbhealth
        if dbhealth.db_path().exists():
            bad = [b for b in dbhealth.check() if "authorization denied" not in b]      # the chat sandbox cannot open the database; the worker can
            if bad:
                q.append("Database health: " + "; ".join(bad[:3]))
            from .db import cli as dbcli
            st = dbcli.status(v)
            if "STALE" in st:
                q.append("The database is behind the ledger (" + st[:60] + "). Run: sh scripts/run.sh db refresh")
            exp = v / "wiki" / "db-export" / "store_week.csv"
            if not exp.exists() or time.time() - exp.stat().st_mtime > 3 * 86400:
                q.append("The database text export is more than 3 days old. Run: sh scripts/run.sh db export (the worker does it daily).")
    except Exception as e:
        note_problem(__name__, e)
    prob = v / ".coffee-work" / "problems.log"
    if prob.exists() and prob.stat().st_size > 0:
        lines = [ln for ln in prob.read_text(encoding="utf-8").splitlines() if "authorization denied" not in ln]
        if lines:
            q.append(f"{len(lines)} handled problem(s) are logged in .coffee-work/problems.log; latest: {lines[-1][:140]}. Read them and fix the cause.")
    times = [float(r[5]) for r in _rows(v, "run-log.md")[-6:] if len(r) > 5]
    if len(times) >= 4 and times[-1] > 2 * max(0.1, statistics.median(times[:-1])) and times[-1] > 20 and times[-2] > 2 * max(0.1, statistics.median(times[:-2])):   # two slow runs in a row, not one
        q.append(f"Filing got slower: the last run took {times[-1]:.0f} s against a median of {statistics.median(times[:-1]):.0f} s.")
    try:
        import subprocess
        size = (subprocess.run(["du", "-sk", str(Path.home() / ".coffee-inc-kb-git")], capture_output=True, text=True, timeout=30).stdout.split() or ['0'])[0]
        if int(size) > 400_000:
            q.append(f"The backup repository is {int(size) // 1024} MB. Text only should stay far below this; check what is being committed.")
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as e:
        note_problem(__name__, e)
    stamp = v / SKILL / "references" / ".reviewed.json"
    try:
        last = json.loads(stamp.read_text(encoding="utf-8")).get("hash")
    except (OSError, ValueError):
        last = None
    if last != _hash(v):
        q.append("The engine code changed since the skill docs were last reviewed. Re-read org-chart.md, pipeline.md, review-desk.md and self-healing.md against the code, edit what no longer matches, then run `coffee upkeep --done \"what you changed\"`.")
    return q


def refresh(v: Path) -> list:
    q = items(v)
    body = "# Upkeep queue\n\nWritten automatically after every `coffee week`. Empty means nothing is due.\n\n"
    body += "\n".join(f"- [ ] {i}" for i in q) if q else "Nothing due.\n"
    d = v / SKILL / "references"
    if d.exists():
        atomic_write(d / "upkeep-queue.md", body + "\n")
    return q


def done(v: Path, note: str) -> str:
    d = v / SKILL / "references"
    atomic_write(d / ".reviewed.json", json.dumps({"hash": _hash(v), "at": time.strftime("%Y-%m-%d"), "note": note}))
    log = d / "upkeep-log.md"
    prev = log.read_text(encoding="utf-8") if log.exists() else "# Upkeep log\n\nEach time the skill docs were reviewed against the engine. Newest last.\n\n"
    atomic_write(log, prev.rstrip("\n") + f"\n- {time.strftime('%Y-%m-%d')}: {note}\n")
    refresh(v)
    return "Upkeep recorded. The queue is refreshed."
