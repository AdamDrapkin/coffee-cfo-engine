"""Frame extraction on a SYNTHETIC screen recording built with ffmpeg."""
import random
import shutil
import subprocess

import pytest

from coffeekb import frames

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def screen(text, box=None):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=28)   # phone-UI sized text, not a 6 px default
    im = Image.new("RGB", (390, 844), "white")
    d = ImageDraw.Draw(im)
    d.text((30, 60), "SYNTHETIC SCREEN", fill="black", font=font)
    for i, line in enumerate(text):
        d.text((30, 140 + 60 * i), line, fill="black", font=font)
    if box:
        d.rectangle(box, fill="black")
    return im


def noise(seed):
    from PIL import Image
    random.seed(seed)
    im = Image.new("RGB", (390, 844))
    im.putdata([(random.randint(0, 255),) * 3 for _ in range(390 * 844)])
    return im


def make_video(path, tmp):
    """4 distinct screens, each held 1.5 s at 10 fps, separated by 2 noisy transition frames."""
    seq = []
    screens = [screen(["Exterior 1", "Cost 12000"]),
               screen(["Exterior 2", "Cost 18000"]),
               screen(["Exterior 2", "Cost 18000"], box=(20, 300, 200, 360)),   # only a highlight changed
               screen(["Interior 1", "Cost 9000"])]
    for n, s in enumerate(screens):
        seq += [s] * 15 + [noise(n), noise(n + 100)]
    for i, im in enumerate(seq):
        im.save(tmp / f"f{i:04d}.png")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "10", "-i", str(tmp / "f%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_one_frame_per_distinct_screen(kb, tmp_path):
    video = tmp_path / "RPReplay_Final.mov"
    seqdir = tmp_path / "seq"
    seqdir.mkdir()
    make_video(tmp_path / "v.mp4", seqdir)
    shutil.move(tmp_path / "v.mp4", video)
    r = frames.extract(kb, video)
    assert len(r.frames) == 4, [p.name for p, _ in r.frames]        # no blur frames, no duplicates, highlight change kept
    assert all(p.exists() and p.stat().st_size > 1000 for p, _ in r.frames)
    assert (r.folder / "manifest.md").exists()
    assert str(r.folder).startswith(str(kb / ".coffee-work" / "frames"))


def test_cap_and_errors(kb, tmp_path):
    with pytest.raises(frames.FramesError):
        frames.extract(kb, tmp_path / "missing.mov")
    bad = tmp_path / "x.txt"
    bad.write_text("nope")
    with pytest.raises(frames.FramesError):
        frames.extract(kb, bad)
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    with pytest.raises(frames.FramesError):
        frames.extract(kb, junk)


def test_select_stable_ignores_single_sample_transitions():
    still_a = [10.0] * 64
    still_b = [200.0] * 64
    blur = [100.0] * 64
    sigs = [still_a] * 4 + [blur] + [still_b] * 4 + [still_a] * 2
    assert frames.select_stable(sigs, 2.0) == [1, 6, 9]   # A, B, then A again (different from B)
