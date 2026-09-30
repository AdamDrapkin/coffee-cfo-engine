"""`coffee relocate NEW_PATH`: move the vault (for example into the iCloud Obsidian folder).

Moves the folder, fixes the detached git worktree path, and reloads the launchd
agent if it was installed. The git directory stays outside the vault.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

from . import agent

GITDIR = Path.home() / ".coffee-inc-kb-git"
PATHFILE = Path.home() / ".coffee-inc-kb-path"
NEED_FDA = ("macOS is blocking access to that folder. In System Settings > Privacy & Security > "
            "Full Disk Access, switch on Terminal (and the Python program if you use the worker), "
            "then quit and reopen Terminal and try again.")


def fix_after_move(new: Path):
    """Point git, the launcher and (if loaded) the launchd agent at the new location."""
    subprocess.run(["git", "--git-dir", str(GITDIR), "config", "core.worktree", str(new)], check=True, timeout=30)
    PATHFILE.write_text(str(new) + "\n")


def relocate(v: Path, new: Path, yes=False, already_moved=False) -> int:
    if already_moved:
        if not (new / "scripts" / "coffee.py").exists():
            print(f"{new} does not contain the vault (no scripts/coffee.py).")
            return 1
        fix_after_move(new)
        if agent.loaded():
            os.environ["COFFEE_VAULT"] = str(new)
            agent.install(new, yes=True)
        print(f"Pointed everything at {new}.")
        return 0
    new = Path(new).expanduser()
    if new.resolve() == v.resolve():
        print("Already there.")
        return 0
    if (v / ".git").is_dir():
        print("Refusing: a .git directory is inside the vault.")
        return 1
    try:
        exists = new.exists()
        keep = {p.name for p in new.iterdir()} if exists and new.is_dir() else set()
    except PermissionError:
        print(NEED_FDA)
        return 1
    if exists:
        if not keep <= {".obsidian", ".DS_Store"}:
            print(f"Refusing: {new} exists and is not an empty Obsidian vault (found {sorted(keep)}).")
            return 1
        print(f"{new} holds only Obsidian's empty settings. It will be replaced (settings are recreated on open).")
    if not yes and input(f"Move {v} to {new}? [y/N] ").strip().lower() != "y":
        print("Not moved.")
        return 1
    try:
        if new.exists():
            shutil.rmtree(new)
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(v), str(new))
    except PermissionError:
        print(NEED_FDA)
        return 1
    fix_after_move(new)
    r = subprocess.run(["git", "-C", str(new), "status", "--short"], capture_output=True, text=True, timeout=60)
    print("git works from the new location." if r.returncode == 0 else f"git check failed: {r.stderr.strip()}")
    if agent.loaded():
        os.environ["COFFEE_VAULT"] = str(new)
        agent.install(new, yes=True)
    print(f"Moved to {new}. The coffee command now uses the new location.")
    return 0
