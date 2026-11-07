# The game's textures

What `modkit extract` gives you, and what is worth knowing before you choose what to edit. The numbers are from the USA/Europe release of the game
(the one OpenShao supports).

## What is in the game

| | |
| --- | --- |
| Distinct textures | **3,333** |
| Formats | **DXT5** (2,901, compressed, with an alpha channel) and **A8R8G8B8** (432, uncompressed, with an alpha channel) |
| Sizes | powers of two from 8 to 1,024 pixels on a side, none smaller than 4 |
| Most common sizes | 128 x 128 (1,075), 256 x 256 (683), 64 x 64 (479), 512 x 512 (454), 256 x 128 (227), 256 x 64 (107) |
| 512 pixels or more on a side | 575 textures |
| Pixels in all | 211 million (805 MiB as 32-bit pictures) |

A texture the game uses in several places appears **once** in the extraction. Most (2,176) occur in one place; others occur many times (136 occur ten
or more times), and these are usually worth more work, because the player sees them everywhere.

The game stores each texture once, without the smaller copies (mipmaps) a graphics card would use at a distance; the compiler makes those for your
picture.

## File names

```
0bac2904604d3ecc_DXT5_256x256.png
└──── hash ─────┘ └fmt┘ └─ size ─┘
```

- **hash**: 16 hexadecimal digits. It is a 64-bit hash of the bytes of the texture exactly as the game holds it. OpenShao hashes each texture the game
  asks for and swaps in your picture if the pack has that hash. Two textures with different bytes have different hashes, even if they look alike.
- **format**: `DXT5` or `A8R8G8B8`. Informative: you do not need to keep it in mind. A picture you edit is stored as BC1 or BC3 whatever the
  original format was.
- **size**: the **original** size. Your edited picture may be larger; the name keeps saying the original size. The compiler and the game use
  it to check the proportion.

**Never rename a file.** The hash is its identity; a renamed file is a different texture, or nothing.

## `manifest.json`

Written by `extract` and used by every tool afterwards. One record for each texture, keyed by its hash:

```json
"74c9a6076d45b2aa": {
  "file": "74c9a6076d45b2aa_DXT5_256x512.png",
  "fmt": "DXT5",
  "w": 256, "h": 512,
  "levels": 1,
  "linear": false,
  "at": [[144, 0]],
  "pixels": "98559578127d6267c9c953968114df99481129bf68f8412bc3028efd1837309b"
}
```

| Field | Meaning |
| --- | --- |
| `file` | the picture's file name |
| `fmt`, `w`, `h` | the game's format and original size |
| `levels` | how many mip levels the game stored for it |
| `linear` | whether the game stores it in a linear (not swizzled) layout; irrelevant to you |
| `at` | where the texture occurs in the game's archive: a list of `[archive entry, texture number in it]`. **The more entries, the more places use it.** Textures that share an archive entry usually belong to the same character, level or menu, which helps you edit a character's pictures together |
| `pixels` | the **signature** of the original pixels: SHA-256 of `"<width>x<height>:"` followed by the RGBA bytes, 8 bits a channel, top row first |

A picture counts as **edited** when the signature of its current pixels differs from `pixels`. That is why a single changed pixel counts and why
saving a picture again with the same pixels does not. If you add a picture of your own to the folder (a file named `<hash>_<format>_<w>x<h>.png`
with no record in the manifest) it counts as edited.

Do not delete or edit the manifest. If you lose it, extract again into a new folder and copy your edited pictures over the new ones.

## Finding what to edit

- **By size and format** with the window's folder or the Python package: `folder.find(max_width=128)`, `folder.find(format='A8R8G8B8')` (see
  [AUTOMATION.md](AUTOMATION.md)). The largest textures (512 and up) are the character and large surface textures where more detail shows.
- **By how often it is used**: `len(texture.places)` in the Python package, or the length of `at` in the manifest.
- **By looking at the game**: turn on Developer mode, edit a picture so it is obviously different (tint it red), and see where it appears. This is the
  surest way to learn what a texture is, and the game's log tells you how many pictures were found and used.
- **By neighbours**: textures that share an archive entry (the first number in `at`) belong together.

## About the 432 A8R8G8B8 textures

They are stored uncompressed in the game, so the extracted picture is exact. The 2,901 DXT5 textures were compressed with loss by the game's
makers, so their extracted pictures show the compression's block artefacts; an upscaler may amplify those, and cleaning them first helps.
