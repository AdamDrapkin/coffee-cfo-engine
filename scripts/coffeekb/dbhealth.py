"""Database health rules (Sprint 0 of the SQLite plan; the database itself arrives in Sprint 1).

Hard rules: the file lives outside iCloud and other synced folders (a sync client rewriting a live SQLite file can corrupt it),
it is opened in WAL mode with foreign keys on, and it passes SQLite's integrity check. When the file does not exist yet,
the location rule still applies and the rest passes trivially.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .gemini_client import work_root

SYNCED_MARKERS = ("Mobile Documents", "CloudDocs", "iCloud", "Dropbox", "OneDrive", "Google Drive")


def db_path() -> Path:
    return work_root() / "coffee.db"


def location_problems(path: Path) -> list:
    s = str(Path(path).expanduser().resolve())
    return [f"the database path is inside a synced folder ({m}): {s}" for m in SYNCED_MARKERS if m in s]


def check(path: Path | None = None) -> list:
    """Empty list when healthy."""
    path = Path(path) if path else db_path()
    problems = location_problems(path)
    if not path.exists():
        return problems
    try:
        con = sqlite3.connect(str(path), timeout=10)
        try:
            if con.execute("pragma integrity_check").fetchone()[0] != "ok":
                problems.append("SQLite integrity check failed")
            if con.execute("pragma journal_mode").fetchone()[0].lower() != "wal":
                problems.append("journal mode is not WAL")
            if con.execute("pragma foreign_key_check").fetchall():
                problems.append("foreign key violations found")
        finally:
            con.close()
    except sqlite3.Error as e:
        problems.append(f"cannot open the database: {e}")
    return problems
