# When something goes wrong

Messages are shown as the ModKit says them. Find yours, read the cause, do the fix.

## Extracting

| Message | Cause and fix |
| --- | --- |
| `the game is incomplete, it lacks: ...` | The image or folder has not got every file. A folder needs `default.xbe` and `GAMEDATA.WAD`, `.WAE`, `.WAF`, `.WAG`, `.WAH`, `.WAI`, `.WAJ`, `.WAK`. Use the disc image of the USA/Europe release. |
| `<file> does not exist` / `this is not an Xbox disc image` | The path is wrong, or the file is not an Xbox `.iso`. |
| `WARNING: N entries or textures could not be read` (exit code 2) | The extraction finished but some parts of the game could not be read, so the folder lacks some textures. Check the game image for damage, and extract again. |
| The window says it was cancelled | Nothing is wrong. Pictures already written stay; no `manifest.json` was written, so compile will refuse the folder. Extract again to finish. |

## Compiling

| Message | Cause and fix |
| --- | --- |
| `no picture was edited: every one of the N pictures has the pixels it was extracted with` | You have not changed any picture, or you saved them somewhere else. Edit the files **in the folder**. |
| `the folder has no manifest.json` / `manifest.json cannot be used (...)` | Without it the tool cannot tell what you edited, and the whole game would go in the pack. Put the extraction's `manifest.json` back, or, if every picture in the folder is yours, compile with `--no-manifest`. |
| `N pictures cannot be used: <file> is WxH, not in the proportion of the original ...` | The picture's proportion differs from the original's. Resize with the same proportion (same factor on both sides). |
| `<file> cannot be read as a picture` | The file is damaged or not a picture. Open and save it again, as a PNG. |
| `N edited pictures cannot be stored: ... not a multiple of 4 on both sides` | Both sides must be multiples of 4 (from 4 to 8192). A factor of 2, 4 or 8 on the original always works. |
| `pack information: the information lacks: ...` | A field of `pack.json` (or of the Compile page) is empty: `id`, `name`, `version`, `authors`, `summary` and `min_recomp` are required. |
| `id must be letters, digits, - or _ (1 to 80)` | Remove spaces and other characters from the id. |
| `version must be three numbers like 1.0.0` | Write `1.0.0`, not `1.0` or `v1`. |
| `<field> is longer than N characters` | Name 64, summary 200, description and credits 4,000, license 128, website 256. |
| `there is no pack.json in the folder` | Run `modkit init <folder>`, or use the Compile page, which writes it. |
| `the logo ... cannot be read; the pack has none` (a warning) | The pack was made without its logo. Use a PNG or JPEG up to 256 x 256. |
| `the pack does not verify, so it was not written` | The built file did not pass its own check, and the existing file was left alone. This should not happen: please report it with the messages shown. |
| `the encoder rgbcx:18 was asked for but the BC library is not built` | Only when running from the source: build the encoder with `native/bc/build.sh`, or leave the encoder out to use the default with a warning (Pillow's, which is worse in quality). The executable has the library inside. |

If a compile takes very long: the **Best** quality is slow on purpose (about 1.5 seconds a megapixel on one core, spread over your cores). Try
**Fast** (`--encoder rgbcx:10`) while you work and **Best** for the file you publish.

## In the game

| Symptom | Cause and fix |
| --- | --- |
| Nothing changed in Developer mode | Restart the game: it reads the folder when it starts. Check the launcher's Developer page says it found pictures, and that you edited the files **in that folder**. |
| Only some of my pictures show | Only pictures whose pixels differ from the extraction count. A texture the game draws in places you have not visited has not been drawn yet. Textures with their replacement still being read show the original for a few frames. |
| A menu shows the original for a moment, then changes | List the menu's textures in `preload.txt` (see the guide). |
| The picture the game shows when it starts stays the original | The game draws it for only a few frames before it stops to load. List it in `preload.txt`: `examples/preload-boot.txt` has its hash. |
| Textures flicker or load late, with a big pack | The pack is larger than the video memory budget, so pictures are being read again as the game draws them. Make fewer or smaller pictures, or let players use **Medium** quality. |
| My pack installs but changes nothing | The pack may have been made for another version of the game: its hashes do not match. Extract again from the game you play. |
| Two packs fight over a texture | The pack higher in the order on the Mods page wins. Players change the order with Up and Down. |
| A texture looks wrong after compiling but right in Developer mode | Look at its transparency. A picture with any semi-transparent pixel is stored as BC3; check the alpha around the edges. Compile with **Best**. |

## The window

| Symptom | Cause and fix |
| --- | --- |
| It does not open, or `Failed to create ... window` | The window needs OpenGL and the usual desktop libraries of your system. Use the command line (`modkit extract ...`) as a fallback; it needs nothing else. |
| **Choose** does nothing | The file dialog uses `zenity` or `kdialog`; install one of them, or type the paths on the command line. |

Still stuck? Open an issue with the message exactly as shown, what you did, and your system.
