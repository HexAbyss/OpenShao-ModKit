"""Checks a texture pack file against the validation rules of the format (TEXTURE_PACK_FORMAT.md in the OpenShao repository, section 8), in the
order the game's reader applies them, and reports every problem it finds.
The reader in the game (src/texture_pack_file.cpp) is authoritative for what the game accepts; this one lets the tool confirm, before a pack
is distributed, that the file it wrote is sound."""
import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass, field

from .ostp import BC1, BC3, ENTRY, HEADER, ID, MAGIC, MAX_LEVELS, MAX_LOGO, MAX_SIDE, REQUIRED, VERSION, control_problems, level_size


@dataclass
class Verification:
    ok: bool = False
    problems: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    textures: int = 0
    size: int = 0
    logo: tuple = None  # (width, height), or None when there is none or it is not valid


def verify(path):
    result = Verification()
    problem = result.problems.append
    size = os.path.getsize(path)
    result.size = size
    with open(path, 'rb') as f:
        head = f.read(HEADER)
        if len(head) < HEADER:
            problem('the file is shorter than the 128 byte header')
            return result
        magic = head[:8]
        major, minor, header_size = struct.unpack_from('<HHI', head, 8)
        file_size, meta_offset, meta_size, logo_offset, logo_size, index_offset, index_size, data_offset, data_size = struct.unpack_from('<9Q', head, 16)
        count, flags = struct.unpack_from('<II', head, 88)
        index_sha = head[96:128]
        if magic != MAGIC:
            problem('the magic is not OSTPACK')
            return result
        if major != 1:
            problem('version %d.%d is not one this tool knows' % (major, minor))
        if header_size != HEADER:
            problem('the header size is %d, not 128' % header_size)
        if flags != 0:
            problem('the flags are not zero')
        if file_size != size:
            problem('the header says the file is %d bytes, it is %d' % (file_size, size))
            return result
        sections = [('meta', meta_offset, meta_size), ('index', index_offset, index_size), ('data', data_offset, data_size)]
        if logo_size or logo_offset:
            sections.append(('logo', logo_offset, logo_size))
        for name, offset, length in sections:
            if offset % 16:
                problem('the %s section does not start on a multiple of 16' % name)
            if offset < HEADER or offset + length > size:
                problem('the %s section is outside the file' % name)
        ordered = sorted(sections, key=lambda s: s[1])
        for a, b in zip(ordered, ordered[1:]):
            if a[1] + a[2] > b[1]:
                problem('the %s and %s sections overlap' % (a[0], b[0]))
        if meta_size < 1 or meta_size > (1 << 20):
            problem('the metadata is %d bytes, not 1 to 1048576' % meta_size)
        if count > 100000:
            problem('%d textures is more than 100000' % count)
        if index_size != count * ENTRY:
            problem('the index is %d bytes, %d textures need %d' % (index_size, count, count * ENTRY))
        if logo_size > 4 + MAX_LOGO * MAX_LOGO * 4:
            problem('the logo is larger than 256 x 256')
        if count and data_size == 0:
            problem('there are textures and no data')
        if result.problems:
            return result

        f.seek(index_offset)
        index = f.read(index_size)
        if hashlib.sha256(index).digest() != index_sha:
            problem('the index does not match its SHA-256')
        f.seek(meta_offset)
        try:
            info = json.loads(f.read(meta_size).decode('utf-8'))
        except ValueError as error:
            problem('the metadata is not valid JSON: %s' % error)
            return result
        result.info = info
        for key in REQUIRED + ('features', 'type'):
            if key not in info:
                problem('the metadata lacks %s' % key)
        if info.get('type') != 'texture':
            problem('the type is not texture')
        if 'hdtextures' not in info.get('features', []):
            problem('the features do not include hdtextures')
        if info.get('id') and not ID.match(str(info['id'])):
            problem('the id is not letters, digits, - or _')
        if info.get('version') and not VERSION.match(str(info['version'])):
            problem('the version is not three numbers')
        for text in control_problems(info):
            problem('the metadata: ' + text)
        if info.get('texture_count') != count:
            problem('the metadata says %s textures, the header %d' % (info.get('texture_count'), count))
        for key in ('max_scale', 'texture_count'):
            if key in info and not isinstance(info[key], int):
                problem('%s is not an integer' % key)
        if logo_size:
            f.seek(logo_offset)
            block = f.read(logo_size)
            w, h = struct.unpack_from('<HH', block, 0) if len(block) >= 4 else (0, 0)
            if 1 <= w <= MAX_LOGO and 1 <= h <= MAX_LOGO and logo_size == 4 + w * h * 4:
                result.logo = (w, h)
            else:
                problem('the logo is not valid (the game would drop it, and the pack still works)')

    previous, spans = -1, []
    for i in range(count):
        h, w, hgt, ow, oh, levels, fmt, alpha, compression, reserved, offset, length = struct.unpack_from('<QHHHHBBBBIQQ', index, i * ENTRY)
        where = 'texture %d (%016x)' % (i, h)
        if h <= previous:
            problem('%s: the hashes are not strictly increasing' % where)
        previous = h
        if not (4 <= w <= MAX_SIDE and 4 <= hgt <= MAX_SIDE and w % 4 == 0 and hgt % 4 == 0):
            problem('%s: the size %dx%d is not valid' % (where, w, hgt))
            continue
        if ow < 1 or oh < 1 or w * oh != hgt * ow:
            problem('%s: %dx%d is not in the proportion of %dx%d' % (where, w, hgt, ow, oh))
        most = max(w, hgt).bit_length()
        if not 1 <= levels <= min(MAX_LEVELS, most):
            problem('%s: %d levels' % (where, levels))
            continue
        if fmt not in (BC1, BC3):
            problem('%s: the format %d is not BC1 or BC3' % (where, fmt))
            continue
        if alpha not in (0, 1) or (fmt == BC1 and alpha):
            problem('%s: the alpha flag does not agree with the format' % where)
        if compression != 0 or reserved != 0:
            problem('%s: a reserved field is not zero' % where)
        if offset % 16:
            problem('%s: the data does not start on a multiple of 16' % where)
        expected = sum(level_size(w, hgt, l, fmt) for l in range(levels))
        if length != expected:
            problem('%s: %d bytes of data, %d expected' % (where, length, expected))
        if offset + length > data_size:
            problem('%s: the data goes past the data section' % where)
        spans.append((offset, offset + length, where))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if a[1] > b[0]:
            problem('%s and %s share data' % (a[2], b[2]))
    result.textures = count
    result.ok = not result.problems
    return result


def entries(path):
    """The textures a pack holds, as a list of dicts (hash, width, height, original_width, original_height, levels, format, alpha, size).
    The file is not checked here: use verify() for that. Raises ValueError for a file that is not a pack."""
    with open(path, 'rb') as f:
        head = f.read(HEADER)
        if len(head) < HEADER or head[:8] != MAGIC:
            raise ValueError('%s is not a texture pack' % path)
        index_offset, index_size = struct.unpack_from('<QQ', head, 56)
        count = struct.unpack_from('<I', head, 88)[0]
        if index_size != count * ENTRY:
            raise ValueError('the index of %s is damaged' % path)
        f.seek(index_offset)
        index = f.read(index_size)
    out = []
    for i in range(count):
        h, w, hh, ow, oh, levels, fmt, flags, _, _, _, size = struct.unpack_from('<QHHHHBBBBIQQ', index, i * ENTRY)
        out.append(dict(hash=h, width=w, height=hh, original_width=ow, original_height=oh, levels=levels, format='BC1' if fmt == BC1 else 'BC3',
                        alpha=bool(flags & 1), size=size))
    return out
