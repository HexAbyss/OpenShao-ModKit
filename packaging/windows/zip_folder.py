"""Zips a folder, with its contents at the root of the archive: python zip_folder.py <folder> <out.zip>

The launcher (native/launcher) unpacks it with the tar.exe that comes with Windows 10 and later."""
import os
import sys
import zipfile


def main(folder, out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _, names in os.walk(folder):
            for name in sorted(names):
                path = os.path.join(root, name)
                z.write(path, os.path.relpath(path, folder).replace(os.sep, '/'))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
