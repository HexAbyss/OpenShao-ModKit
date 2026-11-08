#!/usr/bin/env python3
"""Packs the ModKit program with its readme and licenses, the way the OpenShao packages are laid out.

    make_release.py linux   <OpenShao-ModKit executable>  <out>.tar.gz   -> OpenShao-ModKit/{OpenShao-ModKit, readme.txt, licenses/}
    make_release.py windows <OpenShao-ModKit.exe>         <out>.zip      -> {OpenShao-ModKit.exe, readme.txt, licenses/}

The program is stored with its permission to run, and the archive is reproducible: fixed times and owners, sorted entries.
"""
import io
import os
import sys
import tarfile
import zipfile

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'release')
TIME = 1767225600  # 2026-01-01 00:00:00 UTC


def extras():
    """(archive path, file path) of the readme and each license, sorted."""
    items = [('readme.txt', os.path.join(HERE, 'readme.txt'))]
    folder = os.path.join(HERE, 'licenses')
    for name in sorted(os.listdir(folder)):
        items.append(('licenses/' + name, os.path.join(folder, name)))
    return items


def pack_linux(program, out):
    with tarfile.open(out, 'w:gz', format=tarfile.PAX_FORMAT) as tar:
        def add(name, path, mode):
            info = tarfile.TarInfo('OpenShao-ModKit/' + name)
            info.size = os.path.getsize(path)
            info.mode, info.mtime, info.uname, info.gname = mode, TIME, 'root', 'root'
            with open(path, 'rb') as f:
                tar.addfile(info, f)
        folder = tarfile.TarInfo('OpenShao-ModKit')
        folder.type, folder.mode, folder.mtime, folder.uname, folder.gname = tarfile.DIRTYPE, 0o755, TIME, 'root', 'root'
        tar.addfile(folder)
        add('OpenShao-ModKit', program, 0o755)
        add('readme.txt', extras()[0][1], 0o644)
        licenses = tarfile.TarInfo('OpenShao-ModKit/licenses')
        licenses.type, licenses.mode, licenses.mtime, licenses.uname, licenses.gname = tarfile.DIRTYPE, 0o755, TIME, 'root', 'root'
        tar.addfile(licenses)
        for name, path in extras()[1:]:
            add(name, path, 0o644)


def pack_windows(program, out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        def add(name, path):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            with open(path, 'rb') as f:
                z.writestr(info, f.read())
        add('OpenShao-ModKit.exe', program)
        for name, path in extras():
            add(name, path)


def main(argv):
    if len(argv) != 4 or argv[1] not in ('linux', 'windows'):
        sys.exit(__doc__)
    (pack_linux if argv[1] == 'linux' else pack_windows)(argv[2], argv[3])
    print('wrote', argv[3])


if __name__ == '__main__':
    main(sys.argv)
