"""Phone-formatted HOME.md and STATUS.md.

HOME.md is the one note Adam opens. First screen: the latest mobile summary.
Rules: short lines, bullets, no table wider than three columns, key numbers
in bold. STATUS.md first line tells him in one glance whether the Mac has seen
his screenshots. It uses a clock time, not "2 min ago", because a static file
cannot count minutes and a stale relative time would be misleading.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

from .util import note_problem, atomic_write, now_iso, page_fm, dump_frontmatter, today

LATEST = "wiki/outputs/latest.json"
STATE = "wiki/outputs/status-state.json"
MAX_LINE = 72


def _wrap(s: str, width=MAX_LINE):
    """Break a long bullet at word boundaries so it never scrolls sideways on a phone."""
    s = " ".join(str(s).split())
    if len(s) <= width:
        return [s]
    out, cur = [], ""
    for w in s.split(" "):
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    out.append(cur)
    return out


def _bullets(items, indent="- "):
    lines = []
    for it in items:
        parts = _wrap(it, MAX_LINE - len(indent))
        lines.append(indent + parts[0])
        lines += ["  " + p for p in parts[1:]]
    return lines


def save_latest(v: Path, summary: dict, briefing_link: str, confidence_note: str = ""):
    data = {"when": now_iso(), "summary": summary, "briefing": briefing_link}
    atomic_write(v / LATEST, json.dumps(data, indent=1))


def load_latest(v: Path):
    p = v / LATEST
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as _e:
            note_problem(__name__, _e)
            return None
    return None


def load_state(v: Path) -> dict:
    p = v / STATE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as _e:
            note_problem(__name__, _e)
            pass
    return {}


def save_state(v: Path, **kw):
    st = load_state(v)
    st.update(kw)
    atomic_write(v / STATE, json.dumps(st, indent=1))


def fmt(val):
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return f"{val:,}"
    if isinstance(val, float):
        return f"{val:,.2f}".rstrip("0").rstrip(".")
    return str(val)


def snapshot_bullets(v: Path):
    from .digest import _merged_weeks
    weeks = _merged_weeks(v)
    if not weeks:
        return ["No week recorded yet.", "Send a dashboard or income statement."]
    keys = sorted(weeks, key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0))
    wk = keys[-1]
    f = weeks[wk]["fields"]
    out = [f"Week **{wk}** (confidence {weeks[wk]['confidence']})"]
    for k, val in f.items():
        if k == "week":
            continue
        out.append(f"{k.replace('_', ' ')}: **{fmt(val)}**")
        if len(out) >= 9:
            break
    return out


def pending_bullets(v: Path):
    from .digest import _notes
    from .ledger import ledger_dir
    notes = _notes(ledger_dir(v) / "decisions")[-4:]
    out = []
    for p, fm in notes:
        name = fm.get("decision") or fm.get("name") or fm.get("title")
        out.append(str(name))
    return out or ["None recorded."]


def render_home(v: Path):
    latest = load_latest(v)
    fm = page_fm("Home", "Phone landing note: latest answer and what to upload next.",
                 "index", ["home"], status="final")
    L = ["# Panda's Coffee", ""]
    if latest:
        s = latest["summary"]
        L += [f"Updated {latest['when'].replace('T', ' ')[:16]}", "",
              "## Decision", "**" + "\n".join(_wrap(s.get('decision', 'n/a'))) + "**", "",
              f"Confidence: **{s.get('confidence', 'n/a')}**", ""]
        L += ["## Do now"] + _bullets(s.get("do_now") or ["nothing"]) + [""]
        L += ["## Do not"] + _bullets(s.get("do_not") or ["nothing"]) + [""]
        L += ["## Upload next"] + _bullets(s.get("next_upload") or ["nothing"]) + [""]
    else:
        L += ["No answer yet.", "",
              "## Start here", "- Take a game screenshot",
              "- Save it to the vault inbox folder",
              "- Or type a few words in a new inbox note",
              "- Check [[STATUS]], then come back here", ""]
    L += ["## Snapshot"] + _bullets(snapshot_bullets(v)) + [""]
    L += ["## Pending decisions"] + _bullets(pending_bullets(v)) + [""]
    if latest:
        L += ["## Full briefing", f"[[{latest['briefing']}]]", ""]
    L += ["## Status", "[[STATUS]]"]
    atomic_write(v / "HOME.md", dump_frontmatter(fm) + "\n" + "\n".join(L).rstrip() + "\n")


def _clock(iso: str) -> str:
    try:
        t = dt.datetime.fromisoformat(iso)
    except Exception as _e:
        note_problem(__name__, _e)
        return "unknown"
    day = "today" if t.date() == dt.date.today() else t.strftime("%b %d")
    return f"{t.strftime('%-I:%M %p')} {day}"


def render_status(v: Path, queue: int, error: str = "", note: str = ""):
    st = load_state(v)
    seen = st.get("worker_seen") or now_iso()
    fm = page_fm("Status", "Heartbeat: worker last seen, queue size, last problem.",
                 "index", ["status"], status="final")
    first = f"Mac worker last seen {_clock(seen)}. Queue: {queue}."
    L = [first, ""]
    if error:
        L += ["## Problem", *_wrap(error), ""]
    else:
        L += ["## Problem", "None.", ""]
    ok = st.get("last_success")
    L += ["## Last answer", f"{_clock(ok)}" if ok else "No answer yet.", ""]
    if st.get("quota_note"):
        L += ["## Gemini allowance", *_wrap(st["quota_note"]), ""]
    if note:
        L += ["## Note", *_wrap(note), ""]
    atomic_write(v / "STATUS.md", dump_frontmatter(fm) + "\n" + "\n".join(L).rstrip() + "\n")


def phone_check(text: str, max_line=80, max_cols=3):
    """Programmatic phone-width check. Returns a list of problems."""
    probs = []
    for i, line in enumerate(text.splitlines(), 1):
        if len(line) > max_line:
            probs.append(f"line {i} is {len(line)} chars")
        if line.strip().startswith("|"):
            cols = line.strip().strip("|").count("|") + 1
            if cols > max_cols:
                probs.append(f"line {i} table has {cols} columns")
    return probs
