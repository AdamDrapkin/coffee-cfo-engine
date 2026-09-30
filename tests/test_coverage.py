from coffeekb import coverage
from coffeekb.util import page_fm, write_page


def shot(kb, name):
    (kb / "raw" / "screenshots" / name).write_bytes(b"x")


def catalog(kb, category, name):
    fm = page_fm(f"catalog {name}", "s", "ledger", ["ledger"], status="final", kind="catalog", op="append",
                 confidence="High", extracted_by="test", source_screenshot=[], category=category, name=name)
    write_page(kb / "wiki" / "ledger" / "catalog" / f"2026-09-30-{category}-{name}.md", fm, "x")


def test_archived_build_screens_without_records_are_a_gap(kb):
    for i in range(1, 5):
        shot(kb, f"2026-09-29-wkx-store-layout-equipment-{i}.png")
    g = coverage.gaps(kb)
    assert any("4 build-store screens" in x and "only 0" in x for x in g)
    for i in range(3):
        catalog(kb, "exterior", f"opt{i}")
    assert not any("build-store" in x for x in coverage.gaps(kb))


def test_menu_staff_and_marketing_gaps_close_when_catalogued(kb):
    for t in ("menu-pricing-product-quality", "employees-payroll-scheduling", "marketing-advertising-brand-awareness"):
        shot(kb, f"2026-09-30-wk3-{t}-1.png")
    text = " ".join(coverage.gaps(kb))
    assert "menu and pricing" in text and "staff and payroll" in text and "marketing" in text
    catalog(kb, "menu", "latte")
    catalog(kb, "staff", "daniel")
    catalog(kb, "marketing", "wifi")
    assert coverage.gaps(kb) == []


def test_week_screen_without_record_or_cash_flow_fields_is_a_gap(kb):
    shot(kb, "2026-09-30-wk2-income-statement-1.png")
    assert any("no week 2 record" in x for x in coverage.gaps(kb))
    week = page_fm("Week 2", "s", "ledger", ["ledger"], status="final", kind="week", op="append", confidence="High",
                   extracted_by="test", source_screenshot=[], week=2, net_income=-1432)
    write_page(kb / "wiki" / "ledger" / "weeks" / "week-002.md", week, "x")
    assert any("lacks operating_cash_flow" in x for x in coverage.gaps(kb))
    amend = page_fm("Week 2 amendment", "s", "ledger", ["ledger"], status="final", kind="week", op="amend", confidence="High",
                    extracted_by="test", source_screenshot=[], week=2, reason="r", amends="week-002",
                    operating_cash_flow=-929, investing_cash_flow=0, financing_cash_flow=0)
    write_page(kb / "wiki" / "ledger" / "weeks" / "week-002-amend.md", amend, "x")
    assert coverage.gaps(kb) == []
