"""`coffee research "topic"`: sourced research into raw/research/, compiled into the wiki.

Runs in an isolated scratch folder that holds only the research rules: no
ledger, no digest. Fetched text is data. Instructions aimed at the model that
appear in it are quoted and ignored. Python decides labels: a finding is only
'Confirmed' when its source is official AND about Coffee Inc. 2+.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from . import index, seed
from .gemini_client import AuthError, BackendError, BackendTimeout, QuotaError, work_root
from .session import Busy, Outcome
from .util import (append_log, file_lock, now_iso, page_fm, quota_log, read_page, slugify, today,
                   write_page, lock_path)

LABELS = ("Confirmed", "Community", "Inference", "Unknown")
_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.S | re.I)

def rules_text(v: Path) -> str:
    """The research contract lives in core/research-contract.md so any agent can read it."""
    p = v / "core" / "research-contract.md"
    return p.read_text(encoding="utf-8")


def _parse(text):
    blocks = list(_FENCE.finditer(text))
    if not blocks:
        raise ValueError("no json block")
    return text[: blocks[-1].start()].strip(), json.loads(blocks[-1].group(1))


def _label(f, sources):
    """Python decides the label. The model only proposes.

    Confirmed needs ALL of: every cited source is official, the edition is Coffee Inc. 2+,
    and a verbatim quote of 20+ characters is given. Anything less is Community or Unknown.
    """
    label = f.get("label") if f.get("label") in LABELS else "Unknown"
    ids = f.get("source_ids") or []
    rels = [sources.get(i, {}).get("reliability") for i in ids]
    edition = f.get("edition")
    quote = str(f.get("quote") or "").strip()
    if label == "Confirmed" and not (ids and all(r == "official" for r in rels)
                                     and edition == "Coffee Inc. 2+" and len(quote) >= 20):
        label = "Community" if ids else "Unknown"
    if not ids and label in ("Confirmed", "Community"):
        label = "Unknown"
    return label


def run_research(v: Path, backend, topic: str) -> Outcome:
    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            raise Busy("Another ingest is already running.")
        try:
            text = backend.analyze(f"Research topic: {topic}\nFind what is documented and label each finding.",
                                   [], [rules_text(v)], "research")
        except QuotaError as e:
            quota_log(v, "research", [], "quota", backend=backend.name)
            return Outcome("failed", str(e), kind="quota", retry_after=e.retry_after)
        except (AuthError, BackendTimeout, BackendError) as e:
            quota_log(v, "research", [], "error", backend=backend.name)
            return Outcome("failed", str(e), kind="error")
        return compile_research(v, topic, text, backend.name, backend.tokens)


MARKER = "PASTE THE RESEARCH ANSWER BELOW THIS LINE"
TEMPLATE = ("# Research answer\n\nThe chat agent saves its research here, then runs research-absorb.\n\n" + MARKER + "\n")


def pasted_text(v: Path) -> str:
    p = v / "inbox" / "research-paste.md"
    if not p.exists():
        return ""
    raw = p.read_text(encoding="utf-8", errors="replace")
    return raw.split(MARKER, 1)[1].strip() if MARKER in raw else ""


def run_research_absorb(v: Path, by: str = "antigravity") -> Outcome:
    """File research the chat agent did itself (its own web search). Same labeling rules."""
    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            raise Busy("Another ingest is already running.")
        text = pasted_text(v)
        if not text:
            return Outcome("nothing", "inbox/research-paste.md is empty.")
        out = compile_research(v, None, text, by, None)
        if out.status == "done":
            from .util import atomic_write
            atomic_write(v / "inbox" / "research-paste.md", TEMPLATE)
        return out


def compile_research(v: Path, topic, text: str, backend_name: str, tokens) -> Outcome:
    if True:
        try:
            summary, data = _parse(text)
        except Exception as e:
            quota_log(v, "research", [], "rejected", backend=backend_name)
            return Outcome("failed", f"Research answer had no readable JSON ({e}). Nothing written.", kind="rejected")
        topic = topic or data.get("topic") or "untitled research"
        sources = {s.get("id"): s for s in data.get("sources", [])}
        for s in sources.values():
            host = urlparse(s.get("url", "")).netloc
            s["url_type"] = "grounding-redirect (not the publisher page)" if "vertexaisearch" in host else "direct"
        findings = []
        for f in data.get("findings", []):
            if f.get("section") not in seed.SECTIONS:
                continue
            f = dict(f)
            f["label"] = _label(f, sources)
            findings.append(f)

        slug = f"{today()}-{slugify(topic)[:50]}"
        raw = v / "raw" / "research" / f"{slug}.md"
        n = 2
        while raw.exists():
            raw = raw.with_name(f"{slug}-{n}.md")
            n += 1
        fm = page_fm(f"Research: {topic}", f"Raw research output for {topic}, with source registry.",
                     "research", ["research"], status="final", topic=topic, sources=list(sources.values()))
        body = [f"# Research: {topic}", "", summary, "", "## Source registry",
                "| Source ID | Publisher | URL | Date | Reliability | URL type |", "|---|---|---|---|---|---|"]
        for s in sources.values():
            body.append(f"| {s.get('id')} | {s.get('publisher', '')} | {s.get('url', '')} | {s.get('date', '')} | {s.get('reliability', 'unknown')} | {s['url_type']} |")
        body += ["", "## Findings (labels decided by the toolchain)"]
        for f in findings:
            q = f' quote "{str(f.get("quote")).strip()[:160]}"' if str(f.get("quote") or "").strip() else ""
            body.append(f"- [{f['label']}] {f.get('section')}: {f.get('claim')} (sources {', '.join(f.get('source_ids', []))}; edition {f.get('edition')};{q or ' no quote'})")
        if data.get("flagged_instructions"):
            body += ["", "## Flagged instructions found in fetched text (quoted, NOT obeyed)"]
            body += [f"- {x}" for x in data["flagged_instructions"]]
        write_page(raw, fm, "\n".join(body))

        seed.seed(v)
        for f in findings:
            p = seed.kb_path(v, f["section"])
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n### Update {today()}: {topic}\n- [{f['label']}] {f.get('claim')} "
                         f"(sources: {', '.join(f.get('source_ids', []))}; edition: {f.get('edition')}; raw: [[{raw.stem}]])\n")
        append_log(v, "research", topic, f"{len(findings)} findings, {len(sources)} sources. Raw: {raw.stem}")
        index.rebuild(v)
        quota_log(v, "research", [], "ok", tokens=tokens, backend=backend_name)
        out = Outcome("done", f"{len(findings)} findings from {len(sources)} sources")
        out.briefing = raw
        out.kept = data.get("flagged_instructions", [])
        out.labeled = [f"[{f['label']}] {f.get('section')}: {f.get('claim')}" for f in findings]
        return out


_LINE = re.compile(r"^- \[(Confirmed|Community|Inference|Unknown)\] ([^:]+): (.*) \(sources ([^;]*); edition ([^;)]*)(?:;(.*))?\)$")


def audit(v: Path) -> int:
    """Re-check every filed finding against the current rules. Appends a dated audit line to the
    knowledge-base note for each label that would now be lower. Idempotent. Raw notes are untouched."""
    changed = 0
    for raw in sorted((v / "raw" / "research").glob("*.md")):
        fm, body = read_page(raw)
        sources = {s["id"]: s for s in (fm or {}).get("sources", []) or []}
        for line in body.splitlines():
            m = _LINE.match(line.strip())
            if not m:
                continue
            old, section, claim, ids, edition, rest = m.groups()
            qm = re.search(r'quote "(.*)"', rest or "")
            f = {"label": old, "source_ids": [x.strip() for x in ids.split(",") if x.strip()],
                 "edition": edition.strip(), "quote": qm.group(1) if qm else ""}
            new = _label(f, sources)
            if new == old:
                continue
            from .seed import kb_path
            p = kb_path(v, section)
            if not p.exists():
                continue
            tag = f"AUDIT {raw.stem}: {claim[:60]}"
            text = p.read_text(encoding="utf-8")
            if tag in text:
                continue
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n### Audit {today()}: label lowered\n- {tag} ... [{old}] became [{new}] "
                         f"(no verbatim quote from an official Coffee Inc. 2+ source, or a secondary source was cited)\n")
            changed += 1
    if changed:
        append_log(v, "lint", f"research label audit: {changed} label(s) lowered")
    return changed
