# Automating the ModKit from scripts

Everything the command line does is available as a Python package, `modkit`, for scripts, notebooks and AI tools that make or improve textures
in bulk. The graphical tool and the scripts use the same code, so a pack made either way is the same pack.

```
pip install -e .                        # in a clone of this repository; or: PYTHONPATH=src python script.py
```

The examples in [`examples/`](../examples) are complete scripts: `upscale_small_textures.py` (the whole flow), `edit_one_texture.py`, `inspect_pack.py`.

## The flow in code

```python
import modkit

modkit.extract('game.iso', 'textures')                  # 3,333 PNG and a manifest.json; about 3 minutes on six cores
folder = modkit.TextureFolder('textures')

for texture in folder.find(format='DXT5', max_width=128):
    image = folder.image(texture)                       # PIL RGBA
    folder.save(texture, improve(image))                # any size in the same proportion, both sides a multiple of 4

result = folder.compile('MyPack.ostp', info=dict(
    id='MyPack', name='My pack', version='1.0.0', authors=['You'], summary='One sentence.', min_recomp='0.4.1'),
    logo='logo.png', preload=[0x1234abcd5678ef90])
print(result.textures, result.verification.ok)
```

Scripts that call `extract`, `compile` or `TextureFolder.edited` start worker processes, so the script must be guarded by
`if __name__ == '__main__':`. Pass `workers=1` to stay in one process.

## Reference

| Name | What it does |
| --- | --- |
| `modkit.check_game(path)` | The files an ISO or game folder lacks (an empty list when complete). |
| `modkit.extract(game, folder, workers=None, limit=None, progress=None, cancel=None)` | Writes the PNG and `manifest.json`. `progress(done, total, textures)`; `cancel()` returning true stops it and leaves no manifest. Returns an `ExtractResult` (`textures`, `entries`, `stats`, `cancelled`, `seconds`). |
| `modkit.TextureFolder(path)` | A folder as `extract` leaves it. Iterating gives its `Texture` objects, by hash. |
| `.get(h)`, `h in folder`, `len(folder)` | A texture by hash (integer, 16 hexadecimal digits or a `Texture`); `KeyError` if absent. |
| `.find(format=None, min_width=0, max_width=None, min_height=0, max_height=None, where=None)` | Textures by original size, game format (`DXT5`, `A8R8G8B8`) and your own `where(texture)`. |
| `.image(t)`, `.array(t)` | The picture as a PIL RGBA image or a numpy `(height, width, 4)` array. |
| `.save(t, picture)` | Replaces the picture (PIL image or array). Written atomically. |
| `.is_edited(t)`, `.edited(workers=None)` | What differs from the extraction (one changed pixel counts), by the signature of the pixels in the manifest. |
| `.compile(out, info=None, logo=None, preload=None, workers=None, encoder=None, progress=None, cancel=None, require_manifest=True)` | Builds the `.ostp` from the edited pictures and verifies it before moving it into place. |
| `modkit.compile_folder(folder, out, ...)` | The same, for a folder path. Without `info`, it reads `pack.json`, `logo.png` and `preload.txt` from the folder. |
| `modkit.verify(path)` | A `Verification` (`ok`, `problems`, `info`, `textures`, `logo`). |
| `modkit.pack_entries(path)` | The textures a pack holds (hash, sizes, levels, format, alpha). |
| `modkit.pixel_signature(rgba)` | The signature the game's developer mode also uses. |

`Texture` has `hash`, `key` (16 hexadecimal digits), `file`, `format`, `width` and `height` (the game's original size), `places` (where it occurs in the
game's archive) and `signature`.

## Rules the tool enforces

- Both sides of a picture must be a multiple of 4, from 4 to 8192, in the proportion of the original. A picture that does not follow them stops
  `compile` with the reason and the file name, and nothing is written.
- Only edited pictures go in the pack. Without a usable `manifest.json` the tool refuses to guess (`require_manifest=False` says every picture is yours).
- Transparency decides the format: any pixel with alpha under 255 makes the texture BC3; otherwise BC1.
- Errors you can fix come as `ValueError` with the reason in words; a missing encoder library, when you ask for one by name, is a `RuntimeError`.
- The default encoder is rgbcx at level 18 (slow, best). `encoder='rgbcx:10'` is about ten times faster, for trying things.
