"""Deterministic validation of a model answer (worker or chat agent) before any file is written.

Rejects, with a readable reason, when the JSON does not parse, the briefing is
missing required parts, a number in ledger_updates was never seen in extraction
or the CEO's note, a confidence label is missing or invalid, an append would
overwrite an existing week, an amend has no reason, or mobile_summary is
missing or too long.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import note_problem, CONFIDENCE, norm_number, numbers_in

MAX_MOBILE_LINES = 12
TARGETS = {
    "week", "store", "city", "competitor", "decision", "capital-allocation",
    "loan", "investment", "acquisition", "assumption", "event", "test", "catalog", "correction", "review", "menu-week",
}
_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.S | re.I)
_PURE_NUMBER = re.compile(r"^\s*[-(]?\$?-?\d[\d,]*\.?\d*\)?\s*[%kKmMbB]?\s*$")


@dataclass
class Result:
    ok: bool
    reasons: list = field(default_factory=list)
    briefing: str = ""
    data: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def explain(self) -> str:
        return "Rejected: " + "; ".join(self.reasons) if not self.ok else "OK"


def parse_response(text: str):
    """Return (briefing, data, error). Uses the last fenced json block."""
    blocks = list(_FENCE.finditer(text))
    if not blocks:
        return text, None, "no fenced json block found"
    last = blocks[-1]
    briefing = text[: last.start()].strip()
    try:
        data = json.loads(last.group(1))
    except json.JSONDecodeError as e:
        return briefing, None, f"json does not parse ({e.msg} at line {e.lineno})"
    if not isinstance(data, dict):
        return briefing, None, "json block is not an object"
    return briefing, data, None


def _numeric_leaves(obj, key=""):
    """Yield (key, raw) for numeric values in nested fields. Skips derived_* keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("derived_"):
                continue
            yield from _numeric_leaves(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _numeric_leaves(v, key)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        yield key, obj
    elif isinstance(obj, str) and _PURE_NUMBER.match(obj):
        yield key, obj


_LABEL_WORDS = ("last week", "from the ledger", "computed", "estimate", "assum", "illustrat", "heuristic", "example", "unknown", "hypothetical")
_DOLLAR = re.compile(r"\$\s?\d[\d,]*\.?\d*(?:[kKmMbB]\b)?")


def _derived(nums: set, cap: int = 250) -> set:
    """Sums and differences of two seen numbers: plain arithmetic on real figures is not an invention."""
    vals = []
    for n in list(nums)[:cap]:
        try:
            vals.append(float(n))
        except ValueError:
            pass
    out = set()
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            for x in (a + b, abs(a - b)):
                out.add(f"{x:.4f}".rstrip("0").rstrip("."))
    return out


def _prose_dollar_warnings(briefing: str, seen: set, vault) -> list:
    """Dollar figures in the briefing text that were never seen and are not labeled as estimates."""
    allowed = set(seen) | {"800000"} | _derived(set(seen) | {"800000"})
    if vault is not None:
        try:
            from .digest import build
            allowed |= numbers_in(build(vault))
        except Exception as _e:
            note_problem(__name__, _e)
            pass
    out = []
    for line in briefing.splitlines():
        low = line.lower()
        for m in _DOLLAR.finditer(line):
            n = norm_number(m.group(0))
            if n is None or n in allowed or n.lstrip("-") in allowed:
                continue
            # a label word only excuses the figure it is next to, not every figure on the line
            near = low[max(0, m.start() - 70): m.end() + 45]
            if any(w in near for w in _LABEL_WORDS):
                continue
            out.append(f"{m.group(0).strip()} in: {line.strip()[:90]}")
    return out


def validate(text: str, note_text: str = "", vault: Path | None = None,
             known_files=None, bundle_rows=None) -> Result:
    reasons = []
    briefing, data, err = parse_response(text)
    if err:
        return Result(False, [err], briefing)

    low = briefing.lower()
    for need in ("recommendation", "confidence", "next upload request"):
        if need not in low:
            reasons.append(f"briefing lacks '{need.title()}'")

    for key in ("intake", "extraction", "ledger_updates", "next_upload_request", "mobile_summary"):
        if key not in data:
            reasons.append(f"json lacks '{key}'")
    if reasons and any("json lacks" in r for r in reasons):
        return Result(False, reasons, briefing, data)

    # confidence labels everywhere they are required
    for i, row in enumerate(data.get("intake", [])):
        if row.get("confidence") not in CONFIDENCE:
            reasons.append(f"intake[{i}] has no valid confidence label")
    for i, row in enumerate(data.get("extraction", [])):
        if row.get("confidence") not in CONFIDENCE:
            reasons.append(f"extraction[{i}] has no valid confidence label")

    # mobile summary
    ms = data.get("mobile_summary")
    if not isinstance(ms, dict) or not ms.get("decision"):
        reasons.append("mobile_summary missing or has no decision")
    else:
        if ms.get("confidence") not in CONFIDENCE:
            reasons.append("mobile_summary has no valid confidence label")
        n = 2 + sum(len(ms.get(k, []) or []) for k in ("do_now", "do_not", "next_upload"))
        if n > MAX_MOBILE_LINES:
            reasons.append(f"mobile_summary is {n} lines, limit is {MAX_MOBILE_LINES}")

    used = data.get("inbox_files_used", [])
    if not isinstance(used, list) or any(not isinstance(x, str) for x in used):
        reasons.append("inbox_files_used must be a list of file names")

    real_rows = [r for r in data.get("extraction", []) if r.get("file") != "ceo-message"]
    says_high = (isinstance(ms, dict) and ms.get("confidence") == "High") or re.search(r"\*\*Confidence:\*\*\s*High", briefing)
    if says_high and not real_rows:
        reasons.append("Confidence High needs numbers read from a screenshot; with none, use Moderate or Low")

    # numbers the model actually saw
    seen = set()
    for row in data.get("extraction", []):
        seen |= numbers_in(row.get("value", ""))
    seen |= numbers_in(note_text)
    rows = bundle_rows
    if rows is None and vault is not None and data.get("bundle"):
        bp = Path(vault) / ".coffee-work" / "week" / f"{re.sub(r'[^A-Za-z0-9_-]', '', str(data['bundle']))}.json"
        if bp.exists():
            try:
                rows = json.loads(bp.read_text(encoding="utf-8")).get("rows", [])
            except ValueError:
                rows = None
    for r_ in rows or []:      # values the week engine read from screens: real, so a follow-up answer may cite them
        seen |= numbers_in(r_.get("value", ""))
    ceo_words = str(data.get("ceo_words", "") or "")
    ceo_nums = numbers_in(ceo_words)
    seen |= ceo_nums
    for i, row in enumerate(data.get("extraction", [])):
        if row.get("file") == "ceo-message" and not row.get("unreadable"):
            for n in numbers_in(row.get("value", "")):
                if n not in ceo_nums:
                    reasons.append(f"extraction[{i}] says {row.get('value')!r} came from the CEO's message, "
                                   "but that number is not in ceo_words")
    for row in data.get("intake", []):
        seen |= numbers_in(row.get("game_week", ""))

    for i, up in enumerate(data.get("ledger_updates", [])):
        tag = f"ledger_updates[{i}]"
        if up.get("confidence") not in CONFIDENCE:
            reasons.append(f"{tag} has no valid confidence label")
        if up.get("target") not in TARGETS:
            reasons.append(f"{tag} has unknown target '{up.get('target')}'")
        op = up.get("op")
        if op not in ("append", "amend"):
            reasons.append(f"{tag} op must be append or amend")
        if op == "amend" and not str(up.get("reason", "")).strip():
            reasons.append(f"{tag} is an amend without a reason")
        fields = up.get("fields", {})
        if not isinstance(fields, dict):
            reasons.append(f"{tag} fields must be an object")
            continue
        if up.get("target") == "correction":
            for need in ("claim", "correction"):
                if not str(fields.get(need, "")).strip():
                    reasons.append(f"{tag} is a correction without '{need}'")
        for key, raw in _numeric_leaves(fields):
            n = norm_number(raw)
            if n is None:
                continue
            if n not in seen and n.lstrip("-") not in seen:
                reasons.append(
                    f"{tag} number {raw!r} (field '{key}') is not in extraction or the CEO's note"
                )
        if vault is not None and up.get("target") == "week":
            from .ledger import week_exists  # local import: avoids a cycle
            wk = fields.get("week")
            if wk not in (None, "", "not_shown", "unreadable"):
                if op == "append" and week_exists(vault, wk):
                    reasons.append(f"{tag} would overwrite existing week {wk}; use amend with a reason")
                if op == "amend" and not week_exists(vault, wk):
                    reasons.append(f"{tag} amends week {wk} which does not exist")
            elif op == "append":
                reasons.append(f"{tag} week update has no readable week number")

    if known_files is not None:
        known = set(known_files)
        for row in data.get("intake", []):
            if row.get("file") and row["file"] not in known:
                reasons.append(f"intake names unknown file '{row['file']}'")

    warnings = _prose_dollar_warnings(briefing, seen, vault)
    n_up = len(data.get("ledger_updates", []))
    if n_up > 60 and not data.get("bundle"):   # the week engine files big batches by design
        warnings.append(f"This answer files {n_up} records at once. Split big jobs into answers of about 40 or fewer, filing each before the next.")
    if says_high and not data.get("bundle"):   # engine briefings are read straight from screens
        low = briefing.lower()
        soft = sum(low.count(w) for w in ("community", "heuristic", "estimate", "unknown / requires testing", "inference"))
        if soft >= 3:
            warnings.append(f"Confidence is High, yet the briefing leans on {soft} community, heuristic, estimate, inference or unknown items. "
                            "High should mean the recommendation follows from numbers read on screen; consider Moderate.")
    return Result(not reasons, reasons, briefing, data, warnings)
