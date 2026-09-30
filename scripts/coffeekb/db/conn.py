"""Connection and migrations. One writer, WAL mode, foreign keys on, a timeout on every wait."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..dbhealth import db_path, location_problems
from ..util import note_problem

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


class DbError(Exception):
    pass


def connect(path=None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    bad = location_problems(path)
    if bad:
        raise DbError("; ".join(bad))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("pragma journal_mode=wal")
    con.execute("pragma foreign_keys=on")
    con.execute("pragma busy_timeout=15000")
    return con


def _applied(con) -> set:
    con.execute("create table if not exists schema_migration (name text primary key, applied_at text)")
    return {r[0] for r in con.execute("select name from schema_migration")}


def migrate(con: sqlite3.Connection) -> list:
    """Apply every numbered migration not yet applied, each in its own transaction. Returns the names applied."""
    done = _applied(con)
    applied = []
    for f in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
        if f.name in done:
            continue
        try:
            con.executescript("begin;\n" + f.read_text(encoding="utf-8") + f"\ninsert into schema_migration values ('{f.name}', datetime('now'));\ncommit;")
        except sqlite3.Error as e:
            con.execute("rollback") if con.in_transaction else None
            raise DbError(f"migration {f.name} failed and was rolled back: {e}") from e
        applied.append(f.name)
    return applied


def has_fts(con) -> bool:
    try:
        con.execute("create virtual table if not exists _fts_probe using fts5(x)")
        con.execute("drop table _fts_probe")
        return True
    except sqlite3.Error as e:
        note_problem(__name__, e)
        return False
