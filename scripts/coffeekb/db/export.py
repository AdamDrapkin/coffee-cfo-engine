"""Text export and verified restore: the database file is never the backup; these text files are (they go to git)."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .conn import connect, migrate

EXPORT_DIR = "wiki/db-export"
SKIP = {"schema_migration", "source", "document", "reading"}    # large or re-derivable text; the raw/ocr files and briefings hold them


def tables(con) -> list:
    return [r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '%\\_fts%' escape '\\' order by name")]


def export(v: Path, con=None) -> int:
    own = con is None
    con = con or connect()
    d = v / EXPORT_DIR
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    try:
        for t in tables(con):
            if t in SKIP or t.startswith("review_fts") or t.startswith("document_fts") or t.startswith("source_fts"):
                continue
            cols = [r[1] for r in con.execute(f"pragma table_info({t})")]
            rows = con.execute(f"select * from {t} order by 1, 2" if len(cols) > 1 else f"select * from {t} order by 1").fetchall()
            with open(d / f"{t}.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                w.writerows([["" if x is None else x for x in r] for r in rows])
            n += len(rows)
    finally:
        if own:
            con.close()
    return n


def restore(v: Path, target: Path) -> int:
    """Rebuild an empty database from the CSV export (used by `db verify`)."""
    con = connect(target)
    migrate(con)
    con.execute("pragma foreign_keys=off")
    n = 0
    for f in sorted((v / EXPORT_DIR).glob("*.csv")):
        t = f.stem
        with open(f, newline="", encoding="utf-8") as fh:
            rd = csv.reader(fh)
            cols = next(rd)
            for row in rd:
                con.execute(f"insert into {t} ({','.join(cols)}) values ({','.join('?' * len(cols))})", [None if x == "" else x for x in row])
                n += 1
    con.commit()
    bad = con.execute("pragma foreign_key_check").fetchall()
    con.close()
    if bad:
        raise sqlite3.IntegrityError(f"{len(bad)} foreign key violations after restore")
    return n
