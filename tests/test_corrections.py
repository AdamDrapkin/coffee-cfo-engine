"""When something filed turns out wrong: banners, flags, digest, lint. All data SYNTHETIC."""
import json
import re

from coffeekb import absorb, corrections, digest, lint
from coffeekb.ledger import ledger_dir
from coffeekb.validate import validate


def paste(kb, response_text, updates, prose=None):
    m = re.search(r"```json\n(.*?)\n```", response_text, re.S)
    d = json.loads(m.group(1))
    d["ledger_updates"] = updates
    head = response_text[: m.start()]
    if prose:
        head = head.replace("SYNTHETIC test answer.", prose)
    (kb / "inbox" / "answer-paste.md").write_text(absorb.TEMPLATE + head + "```json\n" + json.dumps(d) + "\n```")
    out = absorb.run_absorb(kb)
    assert out.status == "done", out.message
    return out


def file_wrong_claim(kb, response_text):
    paste(kb, response_text,
          [{"target": "decision", "op": "append", "fields": {"decision": "Store manager choice", "recommendation": "Hire Dana Fox as Store Manager"},
            "evidence": ["shot-1.png"], "confidence": "Moderate"}],
          prose="Recommendation: hire Dana Fox as Store Manager.")
    briefing = sorted((kb / "wiki" / "briefings").glob("*.md"), key=lambda p: p.stem)[0]
    decision = next((ledger_dir(kb) / "decisions").glob("2*.md"))
    return briefing, decision


CORRECTION = [{"target": "correction", "op": "append", "confidence": "High", "evidence": [],
               "fields": {"claim": "hire Dana Fox as Store Manager", "correction": "Dana Fox was unavailable; Kim Lee was hired instead.",
                          "applies_to": "Store manager choice", "reason": "The CEO said so on this date."}}]


def test_correction_banners_briefing_and_leaves_ledger_history_untouched(kb, response_text):
    briefing, decision = file_wrong_claim(kb, response_text)
    before_ledger = decision.read_text()
    original_body = briefing.read_text()
    out = paste(kb, response_text, CORRECTION)
    corr = next((ledger_dir(kb) / "corrections").glob("2*.md"))
    text = briefing.read_text()
    assert "[!warning] Corrected on" in text and f"[[{corr.stem}]]" in text and "Kim Lee was hired" in text
    assert original_body.split("---\n", 2)[2].strip() in text          # the original words are still there
    assert decision.read_text() == before_ledger                           # append-only: not one byte changed
    assert any("warning banner" in i for i in out.info)
    fm, body = corrections.notes(kb)[0][1], corr.read_text()
    assert briefing.stem in fm["affected"] and decision.stem in fm["affected"]
    assert "History, left as filed" in body
    assert lint.run(kb) == []


def test_digest_and_hubs_carry_the_correction(kb, response_text):
    file_wrong_claim(kb, response_text)
    paste(kb, response_text, CORRECTION)
    d = digest.build(kb)
    assert "Corrections in force" in d and "Kim Lee was hired" in d
    assert "[CORRECTED" in d                                               # the old decision is marked wherever listed
    hub = (kb / "wiki" / "hubs" / "hub-corrections.md").read_text()
    assert "Kim Lee was hired" in hub
    assert "(CORRECTED, see [[" in (kb / "wiki" / "hubs" / "hub-decisions.md").read_text()
    assert "(CORRECTED, see [[" in (kb / "wiki" / "hubs" / "hub-briefings.md").read_text()


def test_lint_notices_a_missing_banner(kb, response_text):
    briefing, _ = file_wrong_claim(kb, response_text)
    paste(kb, response_text, CORRECTION)
    briefing.write_text(re.sub(r"\n> \[!warning\].*?\n> This document says.*?\n", "\n", briefing.read_text(), flags=re.S))
    assert any("has no correction banner" in i for i in lint.run(kb))


def test_a_correction_must_say_what_is_true(kb, response_text):
    m = re.search(r"```json\n(.*?)\n```", response_text, re.S)
    d = json.loads(m.group(1))
    d["ledger_updates"] = [{"target": "correction", "op": "append", "confidence": "High", "evidence": [], "fields": {"claim": "x is the manager"}}]
    text = response_text[: m.start()] + "```json\n" + json.dumps(d) + "\n```"
    r = validate(text, vault=kb)
    assert not r.ok and any("without 'correction'" in x for x in r.reasons)


def test_amendment_facts_survive_even_though_the_amend_file_sorts_first(kb, response_text):
    paste(kb, response_text, [{"target": "store", "op": "append", "fields": {"name": "9 Elm St", "city": "Springfield"},
                                 "evidence": ["shot-1.png"], "confidence": "High"}])
    paste(kb, response_text, [{"target": "store", "op": "amend", "reason": "SYNTHETIC",
                                 "fields": {"name": "9 Elm St", "manager": "Kim Lee"}, "evidence": ["shot-1.png"], "confidence": "High"}])
    assert "manager Kim Lee" in digest.build(kb)
    assert "manager: Kim Lee" in (kb / "wiki" / "hubs" / "store-9-elm-st.md").read_text()
