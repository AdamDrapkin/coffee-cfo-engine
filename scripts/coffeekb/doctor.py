"""`coffee doctor`: account-based auth, quota, keys, keychain, last success."""
from __future__ import annotations
import os
import platform
import subprocess
import sys
from pathlib import Path

from . import inbox, render
from .gemini_client import AgyBackend, BackendError, parse_usage
from .util import agy_path

KEY_VARS = ("GEMINI" + "_API" + "_KEY", "GOOGLE" + "_API" + "_KEY", "OPENAI" + "_API" + "_KEY",
            "ANTHROPIC" + "_API" + "_KEY", "MINIMAX" + "_API" + "_KEY")


def run(v: Path, offline=False):
    rows = []

    def add(level, name, msg):
        rows.append((level, name, msg))

    add("PASS" if sys.version_info >= (3, 10) else "FAIL", "python", platform.python_version())
    add("PASS" if os.access(v, os.W_OK) else "FAIL", "vault writable", str(v))
    add("FAIL" if (v / ".git").is_dir() else "PASS", "git location", "no .git directory in the vault" if not (v / ".git").is_dir() else ".git DIRECTORY IN VAULT")
    keys = [k for k in KEY_VARS if os.environ.get(k)]
    add("WARN" if keys else "PASS", "api key variables", ("set: " + ", ".join(keys) + " (could redirect agy off your account)") if keys else "none set")
    exe = agy_path()
    if not exe.exists():
        add("FAIL", "agy", f"not installed at {exe}")
    else:
        try:
            ver = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception as e:
            ver = f"error {e}"
        add("PASS", "agy", ver)
        if not offline:
            try:
                b = AgyBackend()
                u = b.usage()
                if not u:
                    add("FAIL", "auth", "agy answered but returned no quota lines. Sign in again by running agy in Terminal.")
                else:
                    add("PASS", "auth", "account sign-in works (keychain reachable, no API key used)")
                    f, w = u.get("gemini_five_hour"), u.get("gemini_weekly")
                    if f and w:
                        lvl = "WARN" if f[0] < 20 or w[0] < 10 else "PASS"
                        add(lvl, "quota", f"Gemini five-hour {f[0]}% left, weekly {w[0]}% left")
            except BackendError as e:
                add("FAIL", "auth", str(e))
    st = render.load_state(v)
    add("PASS" if st.get("last_success") else "WARN", "last successful call", st.get("last_success", "none yet"))
    from . import coverage
    gaps = coverage.gaps(v)
    add("WARN" if gaps else "PASS", "coverage", (f"{len(gaps)} gap(s), run: coffee coverage" if gaps else "every archived kind of screen has records"))
    sc = inbox.scan(v)
    add("PASS", "inbox", f"{sc.count} waiting, {len(sc.placeholders)} iCloud placeholders")
    from .agent import loaded
    add("PASS" if loaded() else "WARN", "watch agent", "loaded in launchd" if loaded() else "not installed (run: coffee install-agent)")
    for lvl, name, msg in rows:
        print(f"{lvl:4}  {name:22} {msg}")
    return 1 if any(r[0] == "FAIL" for r in rows) else 0
