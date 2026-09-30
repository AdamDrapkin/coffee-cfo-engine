"""`coffee frames VIDEO`: turn a screen recording into one sharp frame per distinct screen.

Why: chat apps cap image attachments (5 in Antigravity), but the agent can read any
number of files from the vault. Record the screen, pause about a second on each
option, and this pulls out the frames.

How, with only ffmpeg (no Python image libraries):
1. ffmpeg samples the video at `fps` frames per second as small 192x384 grayscale.
2. Samples with no block-level change between them form a stable run (a screen held still).
3. One frame from the middle of each stable run is kept (never a motion-blurred one),
   and a run that looks the same as the previous kept screen is skipped.
4. Only those frames are re-extracted at full resolution as PNG.
Text-sized changes (a highlighted option, a different price) count as a different screen.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .util import slugify, vault

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".webm", ".mkv", ".avi", ".3gp"}
SIG_W, SIG_H = 192, 384   # signature size in pixels (portrait phone screens)
BLOCK = 8                 # 8 x 8 pixel blocks -> a 24 x 48 grid
CHANGE = 8.0              # a block whose brightness moves this much (of 255) means the screen changed
KEEP_DAYS = 1


class FramesError(Exception):
    pass


@dataclass
class FramesResult:
    folder: Path
    frames: list = field(default_factory=list)   # [(path, seconds)]
    sampled: int = 0
    capped: bool = False
    duration: float = 0.0


def find_ffmpeg() -> str:
    for cand in (shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if cand and Path(cand).exists():
            return cand
    raise FramesError("ffmpeg is not installed. Install it with: brew install ffmpeg")


def frames_root(v: Path) -> Path:
    p = v / ".coffee-work" / "frames"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _blocks(frame: bytes):
    """Mean brightness of every 8x8 block of a 192x384 gray frame."""
    out = []
    for by in range(SIG_H // BLOCK):
        rows = [frame[(by * BLOCK + r) * SIG_W:(by * BLOCK + r + 1) * SIG_W] for r in range(BLOCK)]
        for bx in range(SIG_W // BLOCK):
            x = bx * BLOCK
            out.append(sum(sum(row[x:x + BLOCK]) for row in rows) / (BLOCK * BLOCK))
    return out


def _changed(a, b) -> bool:
    """True if any block differs by CHANGE or more. Catches a different price or highlight,
    not just a different picture, and ignores video compression noise."""
    return any(abs(x - y) >= CHANGE for x, y in zip(a, b))


def select_stable(sigs, fps: float):
    """Indices of representative frames from a list of block signatures."""
    if not sigs:
        return []
    runs, start = [], 0
    for i in range(1, len(sigs)):
        if _changed(sigs[i - 1], sigs[i]):
            runs.append((start, i - 1))
            start = i
    runs.append((start, len(sigs) - 1))

    keep, last = [], None
    for a, b in runs:
        if b - a < 1 and len(runs) > 1:
            continue                      # one sample only: motion or a transition, not a held screen
        mid = (a + b) // 2
        if last is not None and not _changed(sigs[last], sigs[mid]):
            continue                      # same screen as the last kept one
        keep.append(mid)
        last = mid
    return keep


def _sample(ffmpeg: str, video: Path, fps: float):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
           "-vf", f"fps={fps},scale={SIG_W}:{SIG_H}:flags=area,format=gray",
           "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=900)
    if r.returncode != 0:
        raise FramesError("ffmpeg could not read that video: " + r.stderr.decode(errors="replace").strip()[-200:])
    size = SIG_W * SIG_H
    data = r.stdout
    return [data[i:i + size] for i in range(0, len(data) - size + 1, size)]


def videos_dir(v: Path) -> Path:
    p = v / ".coffee-work" / "videos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def prune_videos(v: Path, days: int = 14) -> int:
    """Reviewed videos are kept briefly in case a screen needs a second look, then deleted."""
    d = v / ".coffee-work" / "videos"
    if not d.exists():
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for p in d.iterdir():
        if p.is_file() and p.stat().st_mtime < cutoff:
            p.unlink()
            n += 1
    return n


def cleanup(v: Path, days: int = KEEP_DAYS):
    """Delete extracted frame folders older than `days`. Frames are scratch, never records."""
    prune_videos(v)
    root = v / ".coffee-work" / "frames"
    if not root.exists():
        return 0
    n = 0
    cutoff = time.time() - days * 86400
    for d in root.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n


def extract(v: Path, video: Path, fps: float = 2.0, max_frames: int = 80) -> FramesResult:
    video = Path(video)
    if not video.is_file():
        raise FramesError(f"{video} was not found.")
    if video.suffix.lower() not in VIDEO_EXT:
        raise FramesError("Give me a video file (.mov, .mp4, .m4v, .webm, .mkv, .avi or .3gp).")
    ffmpeg = find_ffmpeg()
    cleanup(v)
    out = frames_root(v) / slugify(video.stem)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    samples = _sample(ffmpeg, video, fps)
    if not samples:
        raise FramesError("The video has no readable frames.")
    sigs = [_blocks(s) for s in samples]
    keep = select_stable(sigs, fps)
    capped = False
    if len(keep) > max_frames:
        step = len(keep) / max_frames
        keep = [keep[int(i * step)] for i in range(max_frames)]
        capped = True

    res = FramesResult(folder=out, sampled=len(samples), capped=capped, duration=len(samples) / fps)
    for n, idx in enumerate(keep, 1):
        t = idx / fps
        dest = out / f"frame-{n:03d}-{t:06.1f}s.png"
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
                            "-frames:v", "1", str(dest)], capture_output=True, timeout=120)
        if r.returncode != 0 or not dest.exists():
            raise FramesError(f"Could not pull the frame at {t:.1f}s.")
        res.frames.append((dest, t))

    lines = [f"# Frames from {video.name}", "",
             f"{len(res.frames)} distinct screens from {res.duration:.0f} s of video (sampled {fps:g} per second).", ""]
    lines += [f"- {p.name}  (t={t:.1f}s)" for p, t in res.frames]
    (out / "manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return res
