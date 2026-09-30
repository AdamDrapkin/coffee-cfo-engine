"""Fixtures. Everything runs in a throwaway copy of the toolchain, never the real vault.
All fixture data is SYNTHETIC."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def kb(tmp_path, monkeypatch):
    v = tmp_path / "coffee-kb-test"
    v.mkdir()
    shutil.copytree(ROOT / "core", v / "core")
    (v / "wiki").mkdir()
    monkeypatch.setenv("COFFEE_VAULT", str(v))
    monkeypatch.setenv("COFFEE_WORK", str(tmp_path / "work"))
    monkeypatch.setenv("COFFEE_ALLOW_FAKE", "1")
    monkeypatch.setenv("COFFEE_BACKEND", "fake")
    from coffeekb import seed
    (v / "wiki" / "log.md").write_text("---\ntitle: Log\ndate_created: 2026-01-01\ndate_modified: 2026-01-01\nsummary: log\ntags: [log]\ntype: index\nstatus: draft\n---\n\n# Log\n")
    seed.seed(v)
    return v


def make_png(path: Path):
    """A SYNTHETIC dashboard image."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (900, 420), "white")
    d = ImageDraw.Draw(im)
    for i, t in enumerate(["SYNTHETIC TEST IMAGE", "Week 7", "Cash: $123,456", "Revenue: $48,210", "Debt: $0"]):
        d.text((30, 20 + i * 70), t, fill="black")
    im.save(path)


@pytest.fixture
def response_text():
    return (FIXTURES / "synthetic-response.md").read_text(encoding="utf-8")


@pytest.fixture
def fake_response(tmp_path, monkeypatch, response_text):
    p = tmp_path / "resp.md"
    p.write_text(response_text, encoding="utf-8")
    monkeypatch.setenv("COFFEE_FAKE_RESPONSE", str(p))
    return p
