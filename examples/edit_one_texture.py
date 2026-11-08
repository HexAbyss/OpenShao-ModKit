"""Edits one texture of an extracted folder and shows what the tool sees.

    python examples/edit_one_texture.py <texture folder> <hash, 16 hexadecimal digits>

The picture is tinted red; then open OpenShao's Developer page on this folder to see it in the game."""
import sys

import modkit


def main(path, key):
    folder = modkit.TextureFolder(path)
    texture = folder.get(key)
    print('%s: %s %dx%d, occurs %d times in the game' % (texture.key, texture.format, texture.width, texture.height, len(texture.places)))
    pixels = folder.array(texture).copy()
    pixels[..., 1:3] //= 2                           # less green and blue
    folder.save(texture, pixels)
    print('edited now:', folder.is_edited(texture))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
