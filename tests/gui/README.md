# Testing the window without a screen

`Dockerfile` (with Python and imgui-bundle) and `Dockerfile.clean` (a plain desktop system with no Python, for the executable) build images with a
virtual screen (Xvfb) and software OpenGL. The tests start the interface in them, click with `xdotool` and take screenshots with ImageMagick.

```
docker build -t modkit-guitest -f tests/gui/Dockerfile tests/gui
docker build -t modkit-clean   -f tests/gui/Dockerfile.clean tests/gui
bash tests/gui/smoke.sh <game.iso>       # the source, then dist/modkit; screenshots in tests/gui/out/
```
