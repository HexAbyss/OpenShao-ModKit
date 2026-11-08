"""Makes a pack that doubles every small texture of the game with a plain resize, to show the whole flow from a script.

    python examples/upscale_small_textures.py <game .iso or folder> <work folder> <out.ostp>

Replace the resize line with anything: a model, a filter, hand-made pictures. The rest stays the same."""
import sys

import modkit


def main(game, work, out):
    missing = modkit.check_game(game)
    if missing:
        sys.exit('the game is incomplete, it lacks: ' + ', '.join(missing))
    modkit.extract(game, work)                       # 3 minutes on six cores; skip it when the folder already exists
    folder = modkit.TextureFolder(work)
    for texture in folder.find(format='DXT5', max_width=128, max_height=128):
        image = folder.image(texture)
        folder.save(texture, image.resize((image.width * 2, image.height * 2)))   # <- your improvement goes here
    result = folder.compile(out, info=dict(
        id='SmallTexturesX2', name='Small textures x2', version='1.0.0', authors=['You'], summary='Doubles the small textures.',
        min_recomp='0.4.1'), encoder='rgbcx:10')    # rgbcx:10 is fast, for trying; leave the encoder out for the best quality
    print('%d textures, %.1f MiB, verified: %s' % (result.textures, result.size / 1048576, result.verification.ok))


if __name__ == '__main__':  # needed: extraction and compilation start worker processes that import this file
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
