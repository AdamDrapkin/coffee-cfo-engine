"""The game calendar: which date, month and season a week falls in, and how the hot and cold mix moved with it.

Week N ends on GAME_START + 7*N days (week 13 is Apr 2, 2022), which matches the date printed on the weekly results
and newspaper screens. The CEO states the game rule: customers want cold drinks in hot months and hot drinks in cold
months. The store is in San Francisco, northern hemisphere. The rule is the CEO's, not measured here, so the packet shows
the real hot and cold unit mix by week and date and lets the analysis test the rule against it.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .screens_core import GAME_START

SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
TREND = {1: "coldest part of the year", 2: "still cold, starting to warm", 3: "warming", 4: "warming", 5: "warm and getting hot", 6: "hot",
         7: "hottest part of the year", 8: "hot, starting to cool", 9: "cooling", 10: "cooling", 11: "cold and getting colder", 12: "cold"}
RULE = ("the CEO states customers want cold drinks in hot months and hot drinks in cold months (game rule as told by the CEO, not measured here)")


def week_date(week) -> dt.date:
    return GAME_START + dt.timedelta(days=7 * int(week))


def describe(week) -> str:
    d = week_date(week)
    return f"{d.strftime('%b')} {d.day}, {d.year}, {SEASONS[d.month]} ({TREND[d.month]})"


def mix_history(v: Path, upto, n: int = 6) -> list:
    """Hot and cold units per week from the weekly menu records (latest amendment per week)."""
    from .digest import _notes
    from .ledger import ledger_dir
    by = {}
    for _, fm in _notes(ledger_dir(v) / "menu-weeks"):
        try:
            by[int(fm.get("week"))] = fm.get("items") or []
        except (TypeError, ValueError):
            continue
    out = []
    for w in sorted(by):
        if w > int(upto):
            continue
        units = {"hot": 0, "cold": 0}
        for i in by[w]:
            g = str(i.get("group", ""))
            if g in units and str(i.get("sales", "")).isdigit():
                units[g] += int(i["sales"])
        if units["hot"] + units["cold"]:
            out.append((w, units["hot"], units["cold"]))
    return out[-n:]


def section(v: Path, week) -> list:
    try:
        w = int(week)
    except (TypeError, ValueError):
        return []
    L = [f"CALENDAR (week {w} ends {describe(w)}; dates count from {GAME_START}; {RULE}):"]
    hist = mix_history(v, w)
    if hist:
        L.append("  hot and cold units by week (units shown on that week's menu screens), with the date:")
        for wk, hot, cold in hist:
            d = week_date(wk)
            L.append(f"    - week {wk} ({d.strftime('%b')} {d.day}): hot {hot}, cold {cold}, cold share {round(100 * cold / (hot + cold))}%")
    nxt = ", ".join(f"week {w + k} = {week_date(w + k).strftime('%b')} {week_date(w + k).day}" for k in range(1, 5))
    L.append(f"  next four weeks: {nxt}. Season for week {w + 1}: {describe(w + 1)}.")
    L.append("  USE THIS: name the month and season in the analysis. Say whether the cold share moved the way the season predicts, and what the coming weeks "
             "should favor (for example menu, prices and stock for the coming season). Do not turn the seasonal rule into numbers; say it is a direction to test against next week's mix.")
    return L
