"""`coffee watch`: the Mac worker.

Polls inbox/, waits for a quiet spell, sends ONE batch to Gemini, writes the
answer, updates HOME.md and STATUS.md, then syncs to GitHub. Never loops on a
failure: quota waits for the reset, other errors back off.
"""
from __future__ import annotations
import datetime as dt
import os
import time

from . import absorb, frames, inbox, render, vision
from .gemini_client import get_backend, work_root
from .session import Busy, run_session
from .sync import SyncError, sync
from .util import note_problem, append_log, file_lock, now_iso, lock_path

QUIET = 90
POLL = 6
HEARTBEAT = 300
SYNC_EVERY = 600
BACKOFF = {"quota": 900, "auth": 3600, "timeout": 900, "error": 900, "rejected": 1800}


def _future(iso: str):
    try:
        t = dt.datetime.fromisoformat(iso)
    except Exception as _e:
        note_problem(__name__, _e)
        return None
    return t if t > dt.datetime.now() else None


def _extract_new_videos(v, state: dict, log):
    """Videos dropped in inbox/ get their frames extracted as soon as the file stops growing."""
    inbox_dir = v / "inbox"
    if not inbox_dir.exists():
        return
    sizes = state.setdefault("vsizes", {})
    done = state.setdefault("vdone", set())
    for p in inbox_dir.iterdir():
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in frames.VIDEO_EXT:
            continue
        size = p.stat().st_size
        key = f"{p.name}:{size}"
        if key in done or size == 0:
            continue
        if sizes.get(p.name) != size:
            sizes[p.name] = size            # still arriving (iCloud); look again next pass
            continue
        try:
            r = frames.extract(v, p)
            log(f"[watch] frames: {p.name} -> {len(r.frames)} screens")
        except Exception as e:
            log(f"[watch] frames failed for {p.name}: {e}")
        done.add(key)


def _preread_images(v, state: dict, log):
    """Read new inbox screens ahead of time, so `coffee week` finds them already read."""
    try:
        sc = inbox.scan(v)
        seen = state.setdefault("preread", {})
        fresh = [p for p in sc.images if p.suffix.lower() not in (".heic", ".heif")
                 and seen.get(p.name) == p.stat().st_size and not vision.cached(v, p)]
        for p in sc.images:
            seen[p.name] = p.stat().st_size      # only read a file once its size held steady between passes
        if fresh:
            t = time.time()
            vision.read_files(v, fresh)
            vision.second_read(v, fresh)
            log(f"[watch] pre-read {len(fresh)} screens in {time.time() - t:.1f} s")
    except Exception as e:  # never let a read problem stop the worker
        log(f"[watch] pre-read skipped: {e}")


def _daily_export(v, state: dict, log) -> None:
    """Once a day, write the database as text (CSV) so the git backup can always rebuild it."""
    day = time.strftime("%Y-%m-%d")
    if state.get("db_export") == day:
        return
    state["db_export"] = day
    from . import dbhealth
    if not dbhealth.db_path().exists():
        return
    try:
        from .db import export, sync
        sync.refresh(v)
        log(f"[watch] database exported: {export.export(v)} rows")
    except Exception as e:
        note_problem(__name__, e)


def _daily_purge(v, state: dict, log) -> None:
    """Once a day, delete archived screenshots older than the retention period (their text stays)."""
    day = time.strftime("%Y-%m-%d")
    if state.get("purge_day") == day:
        return
    state["purge_day"] = day
    from . import retention
    n = retention.purge_screenshots(v)
    if n:
        log(f"[watch] deleted {n} screenshots older than {retention.KEEP_DAYS} days")


def _keep_db_fresh(v, state: dict, log) -> None:
    """The worker can always reach the database; when the ledger changed (for example from a sandboxed chat), rebuild it within seconds."""
    from . import dbhealth
    if not dbhealth.db_path().exists() or time.time() - state.get("db_checked", 0) < 4:
        return
    state["db_checked"] = time.time()
    try:
        from .db.load import signature
        from .db import sync, conn
        sig = signature(v)
        if sig == state.get("db_sig"):
            return
        con = conn.connect()
        try:
            row = con.execute("select value from meta where key='ledger_signature'").fetchone()
        finally:
            con.close()
        if not row or row[0] != sig:
            log(f"[watch] database refresh: {sync.refresh(v)}")
        state["db_sig"] = sig
    except Exception as e:
        note_problem(__name__, e)


def _waiting_videos(v) -> int:
    d = v / "inbox"
    return sum(1 for p in d.iterdir() if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in frames.VIDEO_EXT) if d.exists() else 0


def tick(v, state: dict, now: float, quiet=QUIET, backend=None, do_sync=True, log=print, auto_ingest=False):
    """One pass of the loop. `state` carries memory between passes."""
    _extract_new_videos(v, state, log)
    _preread_images(v, state, log)
    if do_sync and now - state.get("last_sync", 0) >= SYNC_EVERY:
        state["last_sync"] = now
        try:
            sync(v)
        except SyncError as e:
            log(f"[watch] sync error: {e}")
    sc = inbox.scan(v)
    pasted = bool(absorb.pasted_text(v))
    queue = sc.count + (1 if pasted else 0) + len(sc.placeholders) + _waiting_videos(v)

    if now - state.get("last_beat", 0) >= HEARTBEAT or state.get("dirty"):
        render.save_state(v, worker_seen=now_iso())
        note = "" if auto_ingest or not queue else "Files are waiting. Open the chat and tell it about them; it reviews them and clears the inbox."
        render.render_status(v, queue=queue, error=state.get("error", ""), note=note)
        state["last_beat"] = now
        state["dirty"] = False

    if not auto_ingest:
        # The chat is the interface: it reviews the inbox and files the results itself.
        # The worker only keeps time, extracts video frames, backs up, and reports the queue.
        return "waiting-for-chat" if queue else "idle"

    snap = dict(sc.snapshot)
    if pasted:
        snap["pasted"] = 1
    if snap != state.get("snap") or sc.placeholders:
        state["snap"] = snap
        state["last_change"] = now
        state["attempt_final"] = False
    if not (sc.count or pasted):
        state["error"] = state.get("error", "") if state.get("next_attempt", 0) > now else ""
        return "idle"
    if now - state.get("last_change", now) < quiet:
        return "waiting"
    if state.get("attempt_final"):
        return "already-tried"  # same files, nothing new to try (e.g. an unreadable screenshot)
    if now < state.get("next_attempt", 0):
        return "backoff"
    ra = _future(render.load_state(v).get("retry_after", ""))
    if ra:
        state["next_attempt"] = now + (ra - dt.datetime.now()).total_seconds()
        return "quota-wait"

    backend = backend or get_backend()
    state["attempted"] = snap
    try:
        if pasted and not sc.count:
            out = absorb.run_absorb(v)
        else:
            out = run_session(v, backend, "ingest")
            if pasted and out.status == "done":
                absorb.run_absorb(v)
    except Busy:
        return "busy"

    if out.status == "failed":
        state["error"] = out.message
        state["dirty"] = True
        wait = BACKOFF.get(out.kind, 900)
        if out.kind == "quota" and out.retry_after:
            wait = max(60, (out.retry_after - dt.datetime.now()).total_seconds())
        state["next_attempt"] = now + wait
        if out.kind == "rejected":
            state["attempt_final"] = True
        log(f"[watch] failed ({out.kind}): {out.message}")
        return "failed"
    state["error"] = ""
    state["dirty"] = True
    state["attempt_final"] = True  # done: anything left in inbox was judged unreadable
    if out.status == "done":
        log(f"[watch] done: {out.briefing.name if out.briefing else ''}")
        if do_sync:
            try:
                log("[watch] sync:", sync(v))
            except SyncError as e:
                state["error"] = f"GitHub backup skipped: {e}"
                log(f"[watch] sync error: {e}")
        return "done"
    return "idle"


def watch(v, poll=None, quiet=None, auto_ingest=None):
    if auto_ingest is None:
        auto_ingest = os.environ.get("COFFEE_AUTO_INGEST") == "1"
    try:
        import sys
        sys.stdout.reconfigure(line_buffering=True)   # launchd would otherwise hold the log in a buffer and it would stay empty
    except (AttributeError, ValueError):
        pass
    poll = poll or int(os.environ.get("COFFEE_POLL", POLL))
    quiet = quiet if quiet is not None else int(os.environ.get("COFFEE_QUIET", QUIET))
    with file_lock(lock_path("watch.lock"), blocking=False) as held:
        if not held:
            print("coffee watch is already running.")
            return 1
        state = {}
        print(f"[watch] vault {v}. Auto-ingest {'ON: batches go to Gemini after ' + str(quiet) + 's of quiet' if auto_ingest else 'OFF: the chat reviews the inbox'}.")
        while True:
            try:
                tick(v, state, time.time(), quiet=quiet, auto_ingest=auto_ingest)
            except Exception as e:  # never die; report in plain words
                state["error"] = f"Worker hit a problem: {e}"
                state["dirty"] = True
                print("[watch] error:", e)
                state["next_attempt"] = time.time() + 300
            for _ in range(max(1, int(poll))):          # answer the chat's read requests and pre-read new screens every 2 seconds
                time.sleep(2 if poll > 2 else poll)
                try:
                    vision.serve_requests(v)
                    _preread_images(v, state, print)
                    _daily_export(v, state, print)
                    _daily_purge(v, state, print)
                    _keep_db_fresh(v, state, print)
                    if int(time.time()) % 30 < 2:
                        from . import search
                        search.archive_ocr(v, 30)      # keep every archived screen's text searchable
                except Exception as e:
                    print("[watch] quick pass skipped:", e)
