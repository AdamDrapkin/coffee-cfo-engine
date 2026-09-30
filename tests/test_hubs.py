"""Every page reachable, every new record linked. All data SYNTHETIC."""
import json
import re

from coffeekb import absorb, hubs, lint
from coffeekb.ledger import ledger_dir


def paste(kb, response_text, updates, extra_rows=()):
    m = re.search(r"```json\n(.*?)\n```", response_text, re.S)
    d = json.loads(m.group(1))
    d["ledger_updates"] = updates
    d["extraction"] = list(d["extraction"]) + list(extra_rows)
    (kb / "inbox" / "answer-paste.md").write_text(absorb.TEMPLATE + response_text[: m.start()] + "```json\n" + json.dumps(d) + "\n```")
    out = absorb.run_absorb(kb)
    assert out.status == "done", out.message
    return out


def row(field, value):
    return {"file": "shot-1.png", "field": field, "value": value, "unit": "", "confidence": "High", "unreadable": False}


def test_every_page_is_reachable_from_the_map_after_a_filing(kb, response_text):
    paste(kb, response_text, [{"target": "week", "op": "append", "fields": {"week": "7", "revenue": "$48,210"},
                                 "evidence": ["shot-1.png"], "confidence": "High"}])
    reach, files = hubs.reachable_from_map(kb)
    missing = [str(p.relative_to(kb)) for p in files if p not in reach]
    assert missing == []
    assert lint.run(kb) == []


def test_new_record_links_its_hub_and_the_things_it_mentions(kb, response_text):
    paste(kb, response_text, [{"target": "store", "op": "append", "fields": {"name": "12 Oak St", "city": "Springfield"},
                                 "evidence": ["shot-1.png"], "confidence": "High"}])
    paste(kb, response_text, [{"target": "decision", "op": "append",
                                 "fields": {"decision": "Staff the 12 Oak Street store", "recommendation": "hire"},
                                 "evidence": ["shot-1.png"], "confidence": "Moderate"}])
    note = next((ledger_dir(kb) / "decisions").glob("2*.md")).read_text()
    assert "- Part of: [[hub-decisions]]" in note
    assert "[[store-12-oak-st]]" in note            # "12 Oak Street" matched the store "12 Oak St"
    dossier = (kb / "wiki" / "hubs" / "store-12-oak-st.md").read_text()
    assert "Staff the 12 Oak Street store" in dossier or "decisions" in dossier.lower()
    assert "[[" in dossier.split("## Decisions mentioning it")[1]


def test_amendment_links_back_to_what_it_amends(kb, response_text):
    paste(kb, response_text, [{"target": "week", "op": "append", "fields": {"week": "7", "revenue": "$48,210"},
                                 "evidence": ["shot-1.png"], "confidence": "High"}])
    paste(kb, response_text, [{"target": "week", "op": "amend", "reason": "SYNTHETIC correction",
                                 "fields": {"week": "7", "debt": "$0"}, "evidence": ["shot-1.png"], "confidence": "High"}])
    amend = (ledger_dir(kb) / "weeks" / "week-007-amend.md").read_text()
    assert "- Amends: [[week-007]]" in amend
    assert "week-007-amend" in (kb / "wiki" / "hubs" / "hub-weeks.md").read_text()


def test_briefings_chain_to_the_previous_one(kb, response_text):
    paste(kb, response_text, [])
    paste(kb, response_text, [])
    first, second = sorted((kb / "wiki" / "briefings").glob("*.md"), key=lambda x: x.stem)[:2]
    assert f"Previous briefing: [[{first.stem}]]" in second.read_text()


def test_lint_flags_an_unreachable_and_an_isolated_page(kb):
    from coffeekb.util import page_fm, write_page
    fm = page_fm("Lonely", "s", "knowledge", ["x"])
    write_page(kb / "wiki" / "knowledge-base" / "lonely.md", fm, "no links here")
    issues = "\n".join(lint.run(kb))
    assert "lonely.md: not reachable from the vault map" in issues
    assert "lonely.md: isolated" in issues
    from coffeekb import index
    index.rebuild(kb)                                    # hubs pick it up
    assert not any("lonely.md" in i for i in lint.run(kb))


def test_ambiguous_catalog_names_are_not_used_for_mentions(kb, response_text):
    ups = [{"target": "catalog", "op": "append", "fields": {"category": c, "name": "Diner", "cost": "$100"},
            "evidence": ["shot-1.png"], "confidence": "High"} for c in ("exterior", "interior")]
    paste(kb, response_text, ups, extra_rows=[row("diner_cost", "$100")])
    reg = hubs.Registry(kb)
    assert reg.mentions("we picked the Diner look") == []       # same name in two categories: no guess
