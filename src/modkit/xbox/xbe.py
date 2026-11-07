"""The sections of an Xbox executable (default.xbe)."""
import struct


class XBE:
    def __init__(self, data):
        self.d = bytes(data)
        d = self.d
        if d[:4] != b'XBEH':
            raise ValueError('this is not an Xbox executable')
        base, = struct.unpack_from('<I', d, 0x104)
        count, address = struct.unpack_from('<II', d, 0x11C)
        self.base = base
        self.secs = []  # (name, virtual address, virtual size, raw offset, raw size, flags)
        for i in range(count):
            flags, va, vsize, raw, rsize = struct.unpack_from('<IIIII', d, address - base + i * 0x38)
            name_va, = struct.unpack_from('<I', d, address - base + i * 0x38 + 20)
            name = d[name_va - base:name_va - base + 12].split(b'\0')[0].decode()
            self.secs.append((name, va, vsize, raw, rsize, flags))
