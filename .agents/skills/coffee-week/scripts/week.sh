#!/bin/sh
# One command for a whole week. Run from anywhere; finds the vault two folders above .agents/.
cd "$(dirname "$0")/../../../.." || exit 1
exec sh scripts/run.sh week "$@"
