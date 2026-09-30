#!/usr/bin/env python3
"""coffee: the Coffee Inc. knowledge-base toolchain. See README.md."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coffeekb import (absorb, agent, coverage, week, digest, doctor, export, frames, gemini_client, health, index, lint,
                      ready, relocate, render, research, seed, session, sync, util, watcher)
from coffeekb.gemini_client import BackendError


def show(out: session.Outcome):
    if out.status == "done":
        print(f"Done. Briefing: {out.briefing}")
        latest = render.load_latest(util.vault())
        if latest and latest.get("summary"):
            s = latest["summary"]
            print(f"\nDecision: {s.get('decision')}\nConfidence: {s.get('confidence')}")
            for k in ("do_now", "do_not", "next_upload"):
                for x in s.get(k, []):
                    print(f"  {k.replace('_', ' ')}: {x}")
        if out.warnings:
            print(f"\nWARNING: the checker flagged {len(out.warnings)} item(s). A flagged dollar figure is not from the CEO's screenshots or words "
                  "and is not labeled an estimate: tell the CEO it is a guess, or relabel it and absorb again. Other flags (confidence, duplicates, size) are advice to act on:")
            for w in out.warnings[:6]:
                print("  -", w)
        if out.moved:
            print(f"Moved {len(out.moved)} file(s) to raw/.")
        for line in getattr(out, "info", []):
            print(f"NOTE: {line}")
        for g in coverage.gaps(util.vault()):
            print(f"COVERAGE GAP: {g}")
        level, msg = health.report(util.vault())
        print(f"\nSESSION HEALTH [{level}]: {msg}")
        if out.kept:
            print(f"Left {len(out.kept)} unreadable file(s) in inbox/. Retake with the numbers visible.")
        return 0
    if out.status == "nothing":
        print(out.message)
        return 0
    print(f"Failed ({out.kind}): {out.message}")
    print("Your files are still in inbox/. Nothing was lost.")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="coffee", description="Coffee Inc. CFO knowledge base")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="batch inbox/, one Gemini call")
    p.add_argument("--note", default="", help="a few words, e.g. 'choosing a location, three options'")
    p = sub.add_parser("ask", help="ask a question against the digest and wiki")
    p.add_argument("question")
    sub.add_parser("close", help="weekly close")
    p = sub.add_parser("research", help="sourced research on one topic")
    p.add_argument("topic")
    p = sub.add_parser("absorb", help="file an answer saved in inbox/answer-paste.md")
    p.add_argument("--by", default="antigravity", help="who read the screenshots")
    p = sub.add_parser("research-absorb", help="file research the chat agent saved in inbox/research-paste.md")
    p.add_argument("--by", default="antigravity")
    p = sub.add_parser("analysis-absorb", help="file the CFO analysis the chat wrote in inbox/analysis-paste.md")
    p.add_argument("--by", default="antigravity")
    p = sub.add_parser("review-file", help="file values a person read from unrecognized screens (plain table in inbox/review-paste.md)")
    p.add_argument("--by", default="antigravity")
    p = sub.add_parser("learn-layout", help="teach the engine a screen layout from inbox/layout-paste.md (validated against real screen text; see references/self-repair.md)")
    p.add_argument("--by", default="antigravity")
    p = sub.add_parser("find", help="search saved text (records, briefings, reviews, every screen's text) instead of opening images")
    p.add_argument("query", nargs="+")
    p = sub.add_parser("facts", help="structured history of a menu item, metric, group or decision (no images needed)")
    p.add_argument("topic", nargs="+")
    p = sub.add_parser("decide", help="set the status of a decision: decide <words> <open|done|not-possible|superseded|unknown> <note>")
    p.add_argument("fragment")
    p.add_argument("status")
    p.add_argument("note", nargs="?", default="")
    p = sub.add_parser("resolve", help="close an open unknown: resolve <words> <note>")
    p.add_argument("fragment")
    p.add_argument("note", nargs="?", default="")
    p = sub.add_parser("golden", help="save or check the frozen baseline used to prove the database migration: golden <save|check>")
    p.add_argument("action", choices=["save", "check"])
    p = sub.add_parser("db", help="database health: db check")
    p.add_argument("action", choices=["check", "init", "status", "refresh", "compare", "export", "verify"])
    sub.add_parser("ocr-archive", help="save the text of archived screenshots that do not have it yet")
    sub.add_parser("coverage", help="list screens archived whose information was never recorded")
    p = sub.add_parser("week", help="read, check, file and summarize a whole batch of screens in seconds")
    p.add_argument("--expect", type=int, default=None, help="how many files the CEO said they uploaded")
    p.add_argument("--reprocess", default=None, help="re-read archived screens whose file name contains this text (for repairs)")
    p.add_argument("--keep-session", action="store_true", help="do not start a new session marker")
    p = sub.add_parser("report-issue", help="record an engine problem you cannot fix: report-issue <one line>")
    p.add_argument("text", nargs="+")
    p = sub.add_parser("upkeep", help="show or clear the queue of skill files that need redoing")
    p.add_argument("--fix", action="store_true", help="run the automatic repairs and escalate the rest")
    p.add_argument("--done", default=None, help="record that the skill docs were reviewed, with a note of what changed")
    sub.add_parser("session-start", help="mark the start of a new chat conversation (run once, first)")
    sub.add_parser("session-health", help="say whether this conversation is still good or a new one is due")
    p = sub.add_parser("inbox-ready", help="wait until everything in inbox/ has finished syncing")
    p.add_argument("--expect", type=int, default=None, help="how many files the CEO said they uploaded")
    p.add_argument("--wait", type=float, default=60.0, help="seconds to wait in this call (default 60)")
    p.add_argument("--settle", type=float, default=15.0, help="seconds the file set must stop changing")
    p = sub.add_parser("frames", help="turn a screen recording into one frame per distinct screen")
    p.add_argument("video")
    p.add_argument("--fps", type=float, default=2.0, help="samples per second (default 2)")
    p.add_argument("--max", type=int, default=80, help="most frames to keep (default 80)")
    sub.add_parser("audit", help="re-check filed research labels against the current rules")
    sub.add_parser("export", help="regenerate the two master-prompt files")
    p = sub.add_parser("lint", help="deterministic checks")
    p.add_argument("--fix-index", action="store_true")
    p = sub.add_parser("doctor", help="auth, quota, keys, last call")
    p.add_argument("--offline", action="store_true")
    sub.add_parser("digest", help="print the state digest")
    sub.add_parser("watch", help="the Mac worker")
    p = sub.add_parser("install-agent", help="keep watch running under launchd")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sub.add_parser("sync", help="commit and push to the private repo")
    sub.add_parser("seed", help="create knowledge-base stubs and phone files")
    p = sub.add_parser("relocate", help="move the vault, e.g. into the iCloud Obsidian folder")
    p.add_argument("new_path")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--already-moved", action="store_true", help="you moved the folder in Finder; just re-point everything")
    a = ap.parse_args(argv)
    v = util.vault()

    try:
        if a.cmd == "ingest":
            seed.seed(v)
            return show(session.run_session(v, gemini_client.get_backend(), "ingest", note=a.note))
        if a.cmd == "ask":
            seed.seed(v)
            extras = ["# Relevant notes (from the wiki)\n\n" + "\n\n".join(session.relevant_notes(v, a.question) or ["none found"])]
            return show(session.run_session(
                v, gemini_client.get_backend(), "ask", note=a.question, use_inbox=False, extra_context=extras,
                prompt_tail="Answer the CEO's question using only the digest and the relevant notes. "
                            "Produce the briefing and the single JSON block; ledger_updates should be empty unless the answer records a new decision."))
        if a.cmd == "close":
            seed.seed(v)
            return show(session.run_session(v, gemini_client.get_backend(), "close", note="WEEKLY CLOSE"))
        if a.cmd == "research":
            seed.seed(v)
            out = research.run_research(v, gemini_client.get_backend(), a.topic)
            if out.status == "done":
                print(f"Done: {out.message}. Raw: {out.briefing}")
                for x in out.kept:
                    print("  FLAGGED (not obeyed):", x)
                return 0
            print(f"Failed ({out.kind}): {out.message}")
            return 1
        if a.cmd == "absorb":
            seed.seed(v)
            return show(absorb.run_absorb(v, by=a.by))
        if a.cmd == "research-absorb":
            seed.seed(v)
            out = research.run_research_absorb(v, by=a.by)
            if out.status == "done":
                print(f"Done: {out.message}. Raw: {out.briefing}")
                print("Labels decided by the toolchain (report these to the CEO exactly):")
                for line in out.labeled:
                    print("  ", line)
                for x in out.kept:
                    print("  FLAGGED (not obeyed):", x)
                return 0
            print(f"{'Nothing to do' if out.status == 'nothing' else 'Failed'}: {out.message}")
            return 0 if out.status == "nothing" else 1
        if a.cmd == "analysis-absorb":
            out = absorb.run_analysis(v, by=a.by)
            print(out.message)
            for w in out.warnings:
                print(f"WARNING: {w}")
            level, msg = health.report(v)
            print(f"SESSION HEALTH [{level}]: {msg}")
            return 0 if out.status == "done" else 1
        if a.cmd == "review-file":
            out = absorb.run_review_file(v, by=a.by)
            print(out.message)
            return 0 if out.status == "done" else 1
        if a.cmd == "learn-layout":
            from coffeekb import learned
            ok, msg = learned.learn(v)
            print(msg)
            return 0 if ok else 1
        if a.cmd == "find":
            from coffeekb import search
            hits = search.find(v, " ".join(a.query))
            print("\n".join(hits) if hits else "No saved text mentions that. The vault has no record of it; say so, and ask the CEO instead of opening images.")
            return 0
        if a.cmd == "facts":
            from coffeekb import lookup
            print(lookup.facts(v, " ".join(a.topic)))
            from coffeekb.db import queries as dbq
            if dbq.stale_note():
                print(dbq.stale_note())
            return 0
        if a.cmd == "decide":
            from coffeekb import decisions
            print(decisions.decide(v, a.fragment, a.status, a.note))
            return 0
        if a.cmd == "resolve":
            from coffeekb import decisions
            print(decisions.resolve(v, a.fragment, a.note))
            return 0
        if a.cmd == "golden":
            from coffeekb import golden
            if a.action == "save":
                print(f"baseline saved: {golden.save(v).relative_to(v)}")
                return 0
            diffs = golden.check(v)
            print("\n".join(diffs) if diffs else "golden: every answer and total matches the baseline")
            return 1 if diffs else 0
        if a.cmd == "db":
            from coffeekb.db import cli as dbcli
            code, text = dbcli.run(v, a.action)
            print(text)
            return code
        if a.cmd == "ocr-archive":
            from coffeekb import search
            n = 1
            total = 0
            while n:
                n = search.archive_ocr(v, 80)
                total += n
            print(f"ocr-archive: {total} screenshot(s) saved as text")
            return 0
        if a.cmd == "coverage":
            found = coverage.gaps(v)
            print("\n".join(f"COVERAGE GAP: {g}" for g in found) if found else "coverage: every archived kind of screen has records")
            return 1 if found else 0
        if a.cmd == "week":
            seed.seed(v)
            r = week.run(v, expect=a.expect, new_session=not a.keep_session, reprocess=a.reprocess)
            print(r["text"])
            return 0 if r["status"] in ("done", "nothing", "empty") else 3
        if a.cmd == "report-issue":
            from coffeekb import autofix
            print("Recorded." if autofix.report_issue(v, " ".join(a.text)) else "Already recorded.")
            return 0
        if a.cmd == "upkeep":
            from coffeekb import upkeep
            if a.fix:
                from coffeekb import autofix
                print("\n".join("UPKEEP: " + x for x in autofix.run(v)))
                return 0
            if a.done:
                print(upkeep.done(v, a.done))
                return 0
            q = upkeep.refresh(v)
            print("\n".join(f"UPKEEP DUE: {i}" for i in q) if q else "upkeep: nothing due")
            return 0
        if a.cmd == "session-start":
            print(health.start(v))
            return 0
        if a.cmd == "session-health":
            level, msg = health.report(v)
            print(f"SESSION HEALTH [{level}]: {msg}")
            return 0
        if a.cmd == "inbox-ready":
            ok, msg = ready.check(v, expect=a.expect, wait=a.wait, settle=a.settle)
            print(msg)
            return 0 if ok else 3
        if a.cmd == "frames":
            try:
                r = frames.extract(v, Path(a.video), fps=a.fps, max_frames=a.max)
            except frames.FramesError as e:
                print(f"Failed: {e}")
                return 1
            print(f"{len(r.frames)} distinct screens from {r.duration:.0f} s of video. Folder: {r.folder.relative_to(v)}")
            for p_, t in r.frames:
                print(f"  {p_.relative_to(v)}   t={t:.1f}s")
            if r.capped:
                print(f"NOTE: capped at {a.max} frames. Record shorter clips or pause less often.")
            print("These are scratch files. They are deleted after a day; the video itself is yours to delete.")
            return 0
        if a.cmd == "audit":
            n = research.audit(v)
            print(f"audit: {n} label(s) lowered" if n else "audit: all filed labels hold up")
            return 0
        if a.cmd == "export":
            for p in export.export_all(v):
                print("wrote", p.relative_to(v))
            return 0
        if a.cmd == "lint":
            issues = lint.run(v, fix_index=a.fix_index)
            print("\n".join(issues) if issues else "lint: clean")
            return 1 if issues else 0
        if a.cmd == "doctor":
            return doctor.run(v, offline=a.offline)
        if a.cmd == "digest":
            print(digest.build(v))
            return 0
        if a.cmd == "watch":
            seed.seed(v)
            return watcher.watch(v)
        if a.cmd == "install-agent":
            return agent.uninstall() if a.uninstall else agent.install(v, yes=a.yes)
        if a.cmd == "sync":
            print(sync.sync(v))
            return 0
        if a.cmd == "seed":
            print(f"seeded {seed.seed(v)} knowledge-base notes")
            return 0
        if a.cmd == "relocate":
            return relocate.relocate(v, Path(a.new_path), yes=a.yes, already_moved=a.already_moved)
    except session.Busy as e:
        print(f"Busy: {e} Try again in a minute.")
        return 2
    except BackendError as e:
        print(f"Backend problem: {e}")
        return 1
    except sync.SyncError as e:
        print(f"Sync problem: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
