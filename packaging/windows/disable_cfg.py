"""Clears the Control Flow Guard flag in the header of a Windows executable: python disable_cfg.py path\to\file.exe

PyInstaller's bootloader is built with Control Flow Guard, which makes the process abort (0xC0000409) at the first indirect call into code that
Unicorn generates at run time. The python.exe the ModKit runs under in a virtual environment is not built with it. Only the flag in the PE
header changes; the archive appended to a one-file executable is left as it is."""
import struct
import sys

GUARD_CF = 0x4000


def main(path):
    with open(path, 'r+b') as f:
        f.seek(0x3c)
        pe = struct.unpack('<I', f.read(4))[0]
        f.seek(pe)
        if f.read(4) != b'PE\0\0':
            raise SystemExit('%s is not a PE file' % path)
        characteristics = pe + 4 + 20 + 70  # the DllCharacteristics field of the optional header, same offset in PE32 and PE32+
        f.seek(characteristics)
        value = struct.unpack('<H', f.read(2))[0]
        f.seek(characteristics)
        f.write(struct.pack('<H', value & ~GUARD_CF))


if __name__ == '__main__':
    main(sys.argv[1])
