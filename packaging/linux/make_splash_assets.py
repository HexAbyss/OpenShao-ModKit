"""Writes what the splash screen of the Linux launcher draws, into one file: python make_splash_assets.py <splash.bin>

The launcher (native/launcher/modkit_launcher_linux.cpp) has no font or image library, so it draws from pictures made here, at twice the size of the
splash's logical pixels. Layout of the file, little-endian:
    "MKSPLSH1"
    ring:  u32 width, u32 height, the RGBA pixels, then one byte per pixel with how far along the stroke it was laid (0 to 255)
    three texts (the name, "Starting", and one dot): u32 width, u32 height, i32 pad, f32 advance, the RGBA pixels. `pad` is the margin around the
           text that holds its soft shadow, and `advance` the width of the text itself.
The ring is the interface's own brush circle (art.enso_base); the texts use the interface's typeface."""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

here = os.path.dirname(os.path.abspath(__file__))
gui = os.path.join(here, '..', '..', 'src', 'modkit', 'gui')
sys.path.insert(0, os.path.join(here, '..', '..', 'src'))
from modkit.gui import art  # noqa: E402

SCALE = 2                       # the launcher composes the splash at twice its logical size
RING_RADIUS, RING_WIDTH = 165, 33.5   # 0.98 of the interface's 84 and 17, at twice the size
PAD = 14


def text_bitmap(text, font_file, size, color):
    font = ImageFont.truetype(os.path.join(gui, 'fonts', font_file), size)
    advance = font.getlength(text)
    ascent, descent = font.getmetrics()
    width, height = int(advance) + 2 * PAD + 2, ascent + descent + 2 * PAD
    mask = Image.new('L', (width, height), 0)
    ImageDraw.Draw(mask).text((PAD, PAD), text, font=font, fill=255)
    # a soft dark edge keeps the light text readable on any desktop
    shadow = Image.new('L', (width, height), 0)
    ImageDraw.Draw(shadow).text((PAD, PAD + 2), text, font=font, fill=255)
    shadow = shadow.filter(ImageFilter.GaussianBlur(2.2)).point(lambda v: int(v * 0.5))
    base = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    base.paste(Image.new('RGBA', (width, height), (0, 0, 0, 255)), (0, 0), shadow)
    base.alpha_composite(Image.merge('RGBA', [Image.new('L', (width, height), c) for c in color] + [mask]))
    return width, height, advance, np.asarray(base)


def main(out):
    rgba, size, t_map = art.enso_base(RING_RADIUS, RING_WIDTH, supersample=2)
    with open(out, 'wb') as f:
        f.write(b'MKSPLSH1')
        f.write(struct.pack('<II', size, size))
        f.write(np.ascontiguousarray(rgba).tobytes())
        f.write(np.clip(t_map * 255.0 + 0.5, 0, 255).astype(np.uint8).tobytes())
        for text, file, px, color in (('OpenShao ModKit', 'HankenGrotesk-SemiBold.ttf', 28 * SCALE, (0xEC, 0xE5, 0xD6)),
                                      ('Starting', 'HankenGrotesk-Regular.ttf', 20 * SCALE, (0xA9, 0xA4, 0x98)),
                                      ('.', 'HankenGrotesk-Regular.ttf', 20 * SCALE, (0xA9, 0xA4, 0x98))):
            w, h, advance, pixels = text_bitmap(text, file, px, color)
            f.write(struct.pack('<IIif', w, h, PAD, advance))
            f.write(np.ascontiguousarray(pixels).tobytes())


if __name__ == '__main__':
    main(sys.argv[1])
