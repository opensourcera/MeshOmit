#!/bin/sh
# MeshOmit launcher for Linux and macOS.
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
unset NO_COLOR
export COLORTERM=truecolor
exec python3 -X utf8 -m meshomit "$@"
