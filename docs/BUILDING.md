# Building the ModKit

## From the source

Python 3.9 or later with `numpy`, `Pillow` and `unicorn`, and the encoder library, built with `native/bc/build.sh` (a C++ compiler).
`pip install -e .` installs the `modkit` command. `pip install -e .[gui]` adds the window, which needs `imgui-bundle` and OpenGL. Without installing,
`PYTHONPATH=src python -m modkit ...` runs the same.

Without the encoder library the default encoder falls back to Pillow's and says so. Pillow makes visible errors in soft transparency. An encoder requested by
name (`--encoder`, `OPENSHAO_BC_ENCODER`) is never replaced: the tool stops instead.

Code that uses the package with several workers must be guarded by `if __name__ == '__main__':`, because the worker processes start by importing the main program.

## The executables

Each system builds two things: the folder `dist/modkit` (the command line) and the file `dist/OpenShao-ModKit` (`.exe` on Windows), which carries that folder
compressed, unpacks it once and opens the window with a splash screen. The splash screen is shown until the window signals that it is up: through a named event
(`MODKIT_READY`) on Windows and through a pipe (`MODKIT_READY_FD`) on Linux.

**Linux.** `packaging/linux/build.sh` needs Docker and builds inside manylinux_2_28, so the result runs on glibc 2.28 or later.
The launcher (`native/launcher/modkit_launcher_linux.cpp`) is C++17 with no library besides glibc: Xlib, Xfixes and RandR are loaded when it starts, so a
system without them still runs the commands. The payload is a tar.gz of the folder, verified against its SHA-256 and unpacked with the system's `tar` into
`$XDG_DATA_HOME/OpenShao/ModKit/<hash>` (`~/.local/share` by default); older versions are removed. The splash screen is a 32-bit X11 window, so it needs a
compositing window manager; without one, or without X11, the window opens without it. It is centred on the primary monitor.

**Windows.** `packaging\windows\build.bat` runs from an x64 Native Tools prompt for Visual Studio, with a Python that has PyInstaller, numpy, Pillow, unicorn
and imgui-bundle. The launcher (`native/launcher/modkit_launcher.cpp`) draws its splash screen with GDI+ and unpacks the payload (a zip) with the `tar.exe`
that comes with Windows 10 and later, into `%LOCALAPPDATA%\OpenShao\ModKit\<hash>`.

Both launchers carry the payload after the program, in the same layout: the payload, its SHA-256 (32 bytes), its size (8 bytes, little-endian) and the
marker `MKPAYLD1` (`packaging/windows/embed_payload.py`). A build with no payload runs a `modkit` folder beside it.

**The packages.** `packaging/make_release.py` packs the program with `packaging/release/readme.txt` and `packaging/release/licenses/` into what is published:
`make_release.py linux dist/OpenShao-ModKit OpenShao-ModKit-Linux-x64.tar.gz` makes a tar.gz whose folder `OpenShao-ModKit/` holds the program (with its permission to run),
the readme and the licenses; `make_release.py windows dist\OpenShao-ModKit.exe OpenShao-ModKit-Windows-x64.zip` makes a zip with the same three. A folder is the unit
that people extract, so the program starts from a folder of its own on any desktop. Keep `licenses/THIRD_PARTY.txt` in step with the libraries the build carries.

## Layout

```
src/modkit/
  cli.py            the command line
  gui/              the window (Dear ImGui): app.py (pages), art.py (palette and drawing), widgets.py, tasks.py (long jobs on a thread), fonts/
  xbox/             reading the game: disc image, executable, archive, the game's own decompressor, textures
  pack/             the .ostp format: the writer (ostp.py) and the reader that checks a file (reader.py)
  textures/         extract, compile, the pixel signature, the BC encoder
native/bc/          the encoder library's C++ sources (rgbcx, stb_dxt) and their licenses
native/launcher/    the launchers of the executables
packaging/          the builds of the executables (linux/, windows/) and the PyInstaller spec
tests/              test_modkit.py, native/ (opens a pack with the game's own reader), gui/ (the window on a virtual screen)
docs/  examples/    the guides and complete example scripts
```

## Tests

`python -m unittest discover -s tests` from the repository root. The tests build a small disc image, executable, archive and textures, so the game is not
needed. Two more checks run when their inputs exist: `OPENSHAO_TEST_ISO` points at the game's image to test against the real game, and the OpenShao source
(beside this repository, or at `OPENSHAO_REPO`) with `g++` lets a test open the compiled pack with the game's own reader.

`tests/gui/` drives the window with clicks on a virtual screen, from the source and from the executable (see its README).

## Notes

- The decompression of the game's archive runs the game's own routine, found in the user's `default.xbe`, in the Unicorn CPU emulator.
- The encoders are rgbcx by Richard Geldreich and stb_dxt by Sean Barrett, both public domain or MIT. Their licenses are in `native/bc/`.
