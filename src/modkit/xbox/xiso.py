"""Reads an Xbox game disc image (XDVDFS): the table of files and their bytes."""
import struct

SECTOR = 2048
MAGIC = b'MICROSOFT*XBOX*MEDIA'

class XisoError(Exception):
    pass


class XISO:
    """The files of an image, by name ('default.xbe', 'dir/file'), each with the byte offset and size inside the image."""

    def __init__(self, data):
        # `data` is any bytes-like object (an mmap of the image works)
        self.data = data
        head = bytes(data[32 * SECTOR:32 * SECTOR + SECTOR])
        if head[:20] != MAGIC:
            raise XisoError('this is not an Xbox disc image')
        self.root, self.size = struct.unpack('<II', head[20:28])
        self.files = {}
        for name, sector, size in self._walk(self.root, self.size, ''):
            self.files[name] = (sector * SECTOR, size)

    def _walk(self, sector, size, prefix):
        directory = bytes(self.data[sector * SECTOR:sector * SECTOR + size])
        out = []
        seen = set()

        def node(offset):
            if offset * 4 >= len(directory) or offset in seen:
                return
            seen.add(offset)
            left, right, first, length, attributes, name_length = struct.unpack('<HHIIBB', directory[offset * 4:offset * 4 + 14])
            if left == 0xFFFF and right == 0xFFFF and first == 0xFFFFFFFF:
                return
            name = directory[offset * 4 + 14:offset * 4 + 14 + name_length].decode('latin-1')
            if left:
                node(left)
            if attributes & 0x10:
                out.extend(self._walk(first, length, prefix + name + '/'))
            else:
                out.append((prefix + name, first, length))
            if right:
                node(right)

        node(0)
        return out

    def find(self, name):
        """(offset, size) of a file, matching the name without regard to case"""
        if name in self.files:
            return self.files[name]
        lower = name.lower()
        for key, value in self.files.items():
            if key.lower() == lower:
                return value
        raise KeyError(name)
