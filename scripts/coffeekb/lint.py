"""`coffee lint`: deterministic checks. Never calls Gemini.

Checks: frontmatter, dangling wikilinks, orphan pages, append-only violations
(against git HEAD), missing confidence on ledger notes, index drift.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

from . import index
from .ledger import FOLDERS
from .util import CONFIDENCE, read_page

REQUIRED = ("title", "date_created", "date_modified", "summary", "tags", "type", "status")
TYPES = {"knowledge", "ledger", "briefing", "test", "decision", "index", "research", "hub"}
RUNNING_TABLES = {"assumptions-and-unknowns.md", "screenshot-intake-log.md", "quota-log.md"}
_LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_FENCE = re.compile(r"```.*?```", re.S)


def _md_files(v: Path):
    skip = {".git", ".obsidian", ".venv", "node_modules"}
    for p in v.rglob("*.md"):
        if any(part in skip for part in p.relative_to(v).parts):
            continue
        yield p


def _links(text: str):
    return [m.group(1).strip() for m in _LINK.finditer(_FENCE.sub("", text))]


def _git_changes(v: Path):
    r = subprocess.run(["git", "-C", str(v), "diff", "HEAD", "--numstat", "--", "wiki/ledger", "wiki/briefings", "raw"],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.splitlines() if r.returncode == 0 else None


def run(v: Path, fix_index=False):
    issues = []
    if fix_index:
        index.rebuild(v)

    stems = {p.stem for p in _md_files(v)}
    wiki_pages = list(index.wiki_pages(v))
    inbound = {s: 0 for s in stems}
    pages_to_check = wiki_pages + [v / "HOME.md", v / "STATUS.md", v / "wiki" / "index.md", v / "wiki" / "log.md"]

    for p in pages_to_check:
        if not p.exists():
            continue
        rel = p.relative_to(v)
        fm, body = read_page(p)
        if fm is None:
            issues.append(f"{rel}: missing or unreadable frontmatter")
        else:
            miss = [k for k in REQUIRED if k not in fm]
            if miss:
                issues.append(f"{rel}: frontmatter lacks {', '.join(miss)}")
            if fm.get("type") and fm["type"] not in TYPES:
                issues.append(f"{rel}: unknown type '{fm['type']}'")
            if fm.get("kind") or str(rel).startswith("wiki/ledger/weeks"):
                if fm.get("confidence") not in CONFIDENCE:
                    issues.append(f"{rel}: ledger note has no valid confidence")
                if not fm.get("extracted_by"):
                    issues.append(f"{rel}: ledger note has no extracted_by")
                if "source_screenshot" not in fm:
                    issues.append(f"{rel}: ledger note has no source_screenshot")
                if fm.get("op") == "amend" and not fm.get("reason"):
                    issues.append(f"{rel}: amendment has no reason")
        for target in _links(body if fm is not None else p.read_text(encoding="utf-8")):
            if target not in stems:
                issues.append(f"{rel}: dangling link [[{target}]]")
            elif p.stem != target:
                inbound[target] = inbound.get(target, 0) + 1

    from . import corrections, hubs
    issues += corrections.problems(v)
    reach, all_files = hubs.reachable_from_map(v)
    if not reach:
        issues.append("wiki/hubs/map.md is missing: run coffee lint --fix-index")
    else:
        for p in all_files:
            if p not in reach:
                issues.append(f"{p.relative_to(v)}: not reachable from the vault map (no chain of links leads to it)")
    for p in all_files:
        if inbound.get(p.stem, 0) == 0 and not any(_links(p.read_text(encoding="utf-8", errors="replace"))):
            issues.append(f"{p.relative_to(v)}: isolated (no links in or out)")

    changes = _git_changes(v)
    if changes:
        for line in changes:
            added, deleted, path = (line.split("\t") + ["", "", ""])[:3]
            if path.startswith("raw/") and not path.startswith("raw/screenshots/") and deleted not in ("0", "-"):
                issues.append(f"{path}: append-only violation, {deleted} lines removed")
            elif path.startswith("wiki/ledger") and Path(path).name not in RUNNING_TABLES and deleted not in ("0", "-"):
                issues.append(f"{path}: append-only violation, existing ledger note was changed")
            elif Path(path).name in RUNNING_TABLES and deleted not in ("0", "-"):
                issues.append(f"{path}: running table lost rows")
    r = subprocess.run(["git", "-C", str(v), "diff", "HEAD", "--name-status", "--", "wiki/ledger", "raw"],
                       capture_output=True, text=True, timeout=60)
    for line in r.stdout.splitlines():
        if line.startswith("D\t") and not line[2:].startswith("raw/screenshots/"):   # images live in iCloud, not git
            issues.append(f"{line[2:]}: append-only violation, file deleted")
    return issues
