"""Database tests (Sprints 1 to 7). Each one fails without the feature it protects."""
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from coffeekb import dbhealth, ledger  # noqa: E402
from coffeekb.db import conn, export, load, queries, sync, totals  # noqa: E402
from coffeekb.util import page_fm, write_page  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFEE_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("COFFEE_WORK", str(tmp_path / "work"))
    monkeypatch.setenv("COFFEE_DB_TEST", "1")
    v = tmp_path / "vault"
    v.mkdir()
    ledger.ensure_seed(v)
    for d in ("briefings", "knowledge-base"):
        (v / "wiki" / d).mkdir(parents=True, exist_ok=True)
    queries.reset()
    return v


def _store(v, name, week, **f):
    fm = page_fm("s", "s", "ledger", ["ledger"], status="final")
    fm.update({"kind": "store", "op": "amend", "confidence": "High", "extracted_by": "t", "source_screenshot": [], "name": name, "week": week, **f})
    n = len(list((v / "wiki/ledger/stores").glob("*")))
    write_page(v / "wiki" / "ledger" / "stores" / f"2026-01-01-{name.replace(' ', '-')}-{week}-{n}.md", fm, "x")


def test_migrations_are_idempotent_and_enforce_rules(env):
    con = conn.connect()
    assert "001_init.sql" in conn.migrate(con)
    assert conn.migrate(con) == []                                  # second run applies nothing
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into menu_week values (99, 1, 1, 1, 1, 1, 1, '')")            # foreign key: no such store
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into decision (decision_key, title, status) values ('k', 't', 'maybe')")   # status must be a known value
    assert dbhealth.check() == []


def test_database_refuses_a_synced_folder(monkeypatch, tmp_path):
    with pytest.raises(conn.DbError):
        conn.connect(Path.home() / "Library/Mobile Documents/x/coffee.db")


def test_rebuild_is_all_or_nothing_and_repeatable(env):
    _store(env, "Main St", 8, sales=100, hot_beverage_cups=10, cold_beverage_cups=5, floor_staff_count=6)
    con = conn.connect()
    conn.migrate(con)
    load.rebuild(env, con)
    assert con.execute("select sales, cups_hot, staff_count from store_week").fetchone()[:] == (100.0, 10, 6)
    load.rebuild(env, con)                                          # again: same result, no duplicates
    assert con.execute("select count(*) from store_week").fetchone()[0] == 1
    _store(env, "Main St", 9, sales="not a number")                # a bad value must not corrupt the database
    load.rebuild(env, con)
    assert con.execute("select count(*) from store_week").fetchone()[0] == 2


def test_readers_use_the_database_only_while_it_matches_the_ledger(env):
    _store(env, "Main St", 8, sales=100)
    con = conn.connect()
    conn.migrate(con)
    load.rebuild(env, con)
    queries.reset()
    assert queries.fresh_con(env) is not None
    _store(env, "Main St", 9, sales=200)                            # the ledger moves on
    queries.reset()
    assert queries.fresh_con(env) is None and "behind the ledger" in queries.stale_note()
    assert sync.refresh(env) == "ok"
    queries.reset()
    assert queries.fresh_con(env) is not None


def test_export_and_restore_reproduce_every_total(env, tmp_path):
    _store(env, "Main St", 8, sales=100, net_profit=5, hot_beverage_cups=10, cold_beverage_cups=5, active_blend="Default Blend", blend_price_per_lb=20.5)
    con = conn.connect()
    conn.migrate(con)
    load.rebuild(env, con)
    assert export.export(env, con) > 0
    n = export.restore(env, tmp_path / "restored.db")
    assert n > 0
    other = conn.connect(tmp_path / "restored.db")
    assert totals.diff(totals.normalize(totals.totals(con)), totals.normalize(totals.totals(other))) == []


def test_database_totals_match_the_ledger_totals(env):
    _store(env, "Main St", 8, sales=100, net_profit=5, hot_beverage_cups=10, cold_beverage_cups=5, review_count=12)
    con = conn.connect()
    conn.migrate(con)
    load.rebuild(env, con)
    assert totals.compare(env, con) == []


def test_views_are_per_store_and_compare_only_the_week_before(env):
    con = conn.connect()
    conn.migrate(con)
    con.executescript("""insert into week values (1,null),(2,null),(3,null);
      insert into store (name) values ('A'),('B');
      insert into store_week (store_id, week, sales, net_profit, cups_hot, cups_cold) values (1,1,100,1,5,5),(1,2,150,2,6,6),(1,3,160,3,6,6),(2,1,900,9,5,5),(2,3,950,9,7,7);
      insert into menu_item (name, grp) values ('Iced Coffee','cold'),('Cold Brew','cold');
      insert into menu_week values (1,3,1,3.0,1.1,60,300,''),(1,3,2,3.75,1.4,60,200,''),(2,3,1,3.0,1.1,60,50,''),(2,3,2,3.75,1.4,60,90,'');""")
    a = {r["week"]: r["sales_change"] for r in con.execute("select * from v_vs_last_week where store_id=1")}
    assert a[2] == 50 and a[3] == 10
    b = {r["week"]: r["sales_change"] for r in con.execute("select * from v_vs_last_week where store_id=2")}
    assert b[3] is None                                             # store B has no week 2: no comparison, not a wrong one
    top = {(r["store_id"], r["name"]) for r in con.execute("select * from v_item_rank where rk=1")}
    assert top == {(1, "Iced Coffee"), (2, "Cold Brew")}            # each store has its own best seller
    assert len(con.execute("select * from v_store_compare").fetchall()) == 5


def test_search_finds_reviews_and_screens_ranked(env):
    con = conn.connect()
    conn.migrate(con)
    con.executescript("""insert into store (name) values ('A');
      insert into review (review_key, store_id, week, text, theme) values ('k1',1,7,'What kinds of coffee beans do you use? It tastes horrible.','beans');
      insert into source (file, week, kind, ocr_text) values ('x.png',7,'menu','Iced Coffee SALES LAST WEEK 329');""")
    con.execute("insert into review_fts(rowid, text) select review_id, text from review")
    con.execute("insert into source_fts(rowid, text) select source_id, ocr_text from source")
    hits = queries.search(con, "coffee beans horrible")
    assert hits and hits[0].startswith("review (week 7)")
    assert any("x.png" in h for h in queries.search(con, "sales last week"))


def test_lever_table_flags_actions_that_do_not_exist(env):
    from coffeekb import facts
    con = conn.connect()
    conn.migrate(con)
    load.rebuild(env, con)
    queries.reset()
    assert facts.guard_warnings(env, "Send the floor staff to training this week.")
    assert facts.guard_warnings(env, "Raise the floor staff wage a little.") == []


def test_queries_and_writes_stay_fast_at_scale(tmp_path):
    con = conn.connect(tmp_path / "big.db")
    conn.migrate(con)
    con.execute("begin")
    for w in range(1, 201):
        con.execute("insert into week values (?, null)", (w,))
    for s in range(1, 51):
        con.execute("insert into store (name) values (?)", (f"Store {s}",))
    for i in range(1, 17):
        con.execute("insert into menu_item (name, grp) values (?, 'hot')", (f"Item {i}",))
    t = time.time()
    for s in range(1, 51):
        for w in range(1, 201):
            con.execute("insert into store_week (store_id, week, sales, net_profit, cups_hot, cups_cold) values (?,?,?,?,?,?)", (s, w, 1000 + w, 10, 100, 100))
            for i in range(1, 17):
                con.execute("insert into menu_week values (?,?,?,?,?,?,?,?)", (s, w, i, 3.0, 1.0, 60, 100 + i, ""))
    con.execute("commit")
    load_time = time.time() - t
    for sql in ("select * from v_vs_last_week where store_id=7 and week=150", "select * from v_item_rank where store_id=9 and week=199 and rk<=3",
                "select week, sum(units_sold) from menu_week where store_id=3 group by week", "select * from v_store_compare where week=100"):
        t = time.time()
        con.execute(sql).fetchall()
        assert time.time() - t < 0.5, sql
    t = time.time()
    con.execute("begin")
    for i in range(1, 17):
        con.execute("insert or replace into menu_week values (1,200,?,3.0,1.0,60,999,'')", (i,))
    con.commit()
    assert time.time() - t < 1 and load_time < 60


def test_an_unreachable_database_is_quiet_and_never_blocks_answers(env, monkeypatch):
    """A sandboxed chat may not be able to open the file: answers come from the ledger, one log line, no 'failed' flag."""
    from coffeekb import lookup
    _store(env, "Main St", 8, sales=100)
    con = conn.connect()
    conn.migrate(con)
    load.rebuild(env, con)
    con.close()
    def boom(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(conn, "connect", boom)
    queries.reset()
    for _ in range(3):
        assert "no record" not in lookup.facts(env, "sales").lower()
    assert sync.refresh(env) == "unreachable"
    log = (env / ".coffee-work" / "problems.log")
    assert not log.exists() or log.read_text().count("unable to open") <= 1
