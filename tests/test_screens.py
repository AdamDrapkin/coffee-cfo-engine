"""Parsers run on SYNTHETIC OCR output (invented numbers), so no real screenshots are needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from coffeekb import screens  # noqa: E402


def doc(name, items):
    lines = [{"t": t, "c": 1.0, "x": x, "y": y, "w": 200, "h": h} for t, x, y, h in items]
    return screens.Doc.from_json({"file": name, "w": 1290, "h": 2796, "lines": lines, "stars": []})


def income():
    rows = [("Test Cafe", 491, 207, 45), ("11 Test St, Testville", 398, 260, 45), ("STORE INCOME STATEMENT", 57, 723, 41),
            ("Jan 22", 872, 876, 35), ("Total Revenues", 57, 1170, 29), ("$1,000", 872, 1169, 43),
            ("Total Expenses", 57, 1861, 37), ("$1,400", 872, 1857, 45),
            ("OPERATING INCOME", 57, 1991, 37), ("-$400", 856, 1991, 46),
            ("NET INCOME", 57, 2349, 41), ("-$400", 855, 2347, 53)]
    return doc("a.png", rows)


def test_income_statement_files_store_amend():
    p = screens.parse(income(), "9")
    assert p.kind == "income_statement"
    assert p.updates and p.updates[0]["target"] == "store"
    f = p.updates[0]["fields"]
    assert f["name"] == "11 Test St" and f["sales"] == "1000" and f["net_profit"] == "-400"
    assert not p.flags


def test_income_statement_math_mismatch_is_flagged():
    d = income()
    next(l for l in d.lines if l.t == "$1,400").t = "$1,700"
    p = screens.parse(d, "9")
    assert any("operating income reads" in f for f in p.flags)


def test_reviews_and_unknown():
    d = doc("r.png", [("CUSTOMER REVIEWS", 57, 1325, 41), ("3.0", 57, 1471, 73), ("Price", 823, 1467, 28), ("2.0", 1168, 1463, 37),
                      ("10 reviews", 57, 1642, 28)])
    p = screens.parse(d)
    assert p.kind == "customer_reviews" and {r["field"] for r in p.rows} >= {"review_overall", "review_price", "review_count"}
    o = screens.parse(doc("o.png", [("Something new", 100, 900, 40)]))
    assert o.kind == "other" and o.flags


def test_blend_word_alone_is_not_a_blend_screen():
    d = doc("b.png", [("COMPANY BLEND", 57, 1748, 37), ("HOT BEVERAGE", 349, 723, 37), ("COLD BEVERAGE", 937, 723, 37),
                      ("7 cups", 410, 788, 69)])
    assert screens.classify(d) == "store_performance"


def test_upkeep_queue_and_done(tmp_path):
    from coffeekb import upkeep
    ref = tmp_path / upkeep.SKILL / "references"
    ref.mkdir(parents=True)
    (ref / "parser-gaps.md").write_text("| 2026-01-01 | NEW LAYOUT | a.png | 2 |\n")
    (ref / "run-log.md").write_text("".join(f"| 2026-01-0{i} 10:00 | 30 | 30 | 0 | 0 | 90 |\n" for i in range(1, 5)))
    q = upkeep.items(tmp_path)
    assert any("NEW LAYOUT" in i for i in q) and any("Speed regression" in i for i in q)
    upkeep.done(tmp_path, "checked")
    assert not any("engine code changed" in i for i in upkeep.items(tmp_path))


def test_engine_briefing_is_detailed(tmp_path):
    from coffeekb import briefing
    rows = [{"file": "a", "field": k, "value": val, "unit": "", "confidence": "High", "unreadable": False}
            for k, val in (("sales", "$1,000"), ("payroll", "400"), ("rent", "100"), ("cogs", "200"), ("coffee_beans", "50"),
                           ("net_profit", "-$50"), ("hot_beverage_cups", "300"), ("cold_beverage_cups", "100"), ("review_price", "2.0"),
                           ("review_service", "3.5"), ("review_overall", "3.0"), ("headline", "A opened business in B"))]
    text = briefing.build(tmp_path, {}, rows, [], {}, [], [], "20260101-000000", "3")
    for need in ("**Recommendation:**", "**Confidence:**", "## Next Upload Request", "Cups sold", "Customer ratings", "Newspaper", "Where"[:0]):
        assert need in text
    assert len(text.split()) > 150


def test_thin_analysis_refused(tmp_path):
    import os
    from coffeekb import absorb
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "analysis-paste.md").write_text("The call: hold.\n")
    os.environ["COFFEE_WORK"] = str(tmp_path / "work")
    out = absorb.run_analysis(tmp_path)
    assert out.status == "failed" and "only" in out.message


def test_menu_change_detected_from_legacy_notes():
    from coffeekb import week
    prior = {"price": "2.50", "unit_cost": "0.65", "margin": "74"}
    d = week._menu_diffs(prior, {"price": "$2.50", "unit_cost": "$1.11", "margin": "56%"})
    assert len(d) == 2 and "unit cost" in d[0] and "margin" in d[1]
    assert week._menu_diffs(prior, {"price": "$2.50", "unit_cost": "$0.65", "margin": "74%"}) == []


def test_analysis_becomes_records():
    from coffeekb import absorb
    text = "## The call\nHold steady.\n## Do this first\nCheck the cup setting.\n## Runner-up\nKeep cups.\n## Do not do yet\nNo loans.\n## Weak spots and risks\nLow morale.\n## What I could not read or verify\nThe cash balance was not shown.\n"
    ups = absorb.analysis_records(text, "6", "Moderate", ["x"])
    assert [u["target"] for u in ups] == ["decision", "assumption"]
    assert ups[0]["fields"]["decision"].startswith("Week 6")


def test_amend_order_is_natural():
    from pathlib import Path
    from coffeekb import digest
    items = [(Path(n), {"date_created": "2026-01-01", "op": "amend" if "amend" in n else "append"}) for n in
             ("x-amend-10.md", "x-amend.md", "x-amend-2.md", "x.md")]
    assert [p.name for p, _ in digest.chron(items)] == ["x.md", "x-amend.md", "x-amend-2.md", "x-amend-10.md"]


def test_bill_headline_does_not_swallow_neighbouring_text():
    d = doc("n.png", [("Cash from Operations", 100, 800, 30), ("Investing Financing Net Cash Flow", 100, 900, 30),
                      ("Top Retail Business", 100, 1400, 30), ("City Tax Bill Proposed", 100, 1990, 40)])
    ev = [e[0] for e in screens._newsletter_events(d)]
    assert ev == ["City Tax bill proposed"]


def test_menu_diff_text_has_single_percent_sign():
    from coffeekb import week
    d = week._menu_diffs({"price": "2.50", "unit_cost": "1.11", "margin": "56"}, {"price": "$2.50", "unit_cost": "$1.60", "margin": "40%"})
    assert len(d) == 2 and all("%%" not in x for x in d) and "was 56% " in d[1]
    assert week._menu_diffs({"price": "2.50", "unit_cost": "1.11", "margin": "56"}, {"price": "$2.50", "unit_cost": "$1.07", "margin": "57%"}) == []


def test_review_comments_are_captured():
    d = doc("r.png", [("34 reviews", 61, 1125, 33), ("What kinds of coffee beans do", 722, 1548, 29), ("you use? It tastes horrible.", 718, 1585, 28),
                      ("Staff is very rude! I'Il never", 65, 1548, 33), ("come back again.", 65, 1585, 28), ("STORE MANAGER", 57, 2162, 37)])
    assert screens.review_comments(d) == ["Staff is very rude! I'll never come back again.", "What kinds of coffee beans do you use? It tastes horrible."]


def test_headline_subjects_drop_navigation_words_and_city_stops_at_next_name():
    d = doc("n.png", [("Top Retail Business Market Politics Sports", 100, 1475, 30),
                      ("Politics Sports Jane's Coffee Opened Business in Rome Jane's Coffee has opened a shop.", 100, 1990, 40)])
    ev = [e[0] for e in screens._newsletter_events(d)]
    assert ev == ["Jane's Coffee opened business in Rome"]
    own = doc("o.png", [("Panda's Coffee Opened Business in San Francisco", 100, 1990, 40)])
    assert screens._newsletter_events(own) == []


def test_store_blend_reads_supplier_blend_name_on_two_lines():
    d = doc("b.png", [("COMPANY BLEND", 57, 1743, 37), ("Pacific Coffee", 268, 1808, 53), ("Finest Blend", 268, 1882, 28),
                      ("Aroma", 320, 2052, 25), ("PRICE", 1124, 2093, 37), ("$33.98", 981, 2156, 82), ("per lb", 1144, 2239, 29)])
    for l in d.lines:
        l.h = {"Pacific Coffee": 53, "Finest Blend": 28, "$33.98": 82}.get(l.t, l.h)
    p = screens.parse_store_blend(d)
    vals = {r["field"]: r["value"] for r in p.rows}
    assert vals["active_blend"] == "Pacific Coffee Finest Blend" and vals["blend_price_per_lb"] == "$33.98"


def test_changes_detects_a_blend_switch(tmp_path):
    from coffeekb import analysis, digest
    from coffeekb.util import write_page
    d = tmp_path / "wiki" / "ledger" / "stores"
    d.mkdir(parents=True)
    for i, (wk, blend) in enumerate((("7", "Default Blend"), ("8", "Pacific Coffee Finest Blend"))):
        write_page(d / f"2026-09-30-s-amend-{i}.md", {"title": "t", "date_created": "2026-09-30", "kind": "store", "op": "amend", "name": "S", "week": wk, "active_blend": blend}, "x")
    ch = analysis.changes(tmp_path, "8")
    assert any("CHANGED: Default Blend in week 7, Pacific Coffee Finest Blend in week 8" in x for x in ch)


def test_worker_request_roundtrip_without_a_worker_times_out_cleanly(tmp_path):
    from pathlib import Path
    from coffeekb import vision
    got = vision.request_worker_read(tmp_path, [Path("/nonexistent/x.png")], timeout=1.2)
    assert got == {} and list((tmp_path / ".coffee-work" / "ocr-requests").glob("*.json"))


def test_review_file_needs_lines(tmp_path):
    import os
    from coffeekb import absorb
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "review-paste.md").write_text("# nothing here\n")
    os.environ["COFFEE_WORK"] = str(tmp_path / "work")
    assert absorb.run_review_file(tmp_path).status in ("nothing", "failed")


def test_not_available_guard_and_learned_facts(tmp_path):
    from coffeekb import facts
    facts.ensure(tmp_path)
    assert facts.guard_warnings(tmp_path, "Invest in staff training to raise skill.")
    assert not facts.guard_warnings(tmp_path, "Raise the hourly wage a little.")
    facts.append(tmp_path, "NOT AVAILABLE", "loan, cafe", "no cafe loans", "test")
    assert facts.guard_warnings(tmp_path, "take a cafe loan")
    assert facts.parse_learned("- NOT AVAILABLE | a, b | text\n- random line") == [("NOT AVAILABLE", "a, b", "text")]


def test_find_searches_saved_text(tmp_path):
    from coffeekb import search
    d = tmp_path / "raw" / "ocr" / "screens"
    d.mkdir(parents=True)
    (d / "x.png.txt").write_text("  100  50 h30 1.00  Floor Staff hourly salary $14.00\n")
    (tmp_path / "wiki" / "briefings").mkdir(parents=True)
    (tmp_path / "wiki" / "briefings" / "b.md").write_text("Hold prices.\n")
    hits = search.find(tmp_path, "hourly salary")
    assert hits and "x.png.txt:1" in hits[0]
    assert search.find(tmp_path, "nonexistent thing") == []


def test_code_health_hard_rules():
    """Vibe Persona execution discipline: no silent broad excepts, every subprocess call has a timeout."""
    from coffeekb import codecheck
    assert codecheck.silent_handlers() == []
    assert codecheck.calls_without_timeout() == []
    assert codecheck.import_cycles() == []


def test_campaign_board_reads_on_switches_and_prices():
    from coffeekb import screens
    from coffeekb.screens_core import Doc
    def L(t, x, y, h=40): return {"t": t, "c": 1.0, "x": x, "y": y, "w": 100, "h": h}
    lines = [L("MARKETING CAMPAIGNS", 57, 423), L("Free WIFI", 239, 929, 44), L("Desk Power Strip", 775, 931, 45), L("$300", 410, 991, 53),
             L("Faster Speed", 130, 1004, 33), L("On", 738, 1004, 33), L("$90", 1055, 996, 49), L("per week", 414, 1057, 28), L("per week", 1025, 1056, 30),
             L("Free Music", 227, 1563, 45), L("Buy 1 Get 1 Free", 791, 1589, 45), L("Off", 126, 1662, 33), L("Off", 738, 1662, 33),
             L("per unit cost", 361, 2377, 29), L("per week", 1026, 2376, 31)]
    d = Doc.from_json({"file": "x.PNG", "w": 1290, "h": 2796, "lines": lines})
    assert screens.classify(d) == "store_marketing"
    got = {r["field"]: r["value"] for r in screens.PARSERS["store_marketing"](d).rows}
    assert got == {"active_campaign_free_wifi": "$300", "campaign_option_free_wifi": "Faster Speed", "active_campaign_desk_power_strip": "$90"}


def test_blend_name_ignores_logo_word_and_flat_sales_change_is_read():
    from coffeekb import screens
    from coffeekb.screens_core import Doc
    def L(t, x, y, h=40): return {"t": t, "c": 1.0, "x": x, "y": y, "w": 100, "h": h}
    lines = [L("COMPANY BLEND", 57, 1439), L("Pacific Coffee", 268, 1605, 53), L("PACIFIC", 98, 1622, 49), L("Finest Blend", 268, 1678, 29),
             L("Aroma", 320, 1849, 26), L("$33.12", 998, 1954, 74), L("per lb", 1100, 1990, 30)]
    p = screens.parse_store_blend(Doc.from_json({"file": "b.PNG", "w": 1290, "h": 2796, "lines": lines}))
    assert {r["field"]: r["value"] for r in p.rows}["active_blend"] == "Pacific Coffee Finest Blend"
    import re
    assert re.match(r"[+-]?[\d,]+ \(", "0 (0%)")


def _doc(lines):
    from coffeekb.screens_core import Doc
    return Doc.from_json({"file": "x.PNG", "w": 1290, "h": 2796, "lines": [{"t": t, "c": 1.0, "x": x, "y": y, "w": 100, "h": h} for t, x, y, h in lines]})


def test_agency_and_company_board_screens_are_parsed():
    from coffeekb import screens
    a = _doc([("Liberty Marketing", 467, 211, 45), ("MARKETING AGENCY", 467, 260, 37), ("TV Ads", 438, 1507, 59), ("6.5% of Marketing Spend", 260, 1959, 49)])
    assert screens.classify(a) == "agency_contract"
    up = screens.parse(a).updates[0]["fields"]
    assert up["name"] == "Liberty Marketing - TV Ads" and up["cost"] == "6.5"
    c = _doc([("COMPANIES", 515, 211, 41), ("Jane's Coffee", 507, 410, 65), ("Berlin", 759, 1357, 28), ("2", 775, 1406, 57), ("Rome", 759, 1723, 24), ("1", 779, 1772, 53),
              ("QUARTERLY REVENUE", 243, 2512, 33), ("NET INCOME", 1010, 2507, 37), ("$197,922", 292, 2575, 93), ("-$12,396", 913, 2572, 85)])
    assert screens.classify(c) == "company_board"
    f = screens.parse(c).updates[0]["fields"]
    assert f["known_stores"] == 3 and f["stores_by_city"] == "Berlin 2, Rome 1" and f["quarterly_net_income"] == "-12396"
