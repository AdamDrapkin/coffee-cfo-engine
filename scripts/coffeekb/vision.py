"""Fast, deterministic screen reading: macOS Vision text recognition plus star counting.

A small Swift program (scripts/native/ocr.swift) reads every image in parallel, about 0.15
seconds per screenshot, with no network and no AI model. Results are cached per file so the
background worker can read screenshots the moment they arrive and `coffee week` finds them ready.
"""
from __future__ import annotations

from .util import note_problem

import hashlib
import json
import re
import os
import subprocess
from pathlib import Path

from .gemini_client import work_root


class VisionError(Exception):
    pass


def _src() -> Path:
    return Path(__file__).resolve().parent.parent / "native" / "ocr.swift"


def binary() -> Path:
    return work_root() / "bin" / "ocr"


def ensure_binary() -> Path:
    """Compile the reader once (about 20 seconds) and reuse it."""
    b, src = binary(), _src()
    if b.exists() and b.stat().st_mtime >= src.stat().st_mtime:
        return b
    b.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["swiftc", "-O", str(src), "-o", str(b)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not b.exists():
        raise VisionError("Could not build the screen reader (needs Xcode command line tools: xcode-select --install). "
                          + (r.stderr or "")[-200:])
    return b


def cache_dir(v: Path) -> Path:
    d = v / ".coffee-work" / "ocr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(p: Path) -> str:
    st = p.stat()
    return hashlib.sha1(f"{p.name}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:20]


def cached(v: Path, p: Path):
    if not Path(p).exists():
        return None
    c = cache_dir(v) / f"{_key(p)}.json"
    if c.exists():
        try:
            return json.loads(c.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def read_files(v: Path, paths, use_cache=True, allow_run=True):
    """OCR every path (cache first). Returns {path: doc}. Missing docs stay out when allow_run is False."""
    docs, todo = {}, []
    for p in map(Path, paths):
        d = cached(v, p) if use_cache else None
        if d:
            docs[p] = d
        else:
            todo.append(p)
    if todo and allow_run:
        try:
            exe = ensure_binary()
            r = subprocess.run([str(exe), *map(str, todo)], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            # the chat's sandbox may not run the reader; the Mac worker pre-reads into the cache instead
            return docs if docs else (_ for _ in ()).throw(VisionError(f"The screen reader cannot run here ({e}). The Mac worker reads new screens on its own; wait a minute and try again."))
        if r.returncode != 0 and not r.stdout.strip():
            raise VisionError("The screen reader failed: " + (r.stderr or "")[-200:])
        for p, line in zip(todo, [ln for ln in r.stdout.splitlines() if ln.strip()]):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "error" in d:
                continue
            docs[p] = d
            (cache_dir(v) / f"{_key(p)}.json").write_text(line, encoding="utf-8")
    return docs


def _second_cache(v: Path, p: Path):
    return cache_dir(v) / f"{_key(p)}.fast.json"


def second_cached(v: Path, paths):
    out, todo = {}, []
    for p in map(Path, paths):
        c = _second_cache(v, p)
        if c.exists():
            try:
                out[p] = set(json.loads(c.read_text(encoding="utf-8")))
                continue
            except ValueError:
                pass
        todo.append(p)
    return out, todo


def second_read(v: Path, paths, allow_run=True):
    """Independent second reading with Vision's fast recognizer (never cached, never used for filing).
    Returns {path: set of numbers seen}. Used to catch a misread digit in the accurate pass."""
    if not paths:
        return {}
    out, todo = second_cached(v, paths)
    if not todo or not allow_run:
        return out
    exe = ensure_binary()
    env = dict(os.environ, OCR_LEVEL="fast")
    r = subprocess.run([str(exe), *map(str, todo)], capture_output=True, text=True, timeout=120, env=env)
    for p, line in zip(todo, [ln for ln in r.stdout.splitlines() if ln.strip()]):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        nums = {re.sub(r"[^\d.]", "", w) for l in d.get("lines", []) for w in re.findall(r"[-+$]?[\d,]+(?:\.\d+)?", l["t"])}
        out[p] = nums
        _second_cache(v, p).write_text(json.dumps(sorted(nums)), encoding="utf-8")
    return out


# ---- worker requests: the chat sandbox cannot run the reader, so it asks the Mac worker, which can ---------------

def _req_dir(v: Path) -> Path:
    d = v / ".coffee-work" / "ocr-requests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def request_worker_read(v: Path, paths, timeout: float = 45.0) -> dict:
    """Ask the worker to read these files and wait for the cache to fill. Returns {path: doc} for what arrived in time."""
    import time
    import uuid
    paths = [Path(p) for p in paths]
    if not paths:
        return {}
    (_req_dir(v) / f"{uuid.uuid4().hex}.json").write_text(json.dumps([str(p) for p in paths]), encoding="utf-8")
    deadline, got = time.time() + timeout, {}
    while time.time() < deadline:
        for p in paths:
            if p not in got:
                d = cached(v, p)
                if d:
                    got[p] = d
        if len(got) == len(paths):
            break
        time.sleep(0.5)
    return got


def serve_requests(v: Path) -> int:
    """Worker side: read what the chat asked for (and the second reading), then remove the request."""
    n = 0
    for f in sorted(_req_dir(v).glob("*.json")):
        try:
            paths = [Path(x) for x in json.loads(f.read_text(encoding="utf-8"))]
            paths = [p for p in paths if p.exists()]
            read_files(v, paths)
            second_read(v, paths)
            n += len(paths)
        except Exception as _e:
            note_problem(__name__, _e)
            pass
        finally:
            try:
                f.unlink()
            except OSError:
                pass
    return n
