"""Shared helpers: vault paths, frontmatter, locking, logs, retry.

All paths resolve relative to the vault root so the vault can move (for
example into iCloud) by changing one place: the COFFEE_VAULT environment
variable, or simply moving the folder.
"""
from __future__ import annotations
import contextlib
import datetime as dt
import fcntl
import os
import re
import time
from pathlib import Path

import sys

try:
    import yaml
except ImportError:  # plain python3 with nothing installed: use the bundled pure-Python copy (MIT)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_vendor"))
    import yaml

CONFIDENCE = ("High", "Moderate", "Low", "Unknown")


def vault() -> Path:
    env = os.environ.get("COFFEE_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent.parent


def lock_path(name: str) -> Path:
    """Lock files live in the vault (gitignored) so a sandboxed chat and the worker share them."""
    p = vault() / ".coffee-work"
    p.mkdir(parents=True, exist_ok=True)
    return p / name


def agy_path() -> Path:
    return Path(os.environ.get("COFFEE_AGY", str(Path.home() / ".local" / "bin" / "agy")))


def today() -> str:
    return dt.date.today().isoformat()


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "item"


# ---------- frontmatter ----------

_FM = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def split_frontmatter(text: str):
    m = _FM.match(text)
    if not m:
        return None, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = None
    return data, text[m.end():]


def read_page(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    return fm, body


def dump_frontmatter(data: dict) -> str:
    return "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000).strip() + "\n---\n"


def write_page(path: Path, fm: dict, body: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, dump_frontmatter(fm) + "\n" + body.strip("\n") + "\n")


def page_fm(title, summary, type_, tags=None, status="draft", **extra):
    d = today()
    fm = {
        "title": title,
        "date_created": d,
        "date_modified": d,
        "summary": summary,
        "tags": tags or [],
        "type": type_,
        "status": status,
    }
    fm.update(extra)
    return fm


def atomic_write(path: Path, text: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------- locking ----------

@contextlib.contextmanager
def file_lock(path: Path, blocking=True):
    """Advisory lock. Yields True if held, False if non-blocking and busy."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            held = True
        except BlockingIOError:
            held = False
        yield held
    finally:
        if fh and not fh.closed:
            with contextlib.suppress(Exception):
                fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()


# ---------- logs ----------

def append_log(v: Path, operation: str, title: str, note: str = ""):
    log = v / "wiki" / "log.md"
    entry = f"\n## [{today()}] {operation} | {title}\n"
    if note:
        entry += note.strip() + "\n"
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(entry)


def ensure_quota_log(v: Path) -> Path:
    path = v / "wiki" / "outputs" / "quota-log.md"
    if not path.exists():
        fm = page_fm("Quota log", "Every Gemini call: date, purpose, files, outcome.", "index", ["log"])
        write_page(path, fm, "# Quota log\n\n| When | Backend | Purpose | Files | Tokens | Outcome |\n|---|---|---|---|---|---|\n")
    return path


def quota_log(v: Path, purpose: str, files, outcome: str, tokens=None, backend="agy"):
    path = ensure_quota_log(v)
    row = f"| {now_iso()} | {backend} | {purpose} | {len(list(files))} | {tokens if tokens is not None else 'n/a'} | {outcome} |\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(row)


# ---------- problems (no silent failures) ----------

def note_problem(where: str, exc) -> None:
    """Record a handled problem so it is never silent: .coffee-work/problems.log (kept short) and stderr."""
    line = f"{now_iso()} {where}: {type(exc).__name__}: {exc}"
    try:
        p = vault() / ".coffee-work" / "problems.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        old = p.read_text(encoding="utf-8").splitlines()[-199:] if p.exists() else []
        p.write_text("\n".join(old + [line]) + "\n", encoding="utf-8")
    except OSError:
        pass
    print(f"[problem] {line}", file=sys.stderr)


# ---------- retry ----------

def retry(fn, max_retries=3, backoff=2.0, label="", retry_on=(Exception,), no_retry=()):
    """Exponential backoff. Exceptions in no_retry are raised immediately."""
    last = None
    for attempt in range(max_retries):
        try:
            return fn()
        except no_retry:
            raise
        except retry_on as e:
            last = e
            if attempt == max_retries - 1:
                break
            time.sleep(backoff * (2 ** attempt))
    raise last


# ---------- numbers ----------

_NUM = re.compile(r"-?\$?\(?\d[\d,]*\.?\d*\)?%?[kKmMbB]?")


def norm_number(tok: str):
    """'$1,234' -> '1234'. Returns None if it is not numeric."""
    t = str(tok).strip()
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")")) or t.startswith("$-")
    t = re.sub(r"[\$,()%\s-]", "", t)
    mult = 1
    if t and t[-1] in "kK":
        mult, t = 1000, t[:-1]
    elif t and t[-1] in "mM":
        mult, t = 1_000_000, t[:-1]
    elif t and t[-1] in "bB":
        mult, t = 1_000_000_000, t[:-1]
    try:
        val = float(t) * mult
    except ValueError:
        return None
    val = -val if neg else val
    return f"{val:.4f}".rstrip("0").rstrip(".")


def numbers_in(text: str):
    out = set()
    for m in _NUM.finditer(str(text)):
        n = norm_number(m.group(0))
        if n is not None:
            out.add(n)
            out.add(n.lstrip("-"))
    return out
