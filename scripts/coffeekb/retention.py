"""Screenshot retention: originals are kept for a set number of days, then deleted.

Every value on a screen is already in the ledger and the full text of every screen is kept in raw/ocr/screens/, so the
images are only a short-term safety copy. An image is deleted only when it is older than KEEP_DAYS and its text is archived.
"""
from __future__ import annotations

import time
from pathlib import Path

from .util import note_problem

KEEP_DAYS = 3
EXT = (".png", ".jpg", ".jpeg", ".heic", ".heif")


def purge_screenshots(v: Path, days: int = KEEP_DAYS, now: float = 0.0) -> int:
    """Delete archived screenshots older than `days` whose text is archived. Returns how many were deleted."""
    shots, text = v / "raw" / "screenshots", v / "raw" / "ocr" / "screens"
    if not shots.exists():
        return 0
    cutoff = (now or time.time()) - days * 86400
    n = 0
    for p in shots.iterdir():
        try:
            if p.suffix.lower() in EXT and p.stat().st_mtime < cutoff and (text / (p.name + ".txt")).exists():
                p.unlink()
                n += 1
        except OSError as e:
            note_problem(__name__, e)
    return n
