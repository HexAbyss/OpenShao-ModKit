OpenShao ModKit
Extract the textures of Mortal Kombat: Shaolin Monks from your own copy and compile edited pictures into OpenShao texture packs (.ostp).

The game is not included. You need your own USA/Europe Xbox copy (an ISO, or a folder with default.xbe and GAMEDATA.WAD to GAMEDATA.WAK).


GETTING STARTED

1. Open the ModKit: OpenShao-ModKit.exe on Windows, OpenShao-ModKit on Linux.
2. Extract: choose the game and a folder. It writes the textures as PNG pictures and takes about 3 minutes on six cores.
3. Edit the pictures in place. A picture may be larger than the original (2x, 4x) in the same proportion, with both sides a multiple of 4.
4. Compile: choose the folder and where to save the pack. Then Verify checks it.
5. In OpenShao, open Mods and select Install from file to install the pack. To try pictures first without building a pack, turn on Developer on the
   Files page and choose the folder.

The first run unpacks the ModKit into your data folder and opens the window in about a second after that:
Windows: %LOCALAPPDATA%\OpenShao\ModKit
Linux:   ~/.local/share/OpenShao/ModKit


REQUIREMENTS

- Windows 10 or later, or Linux with glibc 2.28 or later and an X11 or Wayland desktop
- A GPU and driver with OpenGL for the window. The Linux command line needs nothing else.
- The Windows file is not code signed: SmartScreen can stop it once. Choose More info, then Run anyway.


COMMAND LINE

On Linux, a ModKit command as the first argument runs in the terminal, with the same file:
  ./OpenShao-ModKit extract <game> <folder>
  ./OpenShao-ModKit compile <folder> <pack.ostp>
  ./OpenShao-ModKit verify <pack.ostp>
On Windows, OpenShao-ModKit.exe always opens the window. To use the commands there, build the ModKit from the source (docs/BUILDING.md in the project).


HELP

Project page and documentation: https://github.com/HexAbyss/OpenShao-ModKit
Report a problem: https://github.com/HexAbyss/OpenShao-ModKit/issues
OpenShao: https://github.com/OAleex/OpenShao

Code license: GPL-2.0-or-later. See licenses/LICENSE.txt and the other notices in licenses/.
The license does not cover the original game or its assets.
