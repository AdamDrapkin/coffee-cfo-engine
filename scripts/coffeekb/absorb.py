"""`coffee absorb`: file an answer the chat agent saved in inbox/answer-paste.md.

Same contract, same validation, same writers as the background worker path.
Only the extracted_by label differs.
"""
from __future__ import annotations
import shutil
import unicodedata
from pathlib import Path

from . import render
from .gemini_client import work_root
from .session import Busy, Outcome, _fail, commit_result
from . import frames as frames_mod
from .util import note_problem, append_log, atomic_write, file_lock, now_iso, quota_log, lock_path, today
from .validate import validate

MARKER = "PASTE THE ANSWER BELOW THIS LINE"
LEGACY_MARKER = "PASTE THE GEM ANSWER BELOW THIS LINE"
LEGACY_FILE = "gem-paste.md"   # conversations started before the rename still write here
TEMPLATE = ("# Answer\n\n"
            "The chat agent saves its full answer below the marker line, then runs absorb.\n\n" + MARKER + "\n")


def seed(v: Path):
    p = v / "inbox" / "answer-paste.md"
    if not p.exists():
        atomic_write(p, TEMPLATE)
    t = v / "inbox" / "_new-note-template.md"
    if not t.exists():
        atomic_write(t, "Type: location choice / weekly close / competitor / anything\n\n")


def _read_after_marker(p: Path) -> str:
    if not p.exists():
        return ""
    raw = p.read_text(encoding="utf-8", errors="replace")
    for m in (MARKER, LEGACY_MARKER):
        if m in raw:
            return raw.split(m, 1)[1].strip()
    return ""


def _norm(name: str) -> str:
    """macOS screenshot names contain a narrow no-break space before AM/PM that models usually write as a normal space."""
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()


def resolve_inbox_name(v: Path, raw_name: str):
    """Exact match first, then a whitespace/Unicode-insensitive match. Always a file directly inside inbox/."""
    name = Path(str(raw_name)).name
    d = v / "inbox"
    if not name or not d.exists():
        return None
    exact = d / name
    if exact.is_file():
        return exact
    want = _norm(name)
    hits = [p for p in d.iterdir() if p.is_file() and _norm(p.name) == want]
    return hits[0] if len(hits) == 1 else None


def pasted_source(v: Path):
    """The inbox file holding a pending answer: the current name first, then the legacy one."""
    for name in ("answer-paste.md", LEGACY_FILE):
        p = v / "inbox" / name
        if _read_after_marker(p):
            return p
    return None


def pasted_text(v: Path) -> str:
    p = pasted_source(v)
    return _read_after_marker(p) if p else ""


def run_absorb(v: Path, by: str = "antigravity") -> Outcome:
    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            raise Busy("Another ingest is already running.")
        src = pasted_source(v)
        text = _read_after_marker(src) if src else ""
        if not text:
            return Outcome("nothing", "answer-paste.md is empty.")
        out = file_text(v, text, by)
        if out.status == "done":
            atomic_write(v / "inbox" / "answer-paste.md", TEMPLATE)
            legacy = v / "inbox" / LEGACY_FILE
            if legacy.exists():
                atomic_write(legacy, TEMPLATE)
        return out


def file_text(v: Path, text: str, by: str, bundle_rows=None, refresh: bool = True) -> Outcome:
    """Validate an answer and file it. The caller holds the ingest lock."""
    if True:
        res = validate(text, note_text="", vault=v, known_files=None, bundle_rows=bundle_rows)
        if not res.ok:
            quota_log(v, "absorb", [], "rejected", backend=by)
            q = len([1 for _ in v.glob("inbox/*")])
            return _fail(v, Outcome("failed", f"Answer rejected, nothing was written: {res.reasons[0]}.", kind="rejected"), q)
        from . import inbox as inbox_mod
        moves, videos = [], []
        names = [str(r.get("file", "")) for r in res.data.get("intake", [])]
        names += [str(x) for x in res.data.get("inbox_files_used", []) or []]
        seen_names = set()
        for raw_name in names:
            cand = resolve_inbox_name(v, raw_name)   # basename only: never reach outside inbox/
            if cand is None:
                continue
            name = cand.name
            if (name in seen_names or name.startswith(".")
                    or name in ("answer-paste.md", "research-paste.md", "analysis-paste.md", "review-paste.md", "_new-note-template.md", LEGACY_FILE)):
                continue
            seen_names.add(name)
            ext = cand.suffix.lower()
            if ext in inbox_mod.IMAGES or ext in inbox_mod.NOTES:
                moves.append((name, cand))
            elif ext in frames_mod.VIDEO_EXT:
                videos.append(cand)
        bpath, _, _ = commit_result(v, res, extracted_by=by, mode="absorb",
                                    evidence_map={}, moves=moves, rebuild=False)
        vdir = frames_mod.videos_dir(v)
        for vid in videos:                        # heavy files: hidden scratch folder, git-ignored, pruned later
            dest = vdir / f"{today()}-{vid.name}"
            n = 2
            while dest.exists():
                dest = vdir / f"{today()}-{n}-{vid.name}"
                n += 1
            shutil.move(str(vid), str(dest))
        arch = v / "raw" / "answers"
        arch.mkdir(parents=True, exist_ok=True)
        atomic_write(arch / f"{now_iso().replace(':', '')}.md", text + "\n")
        from . import hubs, index as index_mod   # the archived answer must be linked from the hubs too
        index_mod.rebuild(v)
        try:
            from . import frames
            frames.cleanup(v)
        except Exception as _e:
            note_problem(__name__, _e)
            pass
        quota_log(v, "absorb", [], "ok", backend=by)
        if refresh:
            from .db import sync as dbsync
            dbsync.refresh(v)
        return Outcome("done", "ok", briefing=bpath, warnings=res.warnings, info=getattr(res, "info", []))


def _sections(text: str) -> dict:
    """Split the analysis into {lowercase heading: body} on markdown headings or bold lines."""
    import re
    out, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^\s*(?:#{1,4}\s*|\*\*)([^*#\n]+?)(?:\*\*)?:?\s*$", ln)
        if m and len(m.group(1)) < 70:
            cur = m.group(1).strip().lower()
            out[cur] = []
        elif cur is not None:
            out[cur].append(ln)
    return {k: "\n".join(v_).strip() for k, v_ in out.items()}


def _pick(secs: dict, *keys) -> str:
    for k, val in secs.items():
        if any(k.startswith(x) for x in keys):
            return val
    return ""


def _first_sentence(t: str, n=240) -> str:
    import re
    t = re.sub(r"[*_`>#]", "", " ".join(t.split()))
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    return (m.group(1) if m else t)[:n]


def analysis_records(text: str, week: str, conf: str, evidence: list) -> list:
    """Turn the CFO's analysis into ledger records: one decision, plus one assumption per unverified item."""
    import re
    secs = _sections(text)
    call, first = _pick(secs, "the call"), _pick(secs, "do this first")
    runner, notyet = _pick(secs, "runner-up", "runner up"), _pick(secs, "do not")
    risks, unknown = _pick(secs, "weak spots"), _pick(secs, "what i could not")
    ups = []
    if call and first:
        ups.append({"target": "decision", "op": "append", "confidence": conf, "evidence": evidence,
                    "fields": {"decision": f"Week {week}: " + _first_sentence(first) if week else _first_sentence(first),
                               "options": " ".join(runner.split())[:500] or "Not stated",
                               "recommendation": _first_sentence(call, 320),
                               "do_not_yet": " ".join(notyet.split())[:500],
                               "risks": " ".join(risks.split())[:500],
                               "ceo_decision": "Pending CEO confirmation"}})
    changed = _pick(secs, "what you changed", "what changed", "what the ceo changed")
    for ln in changed.splitlines():
        item = re.sub(r"^[\s\-*\d.)]+", "", ln).strip()
        if len(item) > 8:
            ups.append({"target": "decision", "op": "append", "confidence": "High", "evidence": evidence,
                        "fields": {"decision": (f"Week {week}: CEO changed: " if week else "CEO changed: ") + item[:200],
                                   "options": "Stated by the CEO", "recommendation": "n/a (a change the CEO made)",
                                   "ceo_decision": "Done, as stated by the CEO"}})
    for ln in re.split(r"\n|(?<=[.!?])\s+", unknown):
        item = re.sub(r"^[\s\-*\d.)]+", "", ln).strip()
        if len(item) > 12:
            ups.append({"target": "assumption", "op": "append", "confidence": "Low", "evidence": evidence,
                        "fields": {"item": item[:70], "assumption": item[:300], "how_to_verify": "Confirm on the next screens"}})
    return ups[:10]


# ------------------------------------------------------------------ the CFO analysis briefing

REQUIRED_PARTS = (("the call", "The call"), ("what happened", "What happened"), ("customers are saying", "What customers are saying"), ("why", "Why it happened"),
                  ("do this first", "Do this first"), ("do not", "Do not do yet"), ("weak spots", "Weak spots and risks"),
                  ("send next", "Send next"))
MIN_WORDS = 250


def run_analysis(v: Path, by: str = "antigravity") -> Outcome:
    """File the CFO's analysis (plain markdown in inbox/analysis-paste.md) as its own briefing.

    The engine already filed the data briefing with every number. This files the judgment beside it, and
    refuses an analysis that is too thin, so a week can never end up with numbers and no analysis."""
    import re
    from . import hubs, index as index_mod
    from .ledger import ensure_seed
    from .util import numbers_in, page_fm, write_page
    from .validate import _prose_dollar_warnings
    src = v / "inbox" / "analysis-paste.md"
    if not src.exists() or not src.read_text(encoding="utf-8").strip():
        return Outcome("nothing", "inbox/analysis-paste.md is empty. Write your full analysis there first.")
    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            raise Busy("Another ingest is already running. Try again in a minute.")
        text = src.read_text(encoding="utf-8").strip()
        text = re.sub(r"^.*PASTE THE ANALYSIS BELOW THIS LINE.*$", "", text, flags=re.M).strip()
        low = text.lower()
        words = len(text.split())
        missing = [label for key, label in REQUIRED_PARTS if key not in low]
        if words < MIN_WORDS or missing:
            why = []
            if words < MIN_WORDS:
                why.append(f"only {words} words (needs at least {MIN_WORDS})")
            if missing:
                why.append("missing: " + ", ".join(missing))
            return _fail(v, Outcome("failed", "Analysis rejected, nothing was written: " + "; ".join(why) +
                                    ". Rewrite it with every section of the format in .agents/skills/coffee-week/SKILL.md step 5 and run analysis-absorb again.",
                                    kind="rejected"), 0)
        ensure_seed(v)
        seen = set()
        latest = v / ".coffee-work" / "week" / "latest.md"
        if latest.exists():
            seen |= numbers_in(latest.read_text(encoding="utf-8"))
        for f in (v / ".coffee-work" / "week").glob("2*.json"):
            seen |= numbers_in(f.read_text(encoding="utf-8"))
        for b in sorted((v / "wiki" / "briefings").glob("*absorb*.md"))[-4:]:   # numbers filed by hand this week count as seen too
            seen |= numbers_in(b.read_text(encoding="utf-8"))
        warns = _prose_dollar_warnings(text, seen, v)
        try:
            from .analysis import _store_by_week
            hist = _store_by_week(v)
            blend = str(hist[max(hist)].get("active_blend", "")) if hist else ""
            if blend and "default" not in blend.lower() and "default blend" in low:
                warns.append(f"The analysis says 'default blend' but the blend in use is {blend}. Do not compare its price with the default blend's.")
        except Exception as _e:
            note_problem(__name__, _e)
            pass
        stamp = now_iso()
        stem = f"{today()}-{stamp[11:16].replace(':', '')}-analysis"
        bdir = v / "wiki" / "briefings"
        bpath = bdir / f"{stem}.md"
        n = 2
        while bpath.exists():
            bpath = bdir / f"{stem}-{n}.md"
            n += 1
        stem = bpath.stem
        data = [x for x in sorted(bdir.glob("*-absorb*.md")) if x.stem < stem]
        earlier = [x for x in sorted(bdir.glob("*.md")) if x.stem < stem]
        m = re.search(r"the call[^\n]*\n+(.+)", text, flags=re.I)
        summary = re.sub(r"[*_#>`]", "", (m.group(1) if m else text.splitlines()[0]))[:220].strip()
        cm = re.search(r"confidence\W{0,4}\s*(high|moderate|low)\b", text, re.I)
        conf = cm.group(1).capitalize() if cm else "Moderate"
        cur = v / ".coffee-work" / "week" / "current.json"
        wk_num = ""
        try:
            import json as _j
            wk_num = str(_j.loads(cur.read_text(encoding="utf-8")).get("week", ""))
        except (OSError, ValueError):
            wk_num = str(__import__("coffeekb.health", fromlist=["current_week"]).current_week(v) or "")
        wk = re.match(r"(\d+)", wk_num) or re.search(r"week (\d+)", low)
        text = re.sub(r"\A#[^\n]*Analysis[^\n]*\n+", "", text, flags=re.I)
        body = (f"# Panda's Coffee CFO Analysis - Week {wk.group(1)}\n\n" if wk else "# Panda's Coffee CFO Analysis\n\n") + text + "\n"
        body += "\n## Sequence\n"
        if data:
            body += f"- Data briefing this analysis is based on: [[{data[-1].stem}]]\n"
        if earlier:
            body += f"- Previous briefing: [[{earlier[-1].stem}]]\n"
        if warns:
            body += ("\n## Checker warnings\nThese dollar figures were not on a screen, in the ledger or in the engine packet and are not labeled "
                     "as estimates. Treat them as guesses:\n" + "\n".join(f"- {w}" for w in warns) + "\n")
        fm = page_fm(f"CFO analysis {stamp[:16].replace('T', ' ')}", summary or "CFO analysis", "briefing",
                     ["briefing", "analysis"], status="final", confidence=conf, extracted_by=by)
        from . import facts
        facts.ensure(v)
        warns += facts.guard_warnings(v, text)
        from . import lookup
        warns += lookup.claims_warnings(v, text)
        for kind, kws, fact in facts.parse_learned(_pick(_sections(text), "game facts learned", "game facts")):
            facts.append(v, kind, kws, fact, f"CEO or screens, filed with {stem}")
        ups = analysis_records(text, wk.group(1) if wk else "", conf, [f"wiki/briefings/{stem}.md"])
        from . import ledger, digest, hubs as hubs_mod
        written = ledger.write_updates(v, {"ledger_updates": ups}, by, stem, {}) if ups else []
        links = sorted({f"- [[{p.stem}]]" for p in written if p.name != "assumptions-and-unknowns.md"})
        if links:
            body += "\n## Ledger notes\n" + "\n".join(links) + "\n"
        if any(p.name == "assumptions-and-unknowns.md" for p in written):
            body += "\n- Assumptions logged in [[assumptions-and-unknowns]]\n"
        write_page(bpath, fm, body)
        from .db import sync as dbsync
        dbsync.refresh(v)                      # the database follows every filing
        digest.write(v)
        try:
            from . import state_page
            state_page.write(v)
        except Exception as _e:
            note_problem(__name__, _e)
            pass
        arch = v / "raw" / "answers"
        arch.mkdir(parents=True, exist_ok=True)
        atomic_write(arch / f"{stamp.replace(':', '')}-analysis.md", text + "\n")
        src.unlink()
        index_mod.rebuild(v)
        quota_log(v, "analysis", [], "ok", backend=by)
        return Outcome("done", f"Analysis filed ({words} words). Records written: {sum(1 for u in ups if u['target'] == 'decision')} decision, {sum(1 for u in ups if u['target'] == 'assumption')} assumption(s).", briefing=bpath, warnings=warns)


def run_review_file(v: Path, by: str = "antigravity") -> Outcome:
    """File rows for screens a person looked at, from a plain table in inbox/review-paste.md, no JSON needed.

    Each line is:  FILE | field | value | unit(optional)
    Lines starting with # are ignored. Every file named is treated as reviewed and archived from the inbox."""
    import json
    import re
    src = v / "inbox" / "review-paste.md"
    if not src.exists() or not src.read_text(encoding="utf-8").strip():
        return Outcome("nothing", "inbox/review-paste.md is empty. Write one line per value: FILE | field | value | unit")
    rows, files = [], []
    for ln in src.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.lstrip().startswith("#") or "|" not in ln:
            continue
        parts = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(parts) < 3:
            continue
        f, field, val = parts[0], parts[1], parts[2]
        unit = parts[3] if len(parts) > 3 else ""
        rows.append({"file": f, "field": re.sub(r"[^a-z0-9_]+", "_", field.lower()).strip("_"), "value": val, "unit": unit,
                     "confidence": "High", "unreadable": val.lower() == "unreadable"})
        if f not in files and resolve_inbox_name(v, f):
            files.append(f)
    if not rows:
        return Outcome("failed", "No valid lines found. Each line needs: FILE | field | value")
    from .health import current_week
    wk = str(current_week(v))
    text = ("# Panda's Coffee CFO Briefing - Reviewed Screens\n\n## Executive Decision\n**Recommendation:** Record the values read from the reviewed screens; no decision is implied.\n\n"
            "**Confidence:** Moderate\n\n**One-sentence reason:** These screens were read by a person because the engine did not recognize their layout; the values are listed below.\n\n"
            "## What the Evidence Shows\n" + "\n".join(f"- {r['file']}: {r['field'].replace('_', ' ')} = {r['value']} {r['unit']}".rstrip() for r in rows)
            + "\n\n## Next Upload Request\nUpload:\n1. Nothing further for these screens\n")
    data = {"intake": [{"file": f, "type": "reviewed screen", "confidence": "Moderate", "game_week": wk} for f in files],
            "extraction": rows, "ledger_updates": [], "next_upload_request": ["Nothing further"], "ceo_words": "", "inbox_files_used": files,
            "mobile_summary": {"decision": "Reviewed screens recorded", "confidence": "Moderate", "do_now": ["Continue"], "do_not": ["Nothing"], "next_upload": ["Nothing further"]}}
    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            raise Busy("Another ingest is already running. Try again in a minute.")
        out = file_text(v, text + "\n```json\n" + json.dumps(data, indent=1) + "\n```\n", by)
        if out.status == "done":
            out.message += ("\nNOW TEACH THE ENGINE: these screens were only recorded by hand. If they will be uploaded again (company comparison, agency pages, settings boards), "
                            "write the layout rule in inbox/layout-paste.md and run `sh scripts/run.sh learn-layout` (see references/self-repair.md). "
                            "If they will not recur, say \"not recurring\" in your answer. Do not skip this.")
            src.unlink()
            from . import index as index_mod
            index_mod.rebuild(v)          # the paste file is gone, so the hubs must stop listing it
        return out
