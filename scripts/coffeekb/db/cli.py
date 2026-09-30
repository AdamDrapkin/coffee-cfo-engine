"""`coffee db <action>`: init, status, refresh (rebuild from the ledger), compare, export, verify, check."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .. import dbhealth
from .conn import DbError, connect, migrate
from .load import rebuild, signature


def status(v: Path) -> str:
    path = dbhealth.db_path()
    if not path.exists():
        return f"no database yet ({path}). Run: sh scripts/run.sh db init"
    con = connect()
    try:
        sig = con.execute("select value from meta where key='ledger_signature'").fetchone()
        fresh = bool(sig) and sig[0] == signature(v)
        n = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("store_week", "menu_week", "review", "decision", "source", "document")}
        return f"database {'FRESH' if fresh else 'STALE (the ledger changed since the last refresh)'}; rows: " + ", ".join(f"{k} {n[k]}" for k in n)
    finally:
        con.close()


def run(v: Path, action: str) -> tuple:
    """Returns (exit code, text)."""
    from . import export
    try:
        if action == "check":
            p = dbhealth.check()
            return (1, "\n".join(p)) if p else (0, "db: healthy")
        if action == "init":
            con = connect()
            applied = migrate(con)
            con.close()
            return 0, f"db ready at {dbhealth.db_path()}; migrations applied now: {', '.join(applied) or 'none (already up to date)'}"
        if action == "status":
            return 0, status(v)
        if action == "refresh":
            con = connect()
            migrate(con)
            counts = rebuild(v, con)
            con.close()
            return 0, "database rebuilt from the ledger: " + ", ".join(f"{k} {n}" for k, n in counts.items() if n)
        if action == "compare":
            from .totals import compare
            con = connect()
            d = compare(v, con)
            con.close()
            return (1, "\n".join(d)) if d else (0, "compare: the database and the ledger agree on every total")
        if action == "export":
            n = export.export(v)
            return 0, f"exported {n} rows to {export.EXPORT_DIR}/"
        if action == "verify":
            with tempfile.TemporaryDirectory() as d:
                target = Path(d) / "verify.db"
                n = export.restore(v, target)
                con = connect(target)
                from .totals import totals, normalize, diff
                live = connect()
                a, b = normalize(totals(live)), normalize(totals(con))
                live.close()
                con.close()
            dd = diff(a, b)
            return (1, "verify FAILED:\n" + "\n".join(dd)) if dd else (0, f"verify: rebuilt an empty database from the text export ({n} rows) and every total matches")
    except DbError as e:
        return 1, f"database problem: {e}"
    return 1, f"unknown action {action}"
