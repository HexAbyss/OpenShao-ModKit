#!/usr/bin/env bash
# Starts the interface on a virtual screen, extracts a few archive entries on its own, clicks Cancel on a full extraction, and takes
# screenshots into tests/gui/out/. Run `docker build` for both images first (see README.md). Needs dist/modkit (packaging/linux/build.sh).
set -e
ISO="$(realpath "$1")"
cd "$(dirname "$0")/../.."
mkdir -p tests/gui/out
inside='
Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 &
sleep 1; export DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1
$RUN gui --game /iso/game.iso --out /tmp/done --auto-extract --limit 300 > /tmp/a.log 2>&1 & PID=$!
sleep 22; import -window root /out/$NAME-done.png; kill $PID; sleep 1
$RUN gui --game /iso/game.iso --out /tmp/cancel --auto-extract > /tmp/b.log 2>&1 & PID=$!
sleep 8; xdotool mousemove 62 391 click 1; sleep 5; import -window root /out/$NAME-cancelled.png; kill $PID
test -f /tmp/done/manifest.json && echo "$NAME: extraction finished, manifest written"
test ! -f /tmp/cancel/manifest.json && echo "$NAME: cancelled, no manifest"
'
docker run --rm -e RUN="python3 -m modkit" -e NAME=source -e PYTHONPATH=/src -v "$PWD/src":/src:ro -v "$ISO":/iso/game.iso:ro -v "$PWD/tests/gui/out":/out modkit-guitest bash -c "$inside"
docker run --rm -e RUN=/exe/modkit -e NAME=executable -v "$PWD/dist":/exe:ro -v "$ISO":/iso/game.iso:ro -v "$PWD/tests/gui/out":/out modkit-clean bash -c "$inside"
