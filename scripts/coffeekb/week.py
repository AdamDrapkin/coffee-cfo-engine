"""`coffee week`: one command that reads, checks, files and summarizes a whole batch of screens.

Why: the slow parts of a week were an AI looking at images one at a time and then typing
out hundreds of rows of JSON. Both are mechanical. This engine does them in seconds:

  1. session marker      2. sync gate      3. read every screen in parallel (macOS Vision + star counting)
  4. classify and parse  5. cross-check the numbers    6. de-duplicate against what is already filed
  7. file through the normal validator and writers     8. write a compact packet for the AI

The AI then only has to analyze and decide. Screens the parsers do not recognize stay in the inbox
and are listed under NEEDS EYES, so the AI looks at those few images, not all of them.
"""
from __future__ import annotations

import collections
import json
import re
import time
from pathlib import Path

from . import audit, analysis, briefing as briefing_mod, review, state_page, upkeep, absorb, corrections, coverage, digest, frames, health, inbox, ready, render, screens, vision
from .ledger import ledger_dir
from .session import Busy
from .util import note_problem, atomic_write, file_lock, lock_path, now_iso, read_page
from .week_dedupe import *  # noqa: F401,F403
from .week_dedupe import _norm, _existing, _as_num, _pnum, _menu_prior, _menu_diffs, _same, _dedupe  # noqa: F401
from .week_store import *  # noqa: F401,F403
from .week_store import (_theme, _store_of, _add_store_logging, _menu_items, _add_menu_week, _review_status, _archive_ocr)  # noqa: F401
from .packet import build_packet, _week_state  # noqa: F401


MIN_SCREENS = 25


def _heic_to_png(v: Path, p: Path):
    """Convert with macOS sips into the work folder (the inbox original stays untouched). None on failure."""
    import subprocess
    out = v / ".coffee-work" / "heic" / (p.stem + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
        return out
    try:
        subprocess.run(["sips", "-s", "format", "png", str(p), "--out", str(out)], capture_output=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out.exists() else None


def _collect_inputs(v: Path):
    """Images in the inbox plus frames extracted from videos. Returns (paths, videos, name_of)."""
    sc = inbox.scan(v)
    paths, name_of, videos = [], {}, []
    for p in sc.images:
        if p.suffix.lower() in (".heic", ".heif"):
            conv = _heic_to_png(v, p)
            if conv is None:
                continue      # could not convert; left for the chat
            paths.append(conv)
            name_of[conv] = p.name
            continue
        paths.append(p)
        name_of[p] = p.name
    d = v / "inbox"
    if d.exists():
        for vid in sorted(d.iterdir()):
            if vid.is_file() and vid.suffix.lower() in frames.VIDEO_EXT:
                folder = v / ".coffee-work" / "frames" / frames.slugify(vid.stem)
                fr = sorted(folder.glob("frame-*.png")) if folder.exists() else []
                if fr:
                    videos.append(vid)
                    for f in fr:
                        paths.append(f)
                        name_of[f] = f"{folder.name}/{f.name}"
    return paths, videos, name_of


def run(v: Path, expect=None, new_session=True, log=print, reprocess=None):
    t0 = time.time()
    timing = {}
    lines = []

    def step(name, since):
        timing[name] = round(time.time() - since, 2)
        return time.time()

    t = t0
    if reprocess:
        # re-read archived screens (raw/screenshots) whose names contain the pattern; nothing is moved
        paths = sorted((v / "raw" / "screenshots").glob(f"*{reprocess}*.png"))
        if not paths:
            return {"status": "empty", "text": f"No archived screenshots match '{reprocess}'. Screenshots are deleted after the retention period; their text is still in raw/ocr/screens/.", "timing": timing}
        videos, name_of = [], {p: p.name for p in paths}
        ok, msg = True, "reprocessing archived screens"
        t = step("gate", t)
    else:
        ok, msg = ready.check(v, expect=expect, wait=45, settle=2.0, poll=1.0)
        t = step("gate", t)
        if not ok:
            return {"status": "waiting", "text": msg, "timing": timing}
        paths, videos, name_of = _collect_inputs(v)
    if not paths:
        return {"status": "empty", "text": "The inbox has no screens to read. " + msg, "timing": timing}

    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            raise Busy("Another ingest is already running.")
        try:
            docs = vision.read_files(v, paths)
        except vision.VisionError:
            docs = {}
        missing = [p for p in paths if p not in docs]
        if missing:
            # the chat sandbox cannot run the reader; the Mac worker can, and answers within a couple of seconds
            docs.update(vision.request_worker_read(v, missing, timeout=45))
        t = step("read", t)

        from . import learned
        learned.load(v)
        parsed_raw = {}
        for p in paths:
            if p in docs:
                parsed_raw[p] = screens.parse(screens.Doc.from_json(docs[p]))
        weeks = [x.week for x in parsed_raw.values() if x.week.isdigit()]
        batch_week = collections.Counter(weeks).most_common(1)[0][0] if weeks else ""
        if not batch_week:
            batch_week = str(health.current_week(v) or "")     # a batch of only review screens belongs to the current game week
        parsed = {}
        for p, x in parsed_raw.items():
            if batch_week and not x.week and x.kind in ("weekly_results", "newsletter", "income_statement"):
                x = screens.parse(screens.Doc.from_json(docs[p]), default_week=batch_week)
            parsed[name_of[p]] = x
        t = step("parse", t)

        flags = [f for x in parsed.values() for f in x.flags if x.kind != "other"]
        recognized = {n: x for n, x in parsed.items() if x.kind != "other"}
        needs_eyes = sorted(n for n, x in parsed.items() if x.kind == "other")
        missing_docs = sorted(name_of[p] for p in paths if p not in docs)
        needs_eyes += missing_docs
        by_path = {name_of[p]: p for p in paths}
        flags += review.cross_check(v, by_path, recognized)
        eyes_docs = {n: screens.Doc.from_json(docs[p]) for p in paths if p in docs for n in [name_of[p]] if n in needs_eyes}
        review.dump(v, eyes_docs)
        review.record_gaps(v, eyes_docs)
        low = [f"{n}: text confidence {x.conf:.2f}" for n, x in recognized.items() if x.conf < screens.LOW_CONF]
        flags += low
        review_texts = _add_store_logging(recognized, batch_week)
        _add_menu_week(recognized, [r for x in recognized.values() for r in x.rows], batch_week)
        updates, skipped = _dedupe(v, recognized, flags)
        if reprocess:
            # re-reading archived screens may only ADD logging (reviews, store screen values); it never files events, catalog or weeks again
            keep = lambda u: u["target"] in ("review", "menu-week") or u.get("metric") or (u["target"] == "store" and u["fields"].get("sales"))   # income statements are kept so weeks filed without a week tag get one
            dropped = [u for u in updates if not keep(u)]
            updates = [u for u in updates if keep(u)]
            if dropped:
                skipped["not refiled on a re-read"] = len(dropped)
        menu_changes = [f[len('MENU CHANGE '):] for f in flags if f.startswith('MENU CHANGE ')]
        flags[:] = [f for f in flags if not f.startswith('MENU CHANGE ')]
        if reprocess and not menu_changes:
            # a re-read of archived screens: recover the menu changes the ledger amends already recorded for these files
            mine = {n for n in recognized}
            for _, fm in digest.chron(digest._notes(ledger_dir(v) / "catalog")):
                srcs = {str(x).split("/")[-1] for x in (fm.get("source_screenshot") or [])}
                if fm.get("op") == "amend" and str(fm.get("reason", "")).startswith("Menu values") and srcs & mine:
                    menu_changes.append(f"{fm.get('name')}: " + str(fm["reason"])[len("Menu values on the screen differ from what was on file: "):])
        if any(x.updates and x.kind == "income_statement" for x in recognized.values()):
            flags[:] = [f for f in flags if "top of the income statement" not in f]

        rows = [r for x in recognized.values() for r in x.rows]
        rstore = next((r["value"] for r in rows if r["field"] == "store"), "")
        rtotal = next((r["value"] for r in rows if r["field"] == "review_count"), None)
        review_status = _review_status(v, rstore, batch_week, review_texts, rtotal) if rtotal else {}
        if review_status:
            lines.append(f"REVIEWS: {review_status['captured']} recorded for this week; the game lists {review_status['total']}, of which only the cards on screen can be shown. "
                         "All recorded reviews are in wiki/hubs/hub-reviews.md.")
        intake = [{"file": n, "type": KIND_LABEL.get(x.kind, x.kind), "confidence": "High" if x.conf >= screens.LOW_CONF else "Moderate",
                   "game_week": x.week or batch_week or "not_shown"} for n, x in recognized.items()]
        used = [] if reprocess else [n for n in recognized if "/" not in n] + [vid.name for vid in videos if not needs_eyes]
        filed = {"status": "nothing"}
        bundle_id = time.strftime("%Y%m%d-%H%M%S")
        if recognized:
            data = {
                "intake": intake, "extraction": rows, "ledger_updates": updates,
                "next_upload_request": ["Anything listed as needing a look"] if needs_eyes else ["Nothing further for these screens"],
                "ceo_words": "", "inbox_files_used": used, "bundle": bundle_id,
                "mobile_summary": {"decision": "Screens read and filed; analysis follows", "confidence": "High",
                                   "do_now": ["Read the analysis that follows"], "do_not": ["Do not treat this filing as a decision"],
                                   "next_upload": ["Anything listed as needing a look"] if needs_eyes else ["Nothing further"]},
            }
            text = (briefing_mod.build(v, recognized, rows, updates, skipped, flags, needs_eyes, bundle_id, batch_week, menu_changes, review_status, bool(reprocess), getattr(review.cross_check, 'checked', 0))
                    + "\n```json\n" + json.dumps(data, indent=1) + "\n```\n")
            wd = v / ".coffee-work" / "week"
            wd.mkdir(parents=True, exist_ok=True)
            atomic_write(wd / f"{bundle_id}.json", json.dumps({"week": batch_week, "rows": rows, "flags": flags}, indent=1))
            filed = absorb.file_text(v, text, "vision-ocr", bundle_rows=rows, refresh=False)
        t = step("file", t)
        _archive_ocr(v, bundle_id, docs, name_of)
        from .db import sync as dbsync
        db_status = dbsync.refresh(v)
        flags.extend(f"DB DISAGREES {d}" for d in dbsync.disagreements(v)[:6])
        if db_status == "failed":
            flags.append("DB REFRESH FAILED: answers come from the ledger until `sh scripts/run.sh db refresh` works (see .coffee-work/problems.log)")
        audit_checks, audit_fails = audit.run(v, rows, batch_week, current=not reprocess) if recognized else (0, [])
        flags.extend(f"AUDIT FAIL {x}" for x in audit_fails)
        if new_session and not (isinstance(filed, dict) and filed.get("status") == "nothing" and not recognized):
            lines.insert(0, health.start(v))      # after filing, so the marker holds the week just filed

    timing["total"] = round(time.time() - t0, 2)
    if batch_week:
        atomic_write(v / ".coffee-work" / "week" / "current.json", json.dumps({"week": batch_week, "at": now_iso()}))
    if not reprocess:
        review.log_run(v, len(recognized) + len(needs_eyes), len(recognized), len(needs_eyes), len(flags), round(timing["total"] - timing.get("gate", 0), 2))
    try:
        state_page.write(v)
    except Exception as _e:
        note_problem(__name__, _e)
        pass
    due = upkeep.refresh(v)
    if due:
        lines.append(f"UPKEEP DUE: {len(due)} skill maintenance item(s) queued in .agents/skills/coffee-week/references/upkeep-queue.md. After you have sent the analysis, run `sh scripts/run.sh upkeep --fix` (automatic repairs), then tell the CEO in one line what it fixed and whether anything was escalated.")
    n_all = len(recognized) + len(needs_eyes)
    if n_all < MIN_SCREENS:
        lines.append(f"SCREEN COUNT: only {n_all} screens were in the inbox. A normal week is {MIN_SCREENS} to 28 (25 or more). If the CEO expected more, ask whether the rest finished uploading before you analyze; do not guess what is missing.")
    else:
        lines.append(f"SCREEN COUNT: {n_all} screens, as expected for a normal week ({MIN_SCREENS} to 28).")
    lines.extend(review.staffing(len(recognized) + len(needs_eyes), len(needs_eyes), len(flags)))
    packet = build_packet(v, recognized, needs_eyes, flags, updates, skipped, filed, timing, batch_week, bundle_id, lines, rows, menu_changes, audit_checks, getattr(review.cross_check, 'checked', 0))
    atomic_write(v / ".coffee-work" / "week" / "latest.md", packet)
    return {"status": filed.get("status") if isinstance(filed, dict) else filed.status, "text": packet, "timing": timing,
            "needs_eyes": needs_eyes, "outcome": None if isinstance(filed, dict) else filed}
