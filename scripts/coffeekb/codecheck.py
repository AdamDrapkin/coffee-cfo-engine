"""Code health checks, from the Vibe Persona rules: no silent failures, every external call has a timeout,
files stay small, no circular imports. Used by the test suite (hard rules) and by upkeep (drift warnings).

Hard rules (a violation fails the tests):
  1. A handler that catches Exception must record it (note_problem) or re-raise. Silence is never allowed.
  2. Every subprocess.run or Popen call has a timeout.
  3. The database path is not inside iCloud or another synced folder.
Drift (reported to the upkeep queue):
  3. A file over 400 lines. 4. A module-level import cycle. 5. A function over 80 lines.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent
MAX_FILE, MAX_FUNC = 400, 80


def _files():
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def silent_handlers() -> list:
    out = []
    for p in _files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"))
                if not broad:
                    continue
                body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
                uses_exc = bool(node.name) and any(isinstance(n, ast.Name) and n.id == node.name for b in node.body for n in ast.walk(b))
                if "note_problem" not in body and "Raise" not in body and not uses_exc:
                    out.append(f"{p.name}:{node.lineno}: broad except that neither records nor re-raises")
    return out


def calls_without_timeout() -> list:
    out = []
    for p in _files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("run", "Popen", "check_output") \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                if not any(k.arg == "timeout" for k in node.keywords) and not any(k.arg is None for k in node.keywords):
                    out.append(f"{p.name}:{node.lineno}: subprocess call without a timeout")
    return out


def big_files() -> list:
    return [f"{p.name}: {n} lines (limit {MAX_FILE})" for p in _files() if (n := len(p.read_text(encoding='utf-8').splitlines())) > MAX_FILE]


def long_functions() -> list:
    out = []
    for p in _files():
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno - node.lineno + 1 > MAX_FUNC:
                out.append(f"{p.name}:{node.name}: {node.end_lineno - node.lineno + 1} lines (limit {MAX_FUNC})")
    return out


def import_cycles() -> list:
    """Cycles among module-level `from . import x` / `from .x import y` statements (function-level imports are not counted)."""
    graph = {}
    for p in _files():
        deps = set()
        for node in ast.parse(p.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                if node.module:
                    deps.add(node.module.split(".")[0])
                else:
                    deps.update(a.name for a in node.names)
        graph[p.stem] = deps & {q.stem for q in _files()}
    cycles, seen = [], set()

    def walk(n, path):
        if n in path:
            cyc = path[path.index(n):] + [n]
            key = frozenset(cyc)
            if key not in seen:
                seen.add(key)
                cycles.append(" -> ".join(cyc))
            return
        for m in graph.get(n, ()):
            walk(m, path + [n])
    for n in graph:
        walk(n, [])
    return cycles


def db_location_problems() -> list:
    """The database must never live in a synced folder (Sprint 0 rule of the SQLite plan)."""
    from . import dbhealth
    return dbhealth.location_problems(dbhealth.db_path())


def drift() -> list:
    return big_files() + import_cycles() + long_functions()
