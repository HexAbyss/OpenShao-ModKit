"""The OSTP texture pack file, version 1.1 (specified in TEXTURE_PACK_FORMAT.md in the OpenShao repository).

The layout is: a 128 byte header, the metadata (JSON), an optional logo, the index (40 bytes a texture, sorted by hash) and the data (the BC
blocks of every texture, largest level first, each texture starting on a multiple of 16). The size of every texture's blocks follows from its
size and format, so the whole layout, and so the index, is known before any block is encoded; the data is then written as the blocks arrive."""
import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass

from PIL import Image

from .. import fsutil

MAGIC = b'OSTPACK\0'
HEADER = 128
ENTRY = 40
MAX_SIDE = 8192
MAX_LOGO = 256
MAX_LEVELS = 14
BC1, BC3 = 1, 2
REQUIRED = ('id', 'name', 'version', 'authors', 'summary', 'min_recomp')
ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
LIMITS = dict(name=64, summary=200, description=4000, website=256, credits=4000, license=128)


def align(n):
    return (n + 15) // 16 * 16


def level_count(width, height):
    """All the levels, down to one pixel"""
    n, side = 1, max(width, height)
    while side > 1:
        side >>= 1
        n += 1
    return n


def level_size(width, height, level, fmt):
    w, h = max(1, width >> level), max(1, height >> level)
    return ((w + 3) // 4) * ((h + 3) // 4) * (8 if fmt == BC1 else 16)


@dataclass
class Spec:
    """One texture of the pack, before its blocks exist"""
    hash: int          # 64-bit hash of the level 0 bytes of the game's texture
    width: int         # of the stored picture, level 0
    height: int
    original_width: int   # of the game's own texture
    original_height: int
    alpha: bool        # BC3 when there is transparency, BC1 when there is none
    levels: int = 0
    data_offset: int = 0   # inside the data section; set by layout()

    @property
    def format(self):
        return BC3 if self.alpha else BC1

    @property
    def data_size(self):
        return sum(level_size(self.width, self.height, l, self.format) for l in range(self.levels))


def check_spec(spec):
    """Why a texture cannot be stored, or None"""
    w, h, ow, oh = spec.width, spec.height, spec.original_width, spec.original_height
    if w < 4 or h < 4 or w > MAX_SIDE or h > MAX_SIDE:
        return 'the size %dx%d is not from 4 to %d on each side' % (w, h, MAX_SIDE)
    if w % 4 or h % 4:
        return 'the size %dx%d is not a multiple of 4 on both sides' % (w, h)
    if ow < 1 or oh < 1 or w * oh != h * ow:
        return 'the size %dx%d is not in the proportion of the original %dx%d' % (w, h, ow, oh)
    return None


LINE_TEXT = ('description', 'credits')                      # may have line breaks
ONE_LINE_TEXT = ('name', 'summary', 'website', 'license')   # one line each
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def clean_info(info):
    """A copy of the information the game can read: it refuses control characters, so a tab or a line break in a one-line text (and a tab or a carriage return
    anywhere) becomes a space, and the line breaks of a description and of the credits become line feeds"""
    info = dict(info)
    for key in LINE_TEXT:
        if isinstance(info.get(key), str):
            text = info[key].replace('\r\n', '\n').replace('\r', '\n')
            info[key] = re.sub(r'[\x00-\x09\x0b-\x1f\x7f]', ' ', text).strip()
    for key in ONE_LINE_TEXT:
        if isinstance(info.get(key), str):
            info[key] = _CONTROL.sub(' ', info[key]).strip()
    if isinstance(info.get('authors'), list):
        info['authors'] = [_CONTROL.sub(' ', a).strip() if isinstance(a, str) else a for a in info['authors']]
    return info


def control_problems(info):
    """The texts that hold control characters the game refuses (a line feed is allowed in the description and in the credits)"""
    problems = []
    for key in ONE_LINE_TEXT + LINE_TEXT:
        text = info.get(key)
        if isinstance(text, str) and re.search(r'[\x00-\x09\x0b-\x1f\x7f]' if key in LINE_TEXT else r'[\x00-\x1f\x7f]', text):
            problems.append('%s has a control character (a tab, or a line break where only one line is allowed)' % key)
    if any(isinstance(a, str) and _CONTROL.search(a) for a in info.get('authors', []) if isinstance(info.get('authors'), list)):
        problems.append('an author has a control character')
    return problems


def validate_info(info):
    """The problems of the pack's information, in words; an empty list when it is fine"""
    problems = ['the information lacks: ' + k for k in REQUIRED if not info.get(k)]
    problems += control_problems(info)
    if info.get('id') and not ID.match(str(info['id'])):
        problems.append('id must be letters, digits, - or _ (1 to 80)')
    if info.get('version') and not VERSION.match(str(info['version'])):
        problems.append('version must be three numbers like 1.0.0')
    if info.get('min_recomp') and not VERSION.match(str(info['min_recomp'])):
        problems.append('min_recomp must be three numbers like 0.4.1')
    for key, limit in LIMITS.items():
        if info.get(key) and len(str(info[key])) > limit:
            problems.append('%s is longer than %d characters' % (key, limit))
    authors = info.get('authors')
    if authors is not None and (not isinstance(authors, list) or not authors or len(authors) > 16 or
                                any(not isinstance(a, str) or not a or len(a) > 64 for a in authors)):
        problems.append('authors must be a list of 1 to 16 names of up to 64 characters')
    preload = info.get('preload', [])
    if len(preload) > 4096 or any(not re.match(r'^[0-9a-fA-F]{16}$', p if isinstance(p, str) else '%016x' % p) for p in preload):
        problems.append('preload must be at most 4096 hashes of 16 hexadecimal digits')
    return problems


def logo_block(logo):
    """The logo as the file keeps it: width, height (16 bits each) and raw RGBA, at most 256 x 256"""
    if logo is None:
        return b''
    image = logo.convert('RGBA')
    image.thumbnail((MAX_LOGO, MAX_LOGO), Image.LANCZOS)
    w, h = image.size
    return struct.pack('<HH', w, h) + image.tobytes()


def layout(info, specs, logo=None):
    """Everything the header, the metadata and the index say, from the textures' sizes alone.
    Returns a dict: header, meta, logo, index, data_offset, data_size, file_size, and the metadata dict. Sets each spec's data_offset."""
    problems = validate_info(info)
    if problems:
        raise ValueError('; '.join(problems))
    specs = sorted(specs, key=lambda s: s.hash)
    for a, b in zip(specs, specs[1:]):
        if a.hash == b.hash:
            raise ValueError('hash %016x appears twice' % a.hash)
    index, cursor, formats, scale = bytearray(), 0, set(), 1.0
    for s in specs:
        reason = check_spec(s)
        if reason:
            raise ValueError('texture %016x: %s' % (s.hash, reason))
        s.levels = s.levels or level_count(s.width, s.height)
        if not 1 <= s.levels <= MAX_LEVELS:
            raise ValueError('texture %016x: %d levels' % (s.hash, s.levels))
        cursor = align(cursor)
        s.data_offset = cursor
        index += struct.pack('<QHHHHBBBBIQQ', s.hash, s.width, s.height, s.original_width, s.original_height, s.levels, s.format,
                             1 if s.alpha else 0, 0, 0, cursor, s.data_size)
        cursor += s.data_size
        formats.add('BC1' if s.format == BC1 else 'BC3')
        scale = max(scale, s.width / s.original_width)
    data_size = align(cursor)
    meta = dict(info)
    if 'preload' in meta:  # hashes to have ready before the menus draw them, as 16 hexadecimal digits
        meta['preload'] = [p if isinstance(p, str) else '%016x' % p for p in meta['preload']]
    meta.update(type='texture', features=sorted(set(info.get('features', [])) | {'hdtextures'}), texture_count=len(specs),
                max_scale=int(-(-scale // 1)), formats=sorted(formats), format_version='1.1')
    meta_bytes = json.dumps(meta, ensure_ascii=False).encode('utf-8')
    logo_bytes = logo_block(logo)

    sections, at = {}, HEADER
    for name, size in (('meta', len(meta_bytes)), ('logo', len(logo_bytes)), ('index', len(index)), ('data', data_size)):
        if name == 'logo' and not size:
            sections[name] = (0, 0)
            continue
        at = align(at)
        sections[name] = (at, size)
        at += size
    header = bytearray(HEADER)
    header[0:8] = MAGIC
    struct.pack_into('<HHIQ', header, 8, 1, 1, HEADER, at)
    for field, name in ((24, 'meta'), (40, 'logo'), (56, 'index'), (72, 'data')):
        struct.pack_into('<QQ', header, field, *sections[name])
    struct.pack_into('<II', header, 88, len(specs), 0)
    header[96:128] = hashlib.sha256(bytes(index)).digest()
    return dict(header=bytes(header), meta=meta_bytes, logo=logo_bytes, index=bytes(index), sections=sections, file_size=at,
                specs=specs, metadata=meta)


def write_pack(path, info, specs, blocks, logo=None, progress=None):
    """Writes the pack. `blocks` yields the encoded bytes of each texture, in the order of the hashes. Returns the metadata written.
    The file is written beside the destination and moved into place, so a failure leaves nothing half made."""
    plan = layout(info, specs, logo)
    sections, specs = plan['sections'], plan['specs']
    temporary = os.fspath(path) + '.part'
    try:
        with open(temporary, 'wb') as out:
            out.write(plan['header'])
            for name in ('meta', 'logo', 'index'):
                if name == 'logo' and not plan['logo']:
                    continue
                out.write(b'\0' * (sections[name][0] - out.tell()))
                out.write(plan[name])
            data_start = sections['data'][0]
            out.write(b'\0' * (data_start - out.tell()))
            written = 0
            for spec, data in zip(specs, blocks):
                if len(data) != spec.data_size:
                    raise ValueError('texture %016x: the encoder made %d bytes, %d were expected' % (spec.hash, len(data), spec.data_size))
                out.write(b'\0' * (data_start + spec.data_offset - out.tell()))
                out.write(data)
                written += 1
                if progress:
                    progress(written, len(specs))
            if written != len(specs):
                raise ValueError('only %d of %d textures were given' % (written, len(specs)))
            out.write(b'\0' * (plan['file_size'] - out.tell()))
        fsutil.replace(temporary, path)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return plan['metadata']
