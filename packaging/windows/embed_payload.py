"""Appends the ModKit (the zipped folder, see zip_folder.py) to the launcher, so the launcher is one file: python embed_payload.py <launcher.exe> <modkit.zip> <out.exe>

Layout of the result: the launcher, the ModKit, its SHA-256 (32 bytes), its size (8 bytes, little-endian) and the marker MKPAYLD1. The launcher reads
the end of its own file (native/launcher/modkit_launcher.cpp, Prepare)."""
import hashlib
import shutil
import struct
import sys


def main(launcher, payload, out):
    with open(payload, 'rb') as f:
        data = f.read()
    shutil.copyfile(launcher, out)
    with open(out, 'ab') as f:
        f.write(data)
        f.write(hashlib.sha256(data).digest())
        f.write(struct.pack('<Q', len(data)))
        f.write(b'MKPAYLD1')


if __name__ == '__main__':
    main(*sys.argv[1:4])
