"""Keep the database in step with the ledger: one transactional rebuild after every filing.

Safe by design: if the rebuild fails, the previous database state is kept, the failure is recorded, and readers see a stale
signature and fall back to the ledger. It never blocks or corrupts a week. It does nothing until `coffee db init` has run.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import dbhealth
from ..util import file_lock, lock_path, note_problem


def refresh(v: Path) -> str:
    """Returns 'skipped', 'ok', 'unreachable' or 'failed'."""
    if not dbhealth.db_path().exists():
        return "skipped"
    from .conn import connect, migrate
    from .load import rebuild
    from .queries import reset
    try:
        with file_lock(lock_path("db.lock"), blocking=True):
            con = connect()
            try:
                migrate(con)
                rebuild(v, con)
            finally:
                con.close()
        reset()
        return "ok"
    except (sqlite3.OperationalError, PermissionError, OSError) as e:
        if "unable to open" in str(e) or "readonly" in str(e).lower() or isinstance(e, PermissionError):
            reset()
            return "unreachable"      # this process (e.g. a sandbox) cannot reach the file; the Mac worker refreshes it within seconds
        note_problem(__name__, e)
        reset()
        return "failed"
    except Exception as e:
        reset()
        if "authorization denied" in str(e):
            return "unreachable"      # a sandbox that may not open the file; the Mac worker refreshes it
        note_problem(__name__, e)
        return "failed"


def disagreements(v: Path) -> list:
    """Totals where the database and the ledger differ (empty when they agree or no database exists)."""
    if not dbhealth.db_path().exists():
        return []
    from .conn import connect
    from .totals import compare
    try:
        con = connect()
        try:
            return compare(v, con)
        finally:
            con.close()
    except Exception as e:
        if "authorization denied" in str(e):
            return []                 # sandbox cannot open the database; the worker checks it
        note_problem(__name__, e)
        return [f"could not compare: {e}"]
