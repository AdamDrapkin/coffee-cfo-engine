#!/bin/sh
# One stable command for chat agents and sandboxes: runs the toolchain with the first working Python (3.9+).
# Usage: sh scripts/run.sh absorb --by antigravity
cd "$(dirname "$0")/.." || exit 1
export PYTHONDONTWRITEBYTECODE=1
for py in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    exec "$py" scripts/coffee.py "$@"
  fi
done
echo "No Python 3.9 or newer found." >&2
exit 1
