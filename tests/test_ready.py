"""inbox-ready: never says READY while files are still syncing. All data SYNTHETIC."""
import struct
import threading
import time
import zlib

from coffeekb import ready


def png_bytes():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"\x00" + b"\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def quick(kb, **kw):
    return ready.check(kb, wait=kw.pop("wait", 1.0), settle=kw.pop("settle", 0.0), poll=0.05, log=lambda *a: None, **kw)


def test_placeholder_blocks_ready(kb):
    (kb / "inbox" / ".IMG_1.PNG.icloud").write_bytes(b"plist")
    ok, msg = quick(kb)
    assert not ok and "still syncing" in msg and "IMG_1.PNG" in msg


def test_truncated_png_blocks_ready_and_full_png_passes(kb):
    data = png_bytes()
    (kb / "inbox" / "IMG_2.png").write_bytes(data[:-6])          # cut off mid-download
    ok, msg = quick(kb)
    assert not ok and "PNG not finished" in msg
    (kb / "inbox" / "IMG_2.png").write_bytes(data)
    ok, msg = quick(kb)
    assert ok and msg.startswith("READY: 1 files") and "IMG_2.png" in msg


def test_expected_count_waits_for_missing_files(kb):
    (kb / "inbox" / "a.png").write_bytes(png_bytes())
    (kb / "inbox" / "b.png").write_bytes(png_bytes())
    ok, msg = quick(kb, expect=3)
    assert not ok and "expected 3 files but only 2 have arrived" in msg and "In the inbox right now: a.png, b.png" in msg
    (kb / "inbox" / "c.png").write_bytes(png_bytes())
    ok, msg = quick(kb, expect=3)
    assert ok and "3 files" in msg


def test_growing_file_is_not_ready_until_it_stops(kb):
    p = kb / "inbox" / "grow.png"
    data = png_bytes()
    p.write_bytes(data)

    def keep_growing():
        for _ in range(12):
            with open(p, "ab") as fh:
                fh.write(b"\x00")
            time.sleep(0.04)
    t = threading.Thread(target=keep_growing)
    t.start()
    ok, _ = quick(kb, wait=0.4)
    t.join()
    assert not ok                       # appended bytes also break the PNG trailer, and the size kept changing


def test_empty_inbox_and_paste_files_do_not_count(kb):
    ok, msg = quick(kb)
    assert ok and msg.startswith("NOTHING TO WAIT FOR")   # a text-only question must never be blocked
    assert "do not answer" not in msg.lower()
    ok, msg = quick(kb, expect=1)
    assert not ok and "expected 1 files but only 0 have arrived" in msg   # an announced upload still waits


def test_zero_arrived_explains_that_the_phone_may_still_be_uploading(kb):
    ok, msg = quick(kb, expect=1)
    assert not ok and "phone has not finished uploading" in msg and "In the inbox right now: none" in msg
