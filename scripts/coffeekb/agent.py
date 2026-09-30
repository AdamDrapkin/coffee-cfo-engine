"""`coffee install-agent`: keep `coffee watch` running under launchd."""
from __future__ import annotations
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.coffeeinc.watch"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / "Library" / "Logs" / "coffee-inc-kb.log"


def build(v: Path) -> bytes:
    passthru = {k: os.environ[k] for k in ("COFFEE_WORK", "COFFEE_QUIET", "COFFEE_POLL", "COFFEE_SYNC_ORIGIN", "COFFEE_AUTO_INGEST") if k in os.environ}
    d = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(v / "scripts" / "coffee.py"), "watch"],
        "EnvironmentVariables": {
            "COFFEE_VAULT": str(v),
            "HOME": str(Path.home()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
            **passthru,
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    return plistlib.dumps(d)


def _domain():
    return f"gui/{os.getuid()}"


def install(v: Path, yes=False):
    xml = build(v).decode()
    print(f"Will write {PLIST} and load it with launchctl:\n\n{xml}")
    if not yes:
        if input("Load this agent? [y/N] ").strip().lower() != "y":
            print("Not loaded.")
            return 1
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(build(v))
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True, timeout=30)
    r = subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST)], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print("launchctl failed:", (r.stderr or r.stdout).strip())
        return 1
    print("Loaded. It restarts after reboot. Log:", LOG)
    return 0


def uninstall():
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True, timeout=30)
    if PLIST.exists():
        PLIST.unlink()
    print("Agent removed.")
    return 0


def loaded() -> bool:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=30)
    return LABEL in r.stdout
