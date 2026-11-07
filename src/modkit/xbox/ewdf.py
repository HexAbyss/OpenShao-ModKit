"""Decompresses EWDF entries of the game's archive by running the game's own decompressor, found in its default.xbe, in the Unicorn
CPU emulator. The routine is the game's: it comes out of the disc the user has, and nothing of it is kept or distributed."""
import struct

from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP

from .xbe import XBE

DECOMPRESS = 0x326690  # the routine's address in default.xbe of this game
STACK, STACK_SIZE, BUFFER, BUFFER_SIZE, RETURN = 0x10000000, 0x100000, 0x20000000, 0x4000000, 0x30000000
MAX_INPUT, MAX_OUTPUT = 0x1000000, 0x2000000  # the source sits 16 MiB below the destination; the destination ends before the size words
BUDGET = 400_000_000  # instructions


class Decompressor:
    def __init__(self, xbe_bytes):
        xbe = XBE(xbe_bytes)
        self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        low = min(va for _, va, *_ in xbe.secs) & ~0xfff
        high = max(va + max(vsize, rsize) for _, va, vsize, raw, rsize, flags in xbe.secs)
        self.mu.mem_map(low, ((high - low) + 0xfff) & ~0xfff)
        for _, va, vsize, raw, rsize, flags in xbe.secs:
            self.mu.mem_write(va, xbe.d[raw:raw + rsize])
        self.mu.mem_map(STACK, STACK_SIZE)
        self.mu.mem_map(BUFFER, BUFFER_SIZE)
        self.mu.mem_map(RETURN, 0x1000)
        self.mu.mem_write(RETURN, b'\xf4')  # hlt marks the return
        # every writable section as loaded (the part past the file's bytes is zero): restored before each call, because the decoder keeps
        # state in globals
        self.init = [(va, bytes(xbe.d[raw:raw + rsize]).ljust(vsize, b'\0')) for name, va, vsize, raw, rsize, flags in xbe.secs if flags & 1]

    def run(self, compressed, expect):
        """(bytes, size) of the decompressed entry, or (None, reason). Never a partial result presented as whole."""
        if len(compressed) > MAX_INPUT:
            return None, 'the compressed entry is %d bytes, more than the %d the emulator holds' % (len(compressed), MAX_INPUT)
        if expect + 0x1000 > MAX_OUTPUT:
            return None, 'the decompressed entry would be %d bytes, more than the %d the emulator holds' % (expect, MAX_OUTPUT)
        mu = self.mu
        for va, data in self.init:
            mu.mem_write(va, data)
        source, destination = BUFFER, BUFFER + 0x1000000
        mu.mem_write(source, compressed)
        destination_size, source_size = BUFFER + 0x3f00000, BUFFER + 0x3f00008
        mu.mem_write(destination_size, struct.pack('<II', expect + 0x1000, 0))
        mu.mem_write(source_size, struct.pack('<II', len(compressed), 0))
        sp = STACK + STACK_SIZE - 0x100
        arguments = [destination, destination_size, source, source_size, 0]
        mu.mem_write(sp, struct.pack('<I', RETURN) + b''.join(struct.pack('<I', a) for a in arguments))
        mu.reg_write(UC_X86_REG_ESP, sp)
        try:
            mu.emu_start(DECOMPRESS, RETURN, count=BUDGET)
        except UcError as error:
            return None, str(error)
        if mu.reg_read(UC_X86_REG_EIP) != RETURN:
            return None, 'the routine did not return within %d instructions' % BUDGET
        size = struct.unpack('<I', mu.mem_read(destination_size, 4))[0]
        if size > MAX_OUTPUT:
            return None, 'the routine produced %d bytes, more than the %d the emulator holds' % (size, MAX_OUTPUT)
        return bytes(mu.mem_read(destination, size)), size


def unpack_entry(decompressor, blob):
    """`blob` is an EWDF header and its stream, as the archive stores them; (bytes, size), or (None, reason)"""
    if blob[:4] != b'EWDF':
        raise ValueError('not an EWDF entry')
    size, header, crc = struct.unpack('<III', blob[4:16])
    return decompressor.run(blob[header:], size)
