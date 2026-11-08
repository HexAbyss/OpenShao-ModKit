"""Makes a tar.gz of a folder, with its contents at the root of the archive: python tar_folder.py <folder> <out.tar.gz>

The launcher (native/launcher/modkit_launcher_linux.cpp) unpacks it with the system's tar."""
import os
import sys
import tarfile


def main(folder, out):
    with tarfile.open(out, 'w:gz', compresslevel=6) as archive:
        for name in sorted(os.listdir(folder)):
            archive.add(os.path.join(folder, name), arcname=name)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
