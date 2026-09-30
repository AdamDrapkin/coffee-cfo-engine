"""Session health is per conversation and per in-game week. All data SYNTHETIC."""
import time

from coffeekb import health
from coffeekb.util import now_iso, page_fm, write_page


def shots(kb, n, week="3", start=0):
    for i in range(start, start + n):
        (kb / "raw" / "screenshots" / f"2026-09-30-wk{week}-menu-{i}.png").write_bytes(b"x")


def filings(kb, n):
    for _ in range(n):
        with open(kb / "wiki" / "outputs" / "quota-log.md", "a") as fh:
            fh.write(f"| {now_iso()} | antigravity | absorb | 0 | n/a | ok |\n")


def week_note(kb, wk):
    fm = page_fm(f"Week {wk}", "s", "ledger", ["ledger"], status="final", kind="week", op="append", confidence="High",
                 extracted_by="t", source_screenshot=[], week=wk)
    write_page(kb / "wiki" / "ledger" / "weeks" / f"week-{wk:03d}.md", fm, "x")


def test_fresh_conversation_is_still_good_with_room_left(kb):
    week_note(kb, 3)
    msg = health.start(kb)
    assert "SESSION STARTED for week 3" in msg
    level, text = health.report(kb)
    assert level == "OK" and "Week 3: still good" in text and "room for roughly 100 more screens" in text


def test_load_before_the_marker_does_not_count(kb):
    week_note(kb, 3)
    shots(kb, 120)
    filings(kb, 10)
    time.sleep(1.1)
    health.start(kb)                                   # a new conversation begins after all that work
    level, text = health.report(kb)
    assert level == "OK" and "0 screens, 0 filings" in text


def test_notice_then_new_as_this_conversation_grows(kb):
    week_note(kb, 3)
    health.start(kb)
    time.sleep(0.05)
    shots(kb, 60)
    filings(kb, 5)                                     # 60 + 40 = 100
    assert health.report(kb)[0] == "NOTICE"
    shots(kb, 50, start=60)                            # 150
    level, text = health.report(kb)
    assert level == "NEW" and "START A NEW CONVERSATION NOW" in text and "nothing is lost" in text


def test_new_in_game_week_asks_for_a_new_conversation(kb):
    week_note(kb, 3)
    health.start(kb)
    week_note(kb, 4)
    level, text = health.report(kb)
    assert level == "WEEK" and "week 4 has started" in text and "began in week 3" in text


def test_without_a_marker_it_counts_from_the_start_of_the_week(kb):
    shots(kb, 30, week="5")
    week_note(kb, 5)
    level, text = health.report(kb)
    assert level == "OK" and "Week 5" in text and "30 screens" in text
    shots(kb, 80, week="5", start=30)
    assert health.report(kb)[0] == "NOTICE"


def test_video_frames_count_as_screens(kb):
    week_note(kb, 2)
    health.start(kb)
    time.sleep(0.05)
    d = kb / ".coffee-work" / "frames" / "clip"
    d.mkdir(parents=True)
    (d / "manifest.md").write_text("# Frames\n\n" + "\n".join(f"- frame-{i:03d}-1.0s.png  (t=1.0s)" for i in range(1, 41)) + "\n")
    assert health.measure(kb, 0)["screens"] >= 40
    assert "40 screens" in health.report(kb)[1]
