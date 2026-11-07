# PyInstaller spec of the ModKit executable. Built by packaging/linux/build.sh, which sets BC_LIB and UNICORN_LIB.
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, '..'))
imgui_datas, imgui_binaries, imgui_hidden = collect_all('imgui_bundle')
a = Analysis(
    [os.path.join(root, 'packaging', 'modkit_main.py')],
    pathex=[os.path.join(root, 'src')],
    binaries=[(os.environ['BC_LIB'], 'modkit/_native'), (os.environ['UNICORN_LIB'], 'unicorn/lib')] + imgui_binaries,
    datas=imgui_datas,
    hiddenimports=collect_submodules('unicorn') + collect_submodules('modkit') + imgui_hidden,
)
# The window system and the C++ runtime belong to the user's machine: the copies the build system happened to have must not travel with the
# program, or they clash with what the graphics driver there was built against.
SYSTEM = ('libX11.so', 'libXext.so', 'libXau.so', 'libXdmcp.so', 'libxcb.so', 'libXrender.so', 'libXi.so', 'libXcursor.so', 'libXrandr.so',
          'libXinerama.so', 'libxkbcommon', 'libwayland', 'libdrm', 'libEGL', 'libGL.so', 'libOpenGL', 'libgbm',
          # the C++ runtime too: the graphics driver of the user's machine is built against its own, and a older copy here would be loaded first
          # and make the driver fail ("GLIBCXX not found"). Every desktop has it.
          'libstdc++.so', 'libgcc_s.so')
# (only the top-level ones: the wheels' own copies, in *.libs/ with a hash in the name, are what their programs were linked against)
a.binaries = [b for b in a.binaries if '/' in b[0] or not b[0].startswith(SYSTEM)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='modkit', console=True, upx=False)
