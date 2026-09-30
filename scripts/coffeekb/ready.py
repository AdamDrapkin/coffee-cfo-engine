"""`coffee inbox-ready`: wait until everything in inbox/ has finished syncing.

iCloud delivers files in stages: a placeholder (.name.icloud), then a partly downloaded
file, then the whole file. Reading too early gives a missing or truncated image. This
check says READY only when ALL of these hold:
- no iCloud placeholders remain (a download is requested for each)
- no file changed size during the last few polls
- every image is structurally complete (PNG ends with IEND, JPEG ends with FFD9)
- every video is readable by ffprobe (when ffprobe is installed)
- at least `expect` files are present (when the CEO said how many they uploaded)
- the set of files has stopped changing for `settle` seconds

Exit code 0 = READY. Exit code 3 = still waiting (run it again). It never guesses.
"""
from __future__ import annotations

from .util import note_problem

import shutil
import subprocess
import time
from pathlib import Path

from . import frames, inbox

STABLE_POLLS = 3
PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def _eligible(v: Path):
    """(real_files, placeholders) that matter: media and notes, not the tool's own paste files."""
    d = v / "inbox"
    real, ph = [], []
    if not d.exists():
        return real, ph
    for p in sorted(d.iterdir()):
        name = p.name
        if name.startswith(".") and name.endswith(".icloud"):
            ph.append(d / name[1:-len(".icloud")])
            continue
        if name.startswith(".") or not p.is_file() or name in inbox.IGNORE:
            continue
        ext = p.suffix.lower()
        if ext in inbox.IMAGES or ext in inbox.NOTES or ext in frames.VIDEO_EXT:
            real.append(p)
    return real, ph


def _complete(p: Path):
    """None if the file looks complete, otherwise a short reason."""
    try:
        size = p.stat().st_size
        if size == 0:
            return "empty so far"
        ext = p.suffix.lower()
        with open(p, "rb") as fh:
            if ext == ".png":
                fh.seek(max(0, size - 12))
                if fh.read() != PNG_END:
                    return "PNG not finished downloading"
            elif ext in (".jpg", ".jpeg"):
                fh.seek(max(0, size - 64))
                tail = fh.read().rstrip(b"\x00")
                if not tail.endswith(b"\xff\xd9"):
                    return "JPEG not finished downloading"
            else:
                fh.read(1)
        if ext in frames.VIDEO_EXT:
            probe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
            if Path(probe).exists():
                r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode != 0 or not r.stdout.strip():
                    return "video not readable yet"
    except OSError as e:
        return f"cannot read yet ({e.strerror or e})"
    return None


def _request_downloads(paths):
    for p in paths:
        try:
            subprocess.run(["brctl", "download", str(p)], capture_output=True, timeout=15)
        except Exception as _e:
            note_problem(__name__, _e)
            pass   # the background worker also requests downloads; this is best effort


def check(v: Path, expect: int | None = None, wait: float = 60.0, settle: float = 15.0,
          poll: float = 2.0, log=print):
    """Return (ready, message). Blocks up to `wait` seconds."""
    deadline = time.time() + wait
    last_set, last_change = None, 0.0
    stable = 0
    prev = None
    reasons = ["nothing checked yet"]
    while True:
        real, ph = _eligible(v)
        if ph:
            _request_downloads(ph)
        snap = tuple((p.name, p.stat().st_size) for p in real if p.exists())
        names = tuple(n for n, _ in snap)
        if names != last_set:
            last_set, last_change = names, max(last_change, time.time() if last_set is not None else 0.0)
        newest = max((p.stat().st_ctime for p in real if p.exists()), default=0.0)   # ctime = when it arrived on this Mac
        last_change = max(last_change, newest)
        stable = stable + 1 if snap == prev else 0
        prev = snap

        reasons = []
        if ph:
            reasons.append(f"{len(ph)} file(s) still syncing from iCloud: " + ", ".join(p.name for p in ph[:6]))
        for p in real:
            why = _complete(p)
            if why:
                reasons.append(f"{p.name}: {why}")
        if stable < STABLE_POLLS:
            reasons.append("files are still changing size")
        if expect is not None and len(real) < expect:
            hint = " (the phone has not finished uploading; keeping the Files app open on the iPhone helps)" if not real and not ph else ""
            reasons.append(f"expected {expect} files but only {len(real)} have arrived{hint}")
        if not real and not ph and expect is None:
            # No upload was announced and nothing is there: there is nothing to wait for.
            return True, "NOTHING TO WAIT FOR: the inbox is empty and no upload was announced. Continue with the CEO's question."
        if time.time() - last_change < settle:
            reasons.append("new files arrived a moment ago; letting the set settle")

        if not reasons:
            kinds = {"images": sum(p.suffix.lower() in inbox.IMAGES for p in real),
                     "videos": sum(p.suffix.lower() in frames.VIDEO_EXT for p in real),
                     "notes": sum(p.suffix.lower() in inbox.NOTES for p in real)}
            summary = ", ".join(f"{n} {k}" for k, n in kinds.items() if n)
            return True, f"READY: {len(real)} files fully synced ({summary}). Files: " + ", ".join(p.name for p in real)
        if time.time() >= deadline:
            seen = ", ".join(p.name for p in real) or "none"
            return False, ("WAITING (run this again, do not answer yet): " + "; ".join(reasons[:8])
                           + f". In the inbox right now: {seen}")
        time.sleep(poll)
