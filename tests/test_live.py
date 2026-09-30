"""Live checks against the real agy backend. Opt in with COFFEE_LIVE=1. Uses a SYNTHETIC image."""
import os

import pytest
from conftest import make_png

live = pytest.mark.skipif(os.environ.get("COFFEE_LIVE") != "1", reason="set COFFEE_LIVE=1 to run")


@live
def test_text_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFEE_WORK", str(tmp_path / "w"))
    from coffeekb.gemini_client import AgyBackend
    out = AgyBackend().analyze("Reply with the single word PONG.", [], ["You are terse."], "ask")
    assert "PONG" in out.upper()


@live
def test_image_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFEE_WORK", str(tmp_path / "w"))
    from coffeekb.gemini_client import AgyBackend
    png = tmp_path / "synthetic-dashboard.png"
    make_png(png)
    b = AgyBackend()
    out = b.analyze("This is a SYNTHETIC test image. List every label and number as 'label: value' lines.",
                    [("shot-1.png", png)], ["You read images accurately and never guess."], "ask")
    flat = out.replace(",", "")
    assert "123456" in flat and "48210" in flat and "7" in flat
