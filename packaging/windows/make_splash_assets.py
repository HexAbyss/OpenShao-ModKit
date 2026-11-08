"""Writes what the splash screen of the Windows launcher draws, into a folder: python make_splash_assets.py <folder>

enso.bin is the interface's own brush circle (art.enso_base): u32 width, u32 height, the RGBA pixels, then one byte per pixel with how far along
the stroke it was laid (0 to 255), which is what lets the launcher draw the circle in and out. The two fonts are copied beside it."""
import os
import shutil
import struct
import sys

import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
gui = os.path.join(here, '..', '..', 'src', 'modkit', 'gui')
sys.path.insert(0, os.path.join(here, '..', '..', 'src'))
from modkit.gui import art  # noqa: E402

RADIUS, WIDTH = 84, 17.0


def main(folder):
    os.makedirs(folder, exist_ok=True)
    rgba, size, t_map = art.enso_base(RADIUS, WIDTH, supersample=2)
    with open(os.path.join(folder, 'enso.bin'), 'wb') as f:
        f.write(struct.pack('<II', size, size))
        f.write(np.ascontiguousarray(rgba).tobytes())
        f.write(np.clip(t_map * 255.0 + 0.5, 0, 255).astype(np.uint8).tobytes())
    for name in ('HankenGrotesk-Regular.ttf', 'HankenGrotesk-SemiBold.ttf'):
        shutil.copyfile(os.path.join(gui, 'fonts', name), os.path.join(folder, name))


if __name__ == '__main__':
    main(sys.argv[1])
