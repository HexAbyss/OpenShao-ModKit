#!/usr/bin/env bash
# Builds the ModKit for Linux inside manylinux_2_28, so it runs on any system with glibc 2.28 or later (about 2018 on) with no Python installed.
# Needs Docker. Run from anywhere. Two results:
#   dist/modkit/            the program and its files: the command line (dist/modkit/modkit extract ...)
#   dist/OpenShao-ModKit    one file, the one to give to people: it carries that folder compressed, unpacks it once into
#                           ~/.local/share/OpenShao/ModKit, opens the window and shows a splash screen while it starts
set -e
cd "$(dirname "$0")/../.."
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" -v "$PWD":/w -w /w quay.io/pypa/manylinux_2_28_x86_64 bash -c '
  set -e
  dnf install -y -q python3.12 python3.12-pip python3.12-devel binutils libX11-devel libXfixes-devel > /dev/null
  PY=/usr/bin/python3.12
  mkdir -p /tmp/bc && g++ -std=c++17 -O2 -shared -fPIC -I native/bc native/bc/bcenc.cpp native/bc/rgbcx.cpp -o /tmp/bc/libbc.so  # outside the repository
  $PY -m pip install -q pyinstaller unicorn numpy pillow imgui-bundle
  # the Unicorn library is loaded by path, so PyInstaller does not see it: it is added by hand
  UNICORN=$(find / -name libunicorn.so.2 2>/dev/null | head -1)
  [ -n "$UNICORN" ] || { echo "libunicorn.so.2 not found"; exit 1; }
  [ -f dist/modkit ] && rm -f dist/modkit   # an earlier build made a single file here; now it is a folder
  rm -rf /tmp/pybuild
  BC_LIB=/tmp/bc/libbc.so UNICORN_LIB="$UNICORN" $PY -m PyInstaller --noconfirm --distpath dist --workpath /tmp/pybuild packaging/modkit.spec > /tmp/pybuild.log 2>&1 || { tail -30 /tmp/pybuild.log; exit 1; }
  # the launcher: its splash pictures, the ModKit folder compressed, and the program that carries both
  $PY packaging/linux/make_splash_assets.py /tmp/splash.bin
  $PY packaging/linux/tar_folder.py dist/modkit /tmp/modkit.tar.gz
  g++ -std=c++17 -O2 -pthread -static-libstdc++ -static-libgcc -DMODKIT_ASSETS="\"/tmp/splash.bin\"" native/launcher/modkit_launcher_linux.cpp -o /tmp/launcher -ldl
  strip /tmp/launcher
  $PY packaging/windows/embed_payload.py /tmp/launcher /tmp/modkit.tar.gz dist/OpenShao-ModKit
  chmod 755 dist/OpenShao-ModKit
  chown -R "$HOST_UID:$HOST_GID" dist
  ls -la dist dist/modkit | head -20
'
