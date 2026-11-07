#!/usr/bin/env bash
# Builds libbc.so, the BC encoders (rgbcx and stb_dxt), into src/modkit/_native. Run it from anywhere.
# Windows: build bcenc.dll from the same files (MSVC: cl /O2 /LD /EHsc bcenc.cpp rgbcx.cpp /Fe:..\\..\\src\\modkit\\_native\\bcenc.dll).
# For a binary that runs on older systems, packaging/linux/build.sh builds its own copy inside manylinux_2_28.
set -e
cd "$(dirname "$0")"
g++ -std=c++17 -O2 -shared -fPIC -I. bcenc.cpp rgbcx.cpp -o ../../src/modkit/_native/libbc.so
echo "built $(cd ../../src/modkit/_native && pwd)/libbc.so"
