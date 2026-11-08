#!/usr/bin/env bash
# Starts the interface on a virtual screen and checks it the way a person would: an extraction that runs on its own, a click on Cancel, a
# compilation of a small folder, the pages. Screenshots go to tests/gui/out/. Run `docker build` for both images first (see README.md).
# Needs dist/OpenShao-ModKit (packaging/linux/build.sh).   usage: smoke.sh <game.iso>
set -e
ISO="$(realpath "$1")"
cd "$(dirname "$0")/../.."
mkdir -p tests/gui/out
inside='
Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 &
sleep 1; export DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1
shot() { import -window root -crop 1040x640+0+0 /out/$NAME-$1.png; }
start() { $RUN gui "$@" > /tmp/gui.log 2>&1 & PID=$!; }
stop() { kill $PID 2>/dev/null; sleep 1; }
# 1. an extraction of the first 300 archive entries
start --game /iso/game.iso --out /tmp/done --auto-extract --limit 300; sleep 22; shot extract-done; stop
test -f /tmp/done/manifest.json && echo "$NAME: extraction finished, manifest written"
# 2. a full extraction, cancelled with a click on the Cancel button of the footer
start --game /iso/game.iso --out /tmp/cancel --auto-extract; sleep 9; shot extracting
xdotool mousemove 952 586 click 1; sleep 5; shot cancelled; stop
test ! -f /tmp/cancel/manifest.json && echo "$NAME: cancelled, no manifest"
# 3. the compilation of the folder the first run made, after doubling three pictures (edited with ImageMagick)
mogrify -resize 200% $(ls /tmp/done/*.png | head -3)
cat > /tmp/done/pack.json <<JSON
{"name": "Smoke", "id": "Smoke", "version": "1.0.0", "authors": ["test"], "summary": "smoke test"}
JSON
start --pictures /tmp/done --pack /tmp/pack.ostp --auto-compile --page Compile; sleep 8; shot compile; stop
test -f /tmp/pack.ostp && echo "$NAME: compiled a pack"
# 4. the pages
start --verify /tmp/pack.ostp; sleep 6; shot verify; stop
start --page About; sleep 5; shot about; stop
# 5. the launcher (only in the clean system, which has the executable): no command opens the window with a splash screen over it until it is up, and
# once the ModKit is unpacked it opens in about a second
if [ -n "$LAUNCHER" ]; then
    xcompmgr >/dev/null 2>&1 & sleep 1
    t0=$(date +%s.%N)
    $RUN --page About > /tmp/gui.log 2>&1 & PID=$!
    sleep 0.5; shot splash
    for i in $(seq 1 100); do [ -n "$(xdotool search --name "OpenShao ModKit" 2>/dev/null | head -1)" ] && break; sleep 0.1; done
    echo "$NAME: launcher opened the window after $(echo "$(date +%s.%N) - $t0" | bc) s"
    sleep 2; shot launched; stop
fi
'
docker run --rm -e RUN="python3 -m modkit" -e NAME=source -e PYTHONPATH=/src -v "$PWD/src":/src:ro -v "$ISO":/iso/game.iso:ro -v "$PWD/tests/gui/out":/out modkit-guitest bash -c "$inside"
docker run --rm -e RUN=/exe/OpenShao-ModKit -e LAUNCHER=1 -e NAME=executable -v "$PWD/dist":/exe:ro -v "$ISO":/iso/game.iso:ro -v "$PWD/tests/gui/out":/out modkit-clean bash -c "$inside"
