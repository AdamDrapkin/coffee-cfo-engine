"""Inbox scanning and image preparation.

Only images (png, jpg, jpeg, heic) and .md/.txt notes count. iCloud
placeholders (.name.icloud) are skipped and a download is requested. Files whose
size or mtime is still changing are reported as unstable.
"""
from __future__ import annotations
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .gemini_client import work_root
from .util import note_problem, split_frontmatter

IMAGES = {".png", ".jpg", ".jpeg", ".heic"}
NOTES = {".md", ".txt"}
IGNORE = {"_new-note-template.md", "answer-paste.md", "research-paste.md", "gem-paste.md", "analysis-paste.md", "review-paste.md"}
TEMPLATE_PROMPT = "Type: location choice / weekly close / competitor / anything"
MAX_SIDE = 3000  # iPhone screenshots stay native; only huge images shrink


@dataclass
class Scan:
    images: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    placeholders: list = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)  # path -> (size, mtime_ns)

    @property
    def count(self) -> int:
        return len(self.images) + len(self.notes)


def note_text(path: Path) -> str:
    """Typed context from a note, without frontmatter or the empty template prompt."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    _, body = split_frontmatter(raw)
    lines = [ln for ln in body.splitlines() if ln.strip() and ln.strip() != TEMPLATE_PROMPT]
    return "\n".join(lines).strip()


def request_download(path: Path):
    try:
        subprocess.run(["brctl", "download", str(path)], capture_output=True, timeout=20)
    except Exception as _e:
        note_problem(__name__, _e)
        pass


def scan(v: Path) -> Scan:
    s = Scan()
    inbox = v / "inbox"
    if not inbox.exists():
        return s
    for p in sorted(inbox.iterdir()):
        name = p.name
        if name.startswith(".") and name.endswith(".icloud"):
            real = inbox / name[1:-len(".icloud")]
            s.placeholders.append(real)
            request_download(real)
            continue
        if name.startswith(".") or name in IGNORE or not p.is_file():
            continue
        ext = p.suffix.lower()
        try:
            st = p.stat()
        except OSError:
            continue
        if ext in IMAGES:
            s.images.append(p)
        elif ext in NOTES:
            if not note_text(p):
                continue
            s.notes.append(p)
        else:
            continue
        s.snapshot[str(p)] = (st.st_size, st.st_mtime_ns)
    return s


def prepare_images(paths, dest: Path | None = None):
    """Convert HEIC to PNG with macOS sips, shrink only very large images.

    Returns [(alias, prepared_path, original_path)] with aliases shot-1.png...
    """
    from PIL import Image
    dest = dest or Path(tempfile.mkdtemp(prefix="prep-", dir=work_root()))
    out = []
    for i, src in enumerate(paths, 1):
        src = Path(src)
        work = src
        if src.suffix.lower() == ".heic":
            work = dest / f"conv-{i}.png"
            r = subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(work)],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not work.exists():
                raise RuntimeError(f"Could not convert {src.name} (HEIC). Send it again as a normal screenshot.")
        with Image.open(work) as im:
            im = im.convert("RGB")
            w, h = im.size
            if max(w, h) > MAX_SIDE:
                scale = MAX_SIDE / max(w, h)
                im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
            alias = f"shot-{i}.png"
            im.save(dest / alias, "PNG")
        out.append((alias, dest / alias, src))
    return out


def is_stable(prev: dict, cur: dict) -> bool:
    return prev == cur and bool(cur)
