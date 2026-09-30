import json
import re

from coffeekb.validate import validate


def mutate(text, fn):
    m = re.search(r"```json\n(.*?)\n```", text, re.S)
    data = json.loads(m.group(1))
    fn(data)
    return text[: m.start()] + "```json\n" + json.dumps(data) + "\n```"


def test_good_answer_passes(kb, response_text):
    r = validate(response_text, note_text="", vault=kb, known_files=["shot-1.png", "note-1.md"])
    assert r.ok, r.reasons


def test_invented_number_rejected(kb, response_text):
    bad = mutate(response_text, lambda d: d["ledger_updates"][0]["fields"].update(net_income="$99,999"))
    r = validate(bad, vault=kb)
    assert not r.ok
    assert any("99,999" in x and "not in extraction" in x for x in r.reasons)


def test_number_from_typed_note_is_allowed(kb, response_text):
    ok = mutate(response_text, lambda d: d["ledger_updates"][0]["fields"].update(rent="$4,200"))
    assert not validate(ok, vault=kb).ok
    assert validate(ok, note_text="rent is $4,200 a week", vault=kb).ok


def test_derived_fields_exempt(kb, response_text):
    ok = mutate(response_text, lambda d: d["ledger_updates"][0]["fields"].update(derived_margin="12.5"))
    assert validate(ok, vault=kb).ok


def test_missing_confidence_rejected(kb, response_text):
    bad = mutate(response_text, lambda d: d["ledger_updates"][0].pop("confidence"))
    assert any("confidence" in x for x in validate(bad, vault=kb).reasons)


def test_amend_needs_reason(kb, response_text):
    bad = mutate(response_text, lambda d: d["ledger_updates"][0].update(op="amend"))
    assert any("amend" in x for x in validate(bad, vault=kb).reasons)


def test_append_cannot_overwrite_week(kb, response_text):
    from coffeekb import ledger
    r = validate(response_text, vault=kb)
    ledger.write_updates(kb, r.data, "test", "b", {})
    again = validate(response_text, vault=kb)
    assert not again.ok and any("overwrite existing week 7" in x for x in again.reasons)


def test_bad_json_rejected(kb):
    r = validate("# x\n```json\n{not json}\n```", vault=kb)
    assert not r.ok and "parse" in r.reasons[0]


def test_briefing_needs_parts(kb, response_text):
    bad = response_text.replace("Next Upload Request", "Later").replace("**Recommendation:**", "**Rec:**")
    r = validate(bad, vault=kb)
    assert any("Recommendation" in x for x in r.reasons) and any("Next Upload" in x for x in r.reasons)


def test_mobile_summary_too_long(kb, response_text):
    bad = mutate(response_text, lambda d: d["mobile_summary"].update(do_now=["x"] * 12))
    assert any("mobile_summary" in x for x in validate(bad, vault=kb).reasons)


def test_mobile_summary_required(kb, response_text):
    bad = mutate(response_text, lambda d: d.pop("mobile_summary"))
    assert not validate(bad, vault=kb).ok


def test_unlabeled_prose_dollar_figures_warn(kb, response_text):
    bad = response_text.replace("SYNTHETIC test answer.", "Expect to spend about $150,000 on the lease.")
    r = validate(bad, vault=kb)
    assert r.ok and any("$150,000" in w for w in r.warnings)
    labeled = response_text.replace("SYNTHETIC test answer.", "My estimate is $150,000 for the lease.")
    assert validate(labeled, vault=kb).warnings == []
    known = response_text.replace("SYNTHETIC test answer.", "You start with $800,000 and $48,210 revenue.")
    assert validate(known, vault=kb).warnings == []


def test_ceo_message_numbers_must_be_in_ceo_words(kb, response_text):
    good = mutate(response_text, lambda d: (d.update(ceo_words="I start with $800,000"),
                                            d["extraction"].append({"file": "ceo-message", "field": "starting_cash", "value": "$800,000", "unit": "USD", "confidence": "High", "unreadable": False})))
    assert validate(good, vault=kb).ok
    bad = mutate(response_text, lambda d: (d.update(ceo_words="I start with $800,000"),
                                           d["extraction"].append({"file": "ceo-message", "field": "revenue", "value": "$5,000", "unit": "USD", "confidence": "High", "unreadable": False})))
    r = validate(bad, vault=kb)
    assert not r.ok and any("ceo_words" in x for x in r.reasons)


def test_high_confidence_needs_screenshot_evidence(kb, response_text):
    bad = mutate(response_text, lambda d: (d.update(extraction=[], ledger_updates=[]), d["mobile_summary"].update(confidence="High")))
    r = validate(bad, vault=kb)
    assert not r.ok and any("Confidence High" in x for x in r.reasons)
    ok = mutate(response_text, lambda d: (d.update(extraction=[], ledger_updates=[]), d["mobile_summary"].update(confidence="Low")))
    ok = ok.replace("**Confidence:** Moderate", "**Confidence:** Low")
    assert validate(ok, vault=kb).ok


def test_arithmetic_on_seen_numbers_is_not_a_warning_and_more_is_not_millions(kb, response_text):
    # extraction has 123456 and 48210; their difference is 75246, their sum is 171666
    text = response_text.replace("SYNTHETIC test answer.", "You keep $75,246 more cash than revenue, and $171,666 combined; that is $5,050 more.")
    r = validate(text, vault=kb)
    assert not any(w.startswith(("$75,246", "$171,666")) for w in r.warnings)
    assert any(w.startswith("$5,050 in:") for w in r.warnings)          # parsed as $5,050, never as 5,050 million


def test_high_confidence_resting_on_unknowns_is_warned(kb, response_text):
    shaky = response_text.replace("SYNTHETIC test answer.", "Community heuristic, an estimate, and an unknown mechanic all apply here, plus one inference.")
    shaky = shaky.replace("**Confidence:** Moderate", "**Confidence:** High")
    shaky = mutate(shaky, lambda d: d["mobile_summary"].update(confidence="High"))
    r = validate(shaky, vault=kb)
    assert r.ok and any(w.startswith("Confidence is High") for w in r.warnings)
    calm = validate(response_text, vault=kb)
    assert not any(w.startswith("Confidence is High") for w in calm.warnings)
