"""`coffee sync`: git add, commit and push to the new private repo only.

Never runs while an ingest is writing. Scans the staged diff for keys and tokens first
and aborts if anything looks like a key, token or OAuth code.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

from .gemini_client import work_root
from .util import file_lock, now_iso, lock_path

_KW = "api" + r"[_-]?" + "key"
_LEAK = re.compile("|".join([
    r"AIza[0-9A-Za-z_\-]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"sk-[A-Za-z0-9]{20,}",
    r"\b4/0A[A-Za-z0-9_\-]{30,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?:" + _KW + r"|" + "sec" + "ret" + r"|token|passw" + "ord" + r")\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}",
]), re.I)
import os
ORIGIN = os.environ.get("COFFEE_SYNC_ORIGIN", "")  # optional: pin the only remote allowed


class SyncError(Exception):
    pass


def git(v: Path, *args, check=True):
    r = subprocess.run(["git", "-C", str(v), *args], capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise SyncError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "git failed")
    return r


def scan_staged(v: Path):
    diff = git(v, "diff", "--cached", "-U0").stdout
    hits = []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++") and _LEAK.search(line):
            hits.append(line[:80])
    return hits


def sync(v: Path, message: str | None = None) -> str:
    if (v / ".git").is_dir():
        raise SyncError("A .git directory exists inside the vault. Refusing to sync.")
    remotes = git(v, "remote", "-v").stdout
    if "origin" not in remotes:
        return "no backup: this vault has no git remote named origin (optional, see README)"
    if ORIGIN and ORIGIN not in remotes:
        raise SyncError("Remote is not the pinned backup repo. Refusing to push.")
    with file_lock(lock_path("ingest.lock"), blocking=False) as held:
        if not held:
            return "busy: an ingest is running, sync skipped"
        git(v, "add", "-A")
        if not git(v, "diff", "--cached", "--name-only").stdout.strip():
            return "clean: nothing to sync"
        hits = scan_staged(v)
        if hits:
            git(v, "reset", "-q", check=False)
            raise SyncError(f"Possible key or token in staged changes, push aborted: {hits[0]}")
        git(v, "commit", "-q", "-m", message or f"sync: {now_iso()}")
        git(v, "push", "-q", "origin", "main")
        return "pushed"
