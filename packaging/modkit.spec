# PyInstaller spec of the ModKit executable. Built by packaging/linux/build.sh and packaging\windows\build.bat, which set BC_LIB and UNICORN_LIB.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, '..'))
imgui_datas, imgui_binaries, imgui_hidden = collect_all('imgui_bundle')
a = Analysis(
    [os.path.join(root, 'packaging', 'modkit_main.py')],
    pathex=[os.path.join(root, 'src')],
    binaries=[(os.environ['BC_LIB'], 'modkit/_native'), (os.environ['UNICORN_LIB'], 'unicorn/lib')] + imgui_binaries,
    datas=imgui_datas + [(os.path.join(root, 'src', 'modkit', 'gui', 'fonts'), 'modkit/gui/fonts'),
                         (os.path.join(root, 'src', 'modkit', 'gui', 'app.ico'), 'modkit/gui')],
    hiddenimports=collect_submodules('unicorn') + collect_submodules('modkit') + imgui_hidden,
)
# The window system libraries and the C++ runtime come from the host. Bundled copies from the build system are loaded first and clash with
# the host's graphics driver, which is linked against its own.
SYSTEM = ('libX11.so', 'libXext.so', 'libXau.so', 'libXdmcp.so', 'libxcb.so', 'libXrender.so', 'libXi.so', 'libXcursor.so', 'libXrandr.so',
          'libXinerama.so', 'libxkbcommon', 'libwayland', 'libdrm', 'libEGL', 'libGL.so', 'libOpenGL', 'libgbm',
          # the C++ runtime: an older bundled libstdc++ is loaded before the host's and the driver then fails with "GLIBCXX not found"
          'libstdc++.so', 'libgcc_s.so')
# Only top-level entries are excluded: the wheels' own copies (in *.libs/, with a hash in the file name) are what their extension modules link to.
a.binaries = [b for b in a.binaries if '/' in b[0] or not b[0].startswith(SYSTEM)]
pyz = PYZ(a.pure)
if sys.platform in ('win32', 'linux'):
    # A folder, dist/modkit/ (the program `modkit` and its files): a one-file executable unpacks itself into a temporary folder at every start, which takes
    # seconds. The folder is the command line (a console, so a terminal waits for it and reads its output). The window is opened by OpenShao-ModKit
    # (native/launcher), which carries the folder compressed, unpacks it once and starts it, with a splash screen.
    icon = os.path.join(root, 'src', 'modkit', 'gui', 'app.ico') if sys.platform == 'win32' else None
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='modkit', console=True, upx=False, icon=icon)
    COLLECT(exe, a.binaries, a.datas, name='modkit', upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='modkit', console=True, upx=False)
