# OpenShao ModKit

Extracts the textures of Mortal Kombat: Shaolin Monks from your own copy of the game and compiles edited pictures into a texture pack
(`.ostp`) that OpenShao installs from its Mods page. It reads the game; it stores and distributes nothing of it.

## The flow

1. **Extract** the game's textures to a folder of PNG pictures: `modkit extract <game> <folder>`.
   `<game>` is the disc image (`.iso`) or a folder with `default.xbe` and the `GAMEDATA.WAD` to `GAMEDATA.WAK` files.
   It takes about 3 minutes on six cores (about 14 on one), and writes 3,333 PNG named `<hash>_<format>_<width>x<height>.png`
   and a `manifest.json` that says where each texture occurs and holds the signature of its pixels.
2. **Edit** the pictures in the folder, in place, with any program. A picture may be larger than the original (2x, 4x), in the same proportion,
   with both sides a multiple of 4.
3. **Try them in the game** without building anything: turn on Developer on OpenShao's Files page and choose the folder. Only the pictures you
   changed count (a single changed pixel is enough). Restart the game to see a change.
4. **Compile** when they are ready: `modkit init <folder>` writes a `pack.json` to fill in (id, name, version, authors, summary,
   description, credits, license, website); put `logo.png` (up to 256 x 256) and `preload.txt` (the hashes drawn at once, those of the menus and of the first picture the game shows, one per line) beside it.
   Then `modkit compile <folder> <pack.ostp>`. Only the edited pictures go in, each with all its mip levels, as BC1 (no transparency)
   or BC3 (transparency), encoded with rgbcx at its highest level. It takes minutes, once, and the player never pays that time.
5. `modkit verify <pack.ostp>` checks the file against the format. Install the pack from OpenShao's Mods page with **Install from file**.

A picture that cannot be used (it does not open, a side is not a multiple of 4, or its proportion is not the original's) stops the build with the
reasons and writes nothing. So does a folder without a usable `manifest.json`, because then there is no way to tell what you edited and the whole
game would go in the pack; `--no-manifest` says that every picture in the folder is yours. The pack is built beside its destination and moved
into place only after it verifies, so a failed or cancelled build never replaces a good pack. A logo that cannot be read only drops the logo, with a
warning.

Scripts and AI tools can do the same from Python: see [docs/AUTOMATION.md](docs/AUTOMATION.md) and `examples/`.

## Commands

```
modkit extract <game> <out folder> [--workers N] [--limit N]
modkit check <game>
modkit init <texture folder>
modkit compile <texture folder> <out.ostp> [--workers N] [--encoder rgbcx:18|rgbcx:10|stb|pillow] [--no-manifest]
modkit verify <file.ostp>
```

`--encoder rgbcx:10` is about ten times faster than the default for a little less quality: for trying the tool. `OPENSHAO_BC_ENCODER` sets the
same.

## Install

**The executable (Linux).** `packaging/linux/build.sh` (needs Docker) builds `dist/modkit`, one file of about 40 MB that runs on any system with
glibc 2.28 or later, with no Python and nothing to install. It takes the commands above. With no command (double-click) it opens the graphical interface
(`modkit gui`): Extract, Compile (pack information, logo, quality), Verify and About pages, with a brush circle as the progress of a long job.

**The executables (Windows).** `packaging\windows\build.bat` (from an x64 Native Tools prompt for Visual Studio, with a Python that has PyInstaller, numpy,
Pillow, unicorn and imgui-bundle) builds two files in `dist`, which stay in the same folder: `modkit.exe` (about 45 MB, the commands above, with no
Python and nothing to install) and `OpenShao-ModKit.exe` (about 0.6 MB), which opens the window with no terminal and a splash screen while `modkit.exe`
starts. Double-click `OpenShao-ModKit.exe`; use `modkit.exe` from a terminal.

**From the source.** Python 3.9 or later with `numpy`, `Pillow` and `unicorn`, and the encoder library: `native/bc/build.sh` (a C++ compiler).
`pip install -e .` installs the `modkit` command (`pip install -e .[gui]` adds the interface, which needs `imgui-bundle` and OpenGL); without installing, `PYTHONPATH=src python -m modkit ...` does the same. Without the library the
default encoder falls back to Pillow's and says so (it makes visible errors in soft transparency); an encoder asked for by name (`--encoder`,
`OPENSHAO_BC_ENCODER`) is never swapped: the tool stops instead.

## Layout

```
src/modkit/
  cli.py            the command line
  gui/              the window (Dear ImGui): app.py (pages), art.py (palette and drawing), widgets.py, tasks.py (long jobs on a thread), fonts/
  xbox/             reading the game: disc image, executable, archive, the game's own decompressor, textures
  pack/             the .ostp format: writer (ostp.py) and the reader that checks a file (reader.py)
  textures/         extract, compile, the pixel signature, the BC encoder
native/bc/          the encoder library's C++ sources (rgbcx, stb_dxt) and their licenses
packaging/          the executable (linux/build.sh)
tests/              test_modkit.py, native/ (opens a pack with the game's own reader), gui/ (the window on a virtual screen)
docs/  examples/    the automation guide, and complete example scripts
```

## Tests

`python -m unittest tests.test_modkit` from the repository root. They build a small disc image, executable, archive and textures, so the game is
not needed. Two more checks run when their inputs exist: `OPENSHAO_TEST_ISO` points at the game's image to test against the real game, and the
OpenShao source (beside this repository, or `OPENSHAO_REPO`) with `g++` lets the test open the compiled pack with the game's own reader.

## Notes

- The decompression of the game's archive runs the game's own routine, found in its `default.xbe`, in the Unicorn CPU emulator.
- The encoder code is rgbcx by Richard Geldreich and stb_dxt by Sean Barrett, both public domain or MIT; their licenses are in `native/bc/`.
- Code that uses the package with several workers must be guarded by `if __name__ == '__main__':`, because the worker processes start by importing the main program.

## License

The ModKit is free software under the GNU General Public License, version 2 or later (see `LICENSE`), the same as OpenShao. The license does not
cover the original game's code, assets, names or artwork: the ModKit contains none of them and you use your own copy. The components it is built
with keep their own licenses, all compatible with the GPL: Dear ImGui and imgui-bundle (MIT), NumPy (BSD-3-Clause), Pillow (MIT-CMU), Unicorn Engine
(GPL-2.0), rgbcx and stb_dxt (public domain or MIT, in `native/bc/`) and Hanken Grotesk (SIL Open Font License 1.1, in `src/modkit/gui/fonts/`).
