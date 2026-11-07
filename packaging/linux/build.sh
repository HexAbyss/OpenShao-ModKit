#!/usr/bin/env bash
# Builds the ModKit as one Linux executable (dist/modkit) inside manylinux_2_28, so it runs on any system with glibc 2.28 or later
# (about 2018 on) with no Python installed. Needs Docker. Run from anywhere. The result is dist/modkit.
set -e
cd "$(dirname "$0")/../.."
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" -v "$PWD":/w -w /w quay.io/pypa/manylinux_2_28_x86_64 bash -c '
  set -e
  dnf install -y -q python3.12 python3.12-pip python3.12-devel binutils > /dev/null
  PY=/usr/bin/python3.12
  mkdir -p /tmp/bc && g++ -std=c++17 -O2 -shared -fPIC -I native/bc native/bc/bcenc.cpp native/bc/rgbcx.cpp -o /tmp/bc/libbc.so  # outside the repository
  $PY -m pip install -q pyinstaller unicorn numpy pillow imgui-bundle
  # the Unicorn library is loaded by path, so PyInstaller does not see it: it is added by hand
  UNICORN=$(find / -name libunicorn.so.2 2>/dev/null | head -1)
  [ -n "$UNICORN" ] || { echo "libunicorn.so.2 not found"; exit 1; }
  rm -rf /tmp/pybuild
  BC_LIB=/tmp/bc/libbc.so UNICORN_LIB="$UNICORN" $PY -m PyInstaller --noconfirm --distpath dist --workpath /tmp/pybuild packaging/modkit.spec > /tmp/pybuild.log 2>&1 || { tail -30 /tmp/pybuild.log; exit 1; }
  chown -R "$HOST_UID:$HOST_GID" dist
  ls -la dist
'
