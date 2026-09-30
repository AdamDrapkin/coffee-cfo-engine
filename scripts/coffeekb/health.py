"""`coffee session-start` and `coffee session-health`: one chat conversation per in-game week.

A chat cannot see its own size, but the vault records the work done. Every conversation
re-reads its whole history on each message, and each archived screen, video frame and
filed briefing adds to it. When the load gets high, replies slow down and can stall on
"working". The vault is the memory, so a new conversation loses nothing.

How it works
- A new conversation runs `session-start`, which drops a marker: the time and the in-game week.
- `session-health` counts the load since that marker:
    1 point per screen archived or video frame extracted,
    8 points per filing (absorb),
    0.5 point per KB of briefing text written.
- OK below 100 points (it says how much room is left), NOTICE from 100, NEW from 150.
- If the in-game week has moved past the marker's week, it says WEEK: start a new conversation
  for the new week.
- With no marker (the chat forgot to start one) it counts from the start of the current week.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

NOTICE, NEW = 100, 150
FALLBACK_HOURS = 6.0
_SHOT = re.compile(r"^\d{4}-\d{2}-\d{2}-wk([a-z0-9]+)-")


def _marker_path(v: Path) -> Path:
    p = v / ".coffee-work"
    p.mkdir(parents=True, exist_ok=True)
    return p / "session.json"


def current_week(v: Path) -> int:
    """Highest in-game week seen in the ledger or in archived screenshot names. 0 if none yet."""
    best = 0
    weeks = v / "wiki" / "ledger" / "weeks"
    if weeks.exists():
        for p in weeks.glob("week-*.md"):
            m = re.match(r"week-(\d+)", p.stem)
            if m:
                best = max(best, int(m.group(1)))
    shots = v / "raw" / "screenshots"
    if shots.exists():
        for p in shots.iterdir():
            m = _SHOT.match(p.name)
            if m and m.group(1).isdigit():
                best = max(best, int(m.group(1)))
    return best


def _week_start(v: Path, week: int) -> float:
    """Estimated start of a week: the earliest screenshot filed for it, else a few hours ago."""
    stamps = []
    shots = v / "raw" / "screenshots"
    if shots.exists():
        for p in shots.iterdir():
            m = _SHOT.match(p.name)
            if m and m.group(1) == str(week):
                stamps.append(p.stat().st_ctime)
    return min(stamps) if stamps else time.time() - FALLBACK_HOURS * 3600


def start(v: Path) -> str:
    wk = current_week(v)
    _marker_path(v).write_text(json.dumps({"started": time.time(), "week": wk}), encoding="utf-8")
    label = f"week {wk}" if wk else "the start of the game"
    return f"SESSION STARTED for {label}. Load so far: 0 of {NOTICE}. It will report whether this conversation is still good after each filing."


def _marker(v: Path):
    p = _marker_path(v)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _recent_absorbs(v: Path, since: float) -> int:
    log = v / "wiki" / "outputs" / "quota-log.md"
    if not log.exists():
        return 0
    n = 0
    for line in log.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 6 and cells[2] == "absorb" and cells[5] == "ok":
            try:
                t = dt.datetime.fromisoformat(cells[0]).timestamp()
            except ValueError:
                continue
            if t >= int(since):      # log times are stamped to the second
                n += 1
    return n


def measure(v: Path, since: float):
    images = 0
    shots = v / "raw" / "screenshots"
    if shots.exists():
        images = sum(1 for p in shots.iterdir() if p.is_file() and p.stat().st_ctime >= since)
    frames = 0
    fdir = v / ".coffee-work" / "frames"
    if fdir.exists():
        for m in fdir.glob("*/manifest.md"):
            if m.stat().st_ctime >= since:
                frames += sum(1 for ln in m.read_text(encoding="utf-8").splitlines() if ln.startswith("- frame-"))
    kb = 0.0
    brief = v / "wiki" / "briefings"
    if brief.exists():
        kb = sum(p.stat().st_size for p in brief.glob("*.md") if p.stat().st_ctime >= since) / 1000.0
    absorbs = _recent_absorbs(v, since)
    points = (images + frames) * 1.0 + absorbs * 8.0 + kb * 0.5
    return {"screens": images + frames, "filings": absorbs, "briefing_kb": round(kb), "points": round(points)}


def report(v: Path):
    """(level, message). level is OK, NOTICE, NEW or WEEK."""
    wk = current_week(v)
    marker = _marker(v)
    if marker and int(marker.get("week", 0)) > 0 and wk > int(marker.get("week", 0)):
        return "WEEK", (f"NEW IN-GAME WEEK: week {wk} has started (this conversation began in week {marker.get('week', 0)}). "
                        f"Start a new conversation for week {wk}. Everything is saved in the vault, so nothing is lost.")
    since = float(marker["started"]) if marker else _week_start(v, wk)
    m = measure(v, since)
    wlabel = f"Week {wk}" if wk else "Game start"
    detail = f"{m['screens']} screens, {m['filings']} filings and {m['briefing_kb']} KB of briefings since this conversation began"
    if m["points"] >= NEW:
        return "NEW", (f"START A NEW CONVERSATION NOW ({wlabel}). This one has carried too much ({detail}). "
                       "Replies will slow down or stall. Everything is saved in the vault, so nothing is lost. "
                       "Open a new conversation before your next message.")
    if m["points"] >= NOTICE:
        return "NOTICE", (f"{wlabel}: this conversation is getting heavy ({detail}). Finish what you are doing, then start a "
                          "new conversation at your next natural pause; everything is saved in the vault.")
    room = NOTICE - m["points"]
    return "OK", (f"{wlabel}: still good. {detail} ({m['points']} of {NOTICE}); room for roughly {room} more screens "
                  "(a filing counts as 8).")
