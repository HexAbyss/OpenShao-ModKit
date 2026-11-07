"""The game's logical archive: eight volumes of 0x12c00000 bytes act as one, with a table at the start (PWF, version 2)."""
import struct

VOLUME = 0x12c00000


def entry(lo, hi):
    """(offset, first size, second size, compressed) of a table entry"""
    if hi & 0x80000000:
        offset = (lo << 11) & 0xffffffff
        value = (hi << 32) | lo
        return offset, (value >> 22) & 0x3fffff, ((hi >> 12) & 0x7ffff) << 3, True
    return lo, hi, hi, False


class Archive:
    def __init__(self, volumes, volume_size=VOLUME):
        self.volumes = volumes
        self.volume_size = volume_size  # always VOLUME for the game; tests use small ones
        head = volumes[0]
        if bytes(head[:4]) != b'PWF ':
            raise ValueError('the first volume is not a game archive')
        count, = struct.unpack('<I', head[12:16])
        self.entries = [entry(*struct.unpack('<II', head[0x20 + 8 * i:0x28 + 8 * i])) for i in range(count)]

    def read(self, offset, size):
        out = bytearray()
        while size > 0:
            index = offset // self.volume_size
            if index >= len(self.volumes):
                break
            volume, low = self.volumes[index], offset % self.volume_size
            step = min(size, self.volume_size - low, len(volume) - low)
            if step <= 0:
                break
            out += volume[low:low + step]
            offset += step
            size -= step
        return bytes(out)
