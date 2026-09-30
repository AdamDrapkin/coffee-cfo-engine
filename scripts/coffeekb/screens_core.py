"""Shared building blocks for the screen parsers: text boxes, documents, money helpers."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

MONEY = re.compile(r"^[+\-]?\$\d[\d,]*(?:\.\d+)?$")


GAME_START = dt.date(2022, 1, 1)          # weekly results dates are counted from here


LOW_CONF = 0.85


@dataclass
class Line:
    t: str
    c: float
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2


@dataclass
class Doc:
    file: str
    w: int
    h: int
    lines: list
    stars: list

    @classmethod
    def from_json(cls, d):
        lines = [Line(l["t"].strip(), l["c"], l["x"], l["y"], l["w"], l["h"]) for l in d.get("lines", []) if l["t"].strip()]
        return cls(d["file"], d.get("w", 0), d.get("h", 0), lines, d.get("stars", []))


@dataclass
class Parsed:
    kind: str
    rows: list = field(default_factory=list)       # extraction rows
    updates: list = field(default_factory=list)    # ledger update proposals
    facts: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    week: str = ""
    conf: float = 1.0


def is_money(t: str) -> bool:
    return bool(MONEY.match(t.strip()))


def money_val(t: str) -> float:
    s = t.strip()
    neg = s.startswith("-")
    n = float(re.sub(r"[+\-$,]", "", s))
    return -n if neg else n


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def row(file, field_, value, unit="", conf=1.0):
    name = file.split("/")[-1]
    if conf < 0.5:
        return {"file": name, "field": field_, "value": "unreadable", "unit": unit, "confidence": "Low", "unreadable": True}
    return {"file": name, "field": field_, "value": str(value), "unit": unit,
            "confidence": "High" if conf >= LOW_CONF else "Moderate", "unreadable": False}


def _find(lines, text, exact=True, **kw):
    for l in lines:
        t = l.t.upper()
        if (t == text.upper() if exact else text.upper() in t):
            if all(kw.get(k) is None or ok(l) for k, ok in kw.items() if callable(ok)):
                return l
    return None


def _row_value(lines, label: Line, dy=30, min_dx=0, money=True):
    """Value on the same row to the right of a label."""
    cands = [l for l in lines if l is not label and abs(l.cy - label.cy) <= dy and l.x > label.x + label.w * 0.5 + min_dx
             and (is_money(l.t) if money else True)]
    return min(cands, key=lambda l: l.x) if cands else None


def _center(lines, lo=200, hi=900):
    return [l for l in lines if lo <= l.cx <= hi]


def _num(t: str):
    t = t.strip()
    return t if re.fullmatch(r"-?\$?[\d,]+(\.\d+)?", t) else None


_STORE_ADDR = re.compile(r"^(\d+ [A-Z][\w. ]+?)(,|$)")


def _store_name(d: Doc) -> str:
    l = next((l for l in d.lines if 240 <= l.y <= 280 and _STORE_ADDR.match(l.t)), None)
    return _STORE_ADDR.match(l.t).group(1) if l else ""


__all__ = ['MONEY', 'GAME_START', 'LOW_CONF', 'Line', 'Doc', 'Parsed', 'is_money', 'money_val', 'slug', 'row', '_find', '_row_value', '_center', '_num', '_STORE_ADDR', '_store_name']
