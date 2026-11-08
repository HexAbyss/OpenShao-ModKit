"""Draws the splash screen of the Windows executable (packaging/windows/splash.png) from the application icon and the interface's font and
colors: python make_splash.py"""
import os

from PIL import Image, ImageDraw, ImageFont

here = os.path.dirname(os.path.abspath(__file__))
gui = os.path.join(here, '..', '..', 'src', 'modkit', 'gui')
W, H = 460, 200
image = Image.new('RGB', (W, H), (0x25, 0x28, 0x2C))
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, W - 1, H - 1), outline=(0x3A, 0x3E, 0x44))
icon = Image.open(os.path.join(gui, 'app.ico'))
icon.size = (128, 128)
icon = icon.convert('RGBA').resize((96, 96), Image.LANCZOS)
image.paste(icon, (36, (H - 96) // 2), icon)
title = ImageFont.truetype(os.path.join(gui, 'fonts', 'HankenGrotesk-SemiBold.ttf'), 30)
small = ImageFont.truetype(os.path.join(gui, 'fonts', 'HankenGrotesk-Regular.ttf'), 18)
draw.text((156, 62), 'OpenShao ModKit', font=title, fill=(0xEC, 0xE5, 0xD6))
draw.text((156, 108), 'Starting...', font=small, fill=(0xA9, 0xA4, 0x98))
image.save(os.path.join(here, 'splash.png'))
