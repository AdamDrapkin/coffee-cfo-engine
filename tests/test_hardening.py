"""Regression tests for the deep-dive fixes: each one fails without the fix."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from coffeekb import analysis, decisions, ledger, lookup, screens  # noqa: E402
from coffeekb.util import page_fm, write_page  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFEE_VAULT", str(tmp_path))
    monkeypatch.setenv("COFFEE_WORK", str(tmp_path / "work"))
    ledger.ensure_seed(tmp_path)
    (tmp_path / "wiki" / "briefings").mkdir(parents=True, exist_ok=True)
    (tmp_path / "wiki" / "hubs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _doc(items):
    lines = [{"t": t, "c": 1.0, "x": x, "y": y, "w": 200, "h": h} for t, x, y, h in items]
    return screens.Doc.from_json({"file": "m.png", "w": 1290, "h": 2796, "lines": lines, "stars": []})


def _store_note(v, name, week, **f):
    fm = page_fm("s", "s", "ledger", ["ledger"], status="final")
    fm.update({"kind": "store", "op": "amend", "confidence": "High", "extracted_by": "t", "source_screenshot": [], "name": name, "week": week, **f})
    write_page(v / "wiki" / "ledger" / "stores" / f"2026-01-01-{name}-{week}-{len(list((v / 'wiki/ledger/stores').glob('*')))}.md", fm, "x")


def _menu_note(v, week, store, items):
    fm = page_fm("m", "m", "ledger", ["ledger"], status="final")
    fm.update({"kind": "menu-week", "op": "append", "confidence": "High", "extracted_by": "t", "source_screenshot": [], "menu_week_id": f"week-{week}", "week": week, "store": store, "items": items})
    d = v / "wiki" / "ledger" / "menu-weeks"
    d.mkdir(parents=True, exist_ok=True)
    write_page(d / f"2026-01-01-week-{week}.md", fm, "x")


ICED = {"name": "Iced Coffee", "group": "cold", "price": "3.00", "unit_cost": "1.12", "margin": "63", "sales": "329", "sales_change": "+12 (+4%)"}
BREW = {"name": "Cold Brew", "group": "cold", "price": "3.75", "unit_cost": "1.46", "margin": "61", "sales": "263", "sales_change": "+9 (+4%)"}


def test_menu_screen_reads_units_sold():
    d = _doc([("Iced Coffee", 495, 1292, 49), ("SALES LAST WEEK", 710, 1556, 33), ("329", 884, 1605, 65), ("+12 (+4%)", 868, 1682, 37),
              ("Unit Cost $1.12", 276, 1711, 24), ("PRICE", 588, 1776, 37), ("$3.00", 746, 1857, 41), ("63%", 341, 1886, 33),
              ("HOT", 247, 784, 41), ("COLD", 604, 780, 41), ("FOOD", 986, 780, 41)])
    p = screens.parse(d)
    r = {x["field"]: x["value"] for x in p.rows}
    assert p.kind == "menu_item" and r["sales_last_week"] == "329" and r["item_group"] == "cold" and r["sales_change"].startswith("+12")


def test_facts_answers_item_and_group_questions_without_images(vault):
    _menu_note(vault, 9, "S", [{**ICED, "sales": "317"}, {**BREW, "sales": "254"}])
    _menu_note(vault, 10, "S", [ICED, BREW])
    out = lookup.facts(vault, "iced coffee")
    assert "| 10 | 329" in out and "1 of 2 cold" in out
    assert "1. Iced Coffee: 329" in lookup.facts(vault, "cold drinks")


def test_top_seller_claim_is_checked(vault):
    _menu_note(vault, 10, "S", [ICED, BREW])
    bad = lookup.claims_warnings(vault, "Raise prices on top-selling cold drinks (Cold Brew).")
    assert bad and "Iced Coffee" in bad[0]
    assert lookup.claims_warnings(vault, "Raise prices on top-selling cold drinks: Iced Coffee and Cold Brew.") == []


def test_decision_status_and_unknowns_can_be_closed(vault):
    up = {"target": "decision", "op": "append", "confidence": "Moderate", "evidence": ["x"],
          "fields": {"decision": "Week 7: Buy the Finest Blend", "options": "o", "recommendation": "r", "ceo_decision": "Pending CEO confirmation"}}
    ledger.write_updates(vault, {"ledger_updates": [up]}, "t", "b", {})
    assert decisions.status_of(decisions.merged(vault)["Week 7: Buy the Finest Blend"]) == "open"
    assert "marked done" in decisions.decide(vault, "Finest Blend", "done", "in use since week 8")
    assert decisions.status_of(decisions.merged(vault)["Week 7: Buy the Finest Blend"]) == "done"
    a = {"target": "assumption", "op": "append", "confidence": "Low", "evidence": ["e"], "fields": {"item": "Cup setting unknown", "assumption": "unknown"}}
    ledger.write_updates(vault, {"ledger_updates": [a, a]}, "t", "b", {})
    assert len(decisions.open_unknowns(vault)) == 1                  # a repeat is not added twice
    assert "Resolved 1" in decisions.resolve(vault, "cup setting", "checked")
    assert decisions.open_unknowns(vault) == []


def test_comparison_is_only_with_the_week_before(vault):
    _store_note(vault, "S", 8, hot_beverage_cups=1928, sales=100)
    _store_note(vault, "S", 10, hot_beverage_cups=1917, sales=110)
    prev, older = analysis.previous_and_older(vault, 10)
    assert "hot_beverage_cups" not in prev and older["hot_beverage_cups"] == (8, 1928.0)
    _store_note(vault, "S", 9, hot_beverage_cups=1900)
    prev, _ = analysis.previous_and_older(vault, 10)
    assert prev["hot_beverage_cups"] == 1900


def test_analysis_is_tagged_with_the_run_week_not_the_first_week_in_the_text(vault):
    from coffeekb import absorb
    (vault / ".coffee-work" / "week").mkdir(parents=True, exist_ok=True)
    (vault / ".coffee-work" / "week" / "current.json").write_text(json.dumps({"week": "10"}))
    (vault / "inbox").mkdir(exist_ok=True)
    body = "\n".join(f"## {h}\nCompared with week 9 this is fine. " + "word " * 40 for h in (
        "The call", "What happened", "What customers are saying", "Why it happened", "Do this first", "Do not do yet", "Weak spots and risks", "Send next"))
    (vault / "inbox" / "analysis-paste.md").write_text(body + "\nConfidence: Low.\n")
    out = absorb.run_analysis(vault)
    assert out.status == "done" and "Week 10" in out.briefing.read_text(encoding="utf-8")
    assert "confidence: Low" in out.briefing.read_text(encoding="utf-8")


def test_game_fact_guard_matches_whole_words_only(vault):
    from coffeekb import facts
    facts.ensure(vault)
    assert facts.guard_warnings(vault, "Invest in staff training.")
    assert facts.guard_warnings(vault, "Cash is constrained, so keep staff steady.") == []


def test_dollar_check_judges_each_figure(vault):
    from coffeekb.validate import _prose_dollar_warnings
    line = "Cash is $1,234. Something else entirely unrelated to timing and padding padding padding padding, profit is $555 (estimate)."
    w = _prose_dollar_warnings(line, set(), None)
    assert len(w) == 1 and "$1,234" in w[0]


def test_review_classifier_needs_the_review_layout():
    d = _doc([("Reviews of staff training", 50, 900, 40), ("Hello boss", 57, 431, 41)])
    assert screens.classify(d) != "review_detail"
    d2 = _doc([("34 reviews", 61, 1125, 33), ("Hello boss", 57, 431, 41)])
    assert screens.classify(d2) == "review_detail"


def test_two_stores_are_logged_separately():
    from coffeekb import week_store
    def mk(store):
        p = screens.Parsed("store_performance")
        p.rows = [{"file": f"{store}.png", "field": "hot_beverage_cups", "value": "100", "unit": "cups", "confidence": "High", "unreadable": False},
                  {"file": f"{store}.png", "field": "store", "value": store, "unit": "", "confidence": "High", "unreadable": False}]
        return p
    rec = {"a.png": mk("1 Main St"), "b.png": mk("2 Oak Ave")}
    week_store._add_store_logging(rec, "10")
    names = {u["fields"]["name"] for x in rec.values() for u in x.updates if u["target"] == "store"}
    assert names == {"1 Main St", "2 Oak Ave"}


def test_failure_audit_names_the_gaps():
    out = "\n".join(analysis.failure_audit({"weekly_results": 1, "income_statement": 2, "customer_reviews": 5, "menu_item": 16}, 24, 2, ["AUDIT FAIL x"], 10))
    assert "store performance" in out and "2 screen(s) are not recognized" in out and "second reader" in out and "disagree" in out


def test_problems_are_recorded_not_swallowed(vault):
    from coffeekb.util import note_problem
    note_problem("test", ValueError("boom"))
    assert "ValueError: boom" in (vault / ".coffee-work" / "problems.log").read_text()


def test_filing_stays_fast_as_the_ledger_grows(vault):
    for i in range(1000):
        fm = page_fm("n", "n", "ledger", ["ledger"], status="final")
        fm.update({"kind": "catalog", "op": "append", "confidence": "High", "extracted_by": "t", "source_screenshot": [], "name": f"Item {i}", "category": "menu", "cost": i})
        write_page(vault / "wiki" / "ledger" / "catalog" / f"2026-01-01-item-{i}.md", fm, "x")
    ups = [{"target": "catalog", "op": "append", "confidence": "High", "evidence": ["x"], "fields": {"category": "menu", "name": f"New {i}", "cost": i}} for i in range(40)]
    t = time.time()
    ledger.write_updates(vault, {"ledger_updates": ups}, "t", "b", {})
    assert time.time() - t < 8


def _png(path):
    from PIL import Image
    Image.new("RGB", (40, 40), (255, 255, 255)).save(path)


def _cache(v, path, items):
    from coffeekb import vision
    lines = [{"t": t, "c": 1.0, "x": x, "y": y, "w": 200, "h": h} for t, x, y, h in items]
    doc = {"file": str(path), "w": 1290, "h": 2796, "lines": lines, "stars": []}
    (vision.cache_dir(v) / f"{vision._key(path)}.json").write_text(json.dumps(doc), encoding="utf-8")


def test_a_whole_week_runs_end_to_end(vault):
    """The real command path on synthetic screens (reading is cached, so no macOS reader is needed)."""
    from coffeekb import week
    inbox = vault / "inbox"
    inbox.mkdir(exist_ok=True)
    for n in ("a.png", "b.png"):
        _png(inbox / n)
    _cache(vault, inbox / "a.png", [("Panda's Coffee", 491, 207, 45), ("117 Mission St, San Francisco", 398, 260, 45), ("WEEKLY RESULTS", 458, 236, 37),
                                     ("WEEKLY REVENUE", 304, 484, 37), ("$1,000", 344, 546, 86), ("WEEKLY NET INCOME", 860, 484, 37), ("$100", 998, 548, 87),
                                     ("Cash from Operations", 191, 768, 37), ("+$120", 953, 768, 45), ("Investing", 186, 840, 43), ("$0", 1043, 837, 41),
                                     ("Financing", 190, 914, 42), ("$0", 1043, 910, 41), ("Net Cash Flow", 191, 1020, 37), ("+$120", 957, 1020, 45),
                                     ("THE CAFE STREET JOURNAL.", 183, 1264, 102), ("Feb 26, 2022", 900, 1369, 37)])
    _cache(vault, inbox / "b.png", [("117 Mission St, San Francisco", 398, 260, 45), ("STORE INCOME STATEMENT", 57, 626, 37), ("Feb 26", 872, 776, 38),
                                     ("Total Revenues", 57, 1069, 37), ("$1,000", 851, 1067, 48), ("Total Expenses", 57, 1760, 37), ("$900", 852, 1760, 45),
                                     ("OPERATING INCOME", 57, 1890, 37), ("$100", 872, 1890, 45), ("NET INCOME", 57, 2251, 37), ("$100", 872, 2251, 45)])
    r = week.run(vault, expect=2, new_session=True)
    assert r["status"] == "done", r["text"][:400]
    assert "WHAT COULD BE WRONG THIS WEEK" in r["text"] and "SCREEN COUNT: only 2 screens" in r["text"]
    assert list((vault / "wiki" / "ledger" / "weeks").glob("week-*.md"))
    assert not list(inbox.glob("*.png"))                      # filed and moved out of the inbox


def test_golden_snapshot_is_deterministic_and_detects_change(vault):
    from coffeekb import golden
    _menu_note(vault, 10, "S", [ICED, BREW])
    assert json.dumps(golden.snapshot(vault), sort_keys=True, default=str) == json.dumps(golden.snapshot(vault), sort_keys=True, default=str)
    golden.save(vault)
    assert golden.check(vault) == []
    _menu_note(vault, 11, "S", [ICED, BREW])
    assert any("menu_week" in d or "menu-weeks" in d for d in golden.check(vault))


def test_database_location_rule_refuses_synced_folders(tmp_path):
    from coffeekb import dbhealth
    assert dbhealth.location_problems(Path.home() / "Library/Mobile Documents/x/coffee.db")
    assert dbhealth.location_problems(tmp_path / "coffee.db") == []
    assert dbhealth.check(tmp_path / "missing.db") == []           # absent file passes until Sprint 1 creates it


def test_database_health_catches_wrong_journal_mode(tmp_path):
    import sqlite3
    from coffeekb import dbhealth
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("create table a(x)")
    con.commit()
    con.close()
    assert "journal mode is not WAL" in dbhealth.check(p)
    con = sqlite3.connect(p)
    con.execute("pragma journal_mode=wal")
    con.close()
    assert dbhealth.check(p) == []


def test_configured_database_path_is_not_synced():
    from coffeekb import codecheck
    assert codecheck.db_location_problems() == []


def test_untagged_income_statement_gets_its_week_tag(vault):
    """A week filed without a week tag must be refiled with one; the same values WITH the tag are not refiled."""
    from coffeekb import week_dedupe
    _store_note(vault, "S", "", sales=100, net_profit=5)            # legacy note: values, no week tag
    p = screens.Parsed("income_statement")
    p.updates = [{"target": "store", "op": "amend", "fields": {"name": "S", "week": "4", "sales": "100", "net_profit": "5"}, "confidence": "High", "evidence": [], "reason": "r"}]
    out, skipped = week_dedupe._dedupe(vault, {"a.png": p}, [])
    assert len(out) == 1 and not skipped["store"]
    _store_note(vault, "S", 4, sales=100, net_profit=5)
    out, skipped = week_dedupe._dedupe(vault, {"a.png": p}, [])
    assert out == [] and skipped["store"] == 1


def test_screenshot_retention_deletes_only_old_archived_images(tmp_path):
    import os, time
    from coffeekb import retention
    shots = tmp_path / "raw" / "screenshots"; text = tmp_path / "raw" / "ocr" / "screens"
    shots.mkdir(parents=True); text.mkdir(parents=True)
    old, fresh, notext = shots / "old.png", shots / "fresh.png", shots / "notext.png"
    for p in (old, fresh, notext):
        p.write_bytes(b"x")
    for n in ("old.png", "fresh.png"):
        (text / (n + ".txt")).write_text("t")
    t = time.time() - 30 * 86400
    os.utime(old, (t, t)); os.utime(notext, (t, t))
    assert retention.purge_screenshots(tmp_path) == 1
    assert not old.exists() and fresh.exists() and notext.exists()


def test_learn_layout_validates_then_teaches_the_engine(tmp_path):
    from coffeekb import learned
    shots = tmp_path / "raw" / "ocr" / "screens"; shots.mkdir(parents=True)
    (tmp_path / "inbox").mkdir(); (tmp_path / "core").mkdir()
    (shots / "S1.PNG.txt").write_text("# S1.PNG  1290x2796  (y x height confidence text)\n"
                                      "  300   100 h 40 1.00  Loyalty Program\n  400   100 h 40 1.00  Members\n  450   110 h 50 1.00  1,240\n")
    paste = tmp_path / "inbox" / "layout-paste.md"
    paste.write_text("LAYOUT | loyalty\nMATCH | Loyalty Program\nSAMPLE | S1.PNG\nFIELD | members | Members | below | number | people | 9,999\n")
    ok, msg = learned.learn(tmp_path)                       # wrong expected value: refused, nothing saved
    assert not ok and "you read 9,999" in msg and not (tmp_path / "core" / "learned-layouts.json").exists()
    paste.write_text("LAYOUT | loyalty\nMATCH | Loyalty Program\nSAMPLE | S1.PNG\nFIELD | members | Members | below | number | people | 1,240\n")
    ok, msg = learned.learn(tmp_path)
    assert ok, msg
    d = learned.doc_from_text(shots / "S1.PNG.txt")
    assert screens.classify(d) == "learned"
    assert {r["field"]: r["value"] for r in screens.parse(d).rows} == {"members": "1,240"}
    learned.RULES.clear()


def test_autofix_escalates_once_and_docs_check_finds_bad_command(tmp_path):
    from coffeekb import autofix
    (tmp_path / "scripts").mkdir(); (tmp_path / ".agents" / "skills" / "coffee-week" / "references").mkdir(parents=True)
    (tmp_path / "scripts" / "coffee.py").write_text('sub.add_parser("week")\n')
    (tmp_path / "AGENTS.md").write_text("run `sh scripts/run.sh week` then `sh scripts/run.sh nonsense`\n")
    assert autofix.docs_mismatches(tmp_path) == ["AGENTS.md names the command 'nonsense', which does not exist"]
    assert autofix.report_issue(tmp_path, "something broke") is True
    assert autofix.report_issue(tmp_path, "something broke") is False          # the same issue is never repeated
    assert len(autofix.open_issues(tmp_path)) == 1


def test_calendar_dates_match_the_game_and_name_the_season():
    from coffeekb import calendar as cal
    assert cal.describe(13).startswith("Apr 2, 2022, spring")
    assert cal.describe(26).startswith("Jul 2, 2022, summer")
    assert cal.describe(49).startswith("Dec 10, 2022, winter")


def test_identical_week_to_week_figures_are_flagged(vault):
    from coffeekb import analysis
    _store_note(vault, "S", 13, cold_beverage_sales=6345, hot_beverage_sales=7300)
    _store_note(vault, "S", 14, cold_beverage_sales=6345, hot_beverage_sales=6588)
    out = "\n".join(analysis.identical_to_last_week(vault, "14"))
    assert "cold beverage sales $6345 is identical" in out and "hot beverage sales" not in out.split("IDENTICAL")[1].split("Say in")[0].replace("cold beverage sales", "")
