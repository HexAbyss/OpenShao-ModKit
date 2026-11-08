"""Extracts every distinct texture of the game as an RGBA PNG at its original size, with a manifest.

Files are named <hash>_<format>_<width>x<height>.png (the hash is the 64-bit hash of the texture's level 0 bytes, the key the game
swaps textures by). manifest.json lists, for each hash, the file, the format, the size, where the texture occurs in the archive, and the
signature of its pixels (signature.py), which the game's developer mode uses to tell an edited picture from one left as extracted.

The work is split by the entries of the archive, which are independent, over several processes. Each process has its own emulator."""
import json
import multiprocessing
import os
import struct
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from ..xbox.archive import VOLUME, Archive, entry as archive_entry
from ..xbox.ewdf import Decompressor, unpack_entry
from ..xbox.source import GameSource
from ..xbox.xpr import parse_xpr, to_rgba, xhash
from .signature import pixel_signature

MANIFEST = 'manifest.json'
CHUNK = 4  # archive entries handed to a process at a time: small, because their cost varies a lot


@dataclass
class ExtractResult:
    textures: int = 0
    entries: int = 0          # archive entries looked at
    stats: dict = field(default_factory=dict)
    cancelled: bool = False
    seconds: float = 0.0
    workers: int = 1


_state = None  # what a worker process keeps between chunks


def _init(path, out_dir):
    global _state
    source = GameSource(path)
    _state = dict(source=source, archive=Archive(source.volumes()), decompressor=Decompressor(source.default_xbe()), out=out_dir, seen=set())


def _release():
    """Lets go of what this process keeps of the game, so its files can be moved or deleted"""
    global _state
    state, _state = _state, None
    if state:
        source = state['source']
        state.clear()
        source.close()


def _save(out_dir, name, image):
    """Writes a PNG, once; two processes that find the same texture write the same bytes, so a race is harmless"""
    target = os.path.join(out_dir, name)
    if os.path.exists(target):
        return
    temporary = '%s.%d.part' % (target, os.getpid())
    Image.fromarray(image, 'RGBA').save(temporary, format='PNG')
    os.replace(temporary, target)


def _visit(buffer, path, found, stats):
    state = _state
    magic = bytes(buffer[:4])
    if magic == b'EWDF':
        result, size = unpack_entry(state['decompressor'], bytes(buffer))
        if result is None:
            stats['ewdf_fail'] = stats.get('ewdf_fail', 0) + 1
            return
        buffer = result
        magic = bytes(buffer[:4])
        stats['ewdf_ok'] = stats.get('ewdf_ok', 0) + 1
    if magic == b'XPR0':
        for k, (info, raw) in enumerate(parse_xpr(bytes(buffer))):
            if info.get('unknown'):
                stats['unknown_format_%x' % info['fmt']] = stats.get('unknown_format_%x' % info['fmt'], 0) + 1
                continue
            if info['cube']:
                stats['cube'] = stats.get('cube', 0) + 1
                continue
            key = '%016x' % xhash(raw)
            if key in found:
                found[key]['at'].append([*path, k])
                continue
            if key in state['seen']:  # decoded and written by an earlier chunk of this process: only the place is new
                found[key] = dict(at=[[*path, k]])
                continue
            try:
                image = to_rgba(info, raw)
            except Exception:
                stats['decode_fail'] = stats.get('decode_fail', 0) + 1
                continue
            if image is None:
                stats['no_decoder_' + info['name']] = stats.get('no_decoder_' + info['name'], 0) + 1
                continue
            image = np.ascontiguousarray(image, dtype=np.uint8)
            name = '%s_%s_%dx%d.png' % (key, info['name'], info['w'], info['h'])
            _save(state['out'], name, image)
            state['seen'].add(key)
            found[key] = dict(file=name, fmt=info['name'], w=info['w'], h=info['h'], levels=info['levels'], linear=info['lin'],
                              at=[[*path, k]], pixels=pixel_signature(image))
        return
    if magic == b'PWF ':
        version = struct.unpack('<I', bytes(buffer[8:12]))[0]
        count = struct.unpack('<I', bytes(buffer[12:16]))[0]
        base = 0x20 if version != 1 else 0x800
        if version not in (1, 2) or count > 200000:
            stats['pwf_bad'] = stats.get('pwf_bad', 0) + 1
            return
        for i in range(count):
            lo, hi = struct.unpack_from('<II', buffer, base + 8 * i)
            offset, size, second, packed = archive_entry(lo, hi)
            if not size or offset + size > len(buffer):
                continue
            _visit(memoryview(buffer)[offset:offset + size], path + [i], found, stats)


def _work(indices):
    """The textures found in some entries of the archive: (how many entries, found, stats)"""
    found, stats = {}, {}
    entries = _state['archive'].entries
    for i in indices:
        offset, size, second, packed = entries[i]
        if not size or offset + size > VOLUME * 8:
            continue
        _visit(_state['archive'].read(offset, size), [i], found, stats)
    return len(indices), found, stats


def default_workers():
    return max(1, min(os.cpu_count() or 1, 8))


def extract(source_path, out_dir, workers=None, limit=None, progress=None, cancel=None):
    """Extracts into `out_dir`. `progress(entries_done, entries_total, textures_so_far)` is called as chunks finish;
    `cancel()` returning true stops it (the pictures already written stay, and no manifest is written). `limit` looks only at the
    first entries of the archive, for tests."""
    started = time.time()
    source = GameSource(source_path)
    try:
        missing = source.check()
        if missing:
            raise ValueError('the game is incomplete, it lacks: ' + ', '.join(missing))
        archive = Archive(source.volumes())
        total = len(archive.entries)
        del archive
    finally:
        source.close()
    if limit is not None:
        total = min(total, limit)
    os.makedirs(out_dir, exist_ok=True)
    workers = workers or default_workers()
    chunks = [list(range(i, min(i + CHUNK, total))) for i in range(0, total, CHUNK)]
    merged, stats, done = {}, {}, 0
    result = ExtractResult(workers=workers)

    def take(count, found, found_stats):
        nonlocal done
        done += count
        for key, record in found.items():
            old = merged.get(key)
            if old is None:
                merged[key] = record
            else:  # a record with only 'at' comes from a process that had already decoded the picture
                places = old['at'] + record['at']
                if 'file' not in old:
                    old.update(record)
                old['at'] = places
        for name, value in found_stats.items():
            stats[name] = stats.get(name, 0) + value
        if progress:
            progress(done, total, len(merged))

    if workers == 1:
        _init(source_path, out_dir)
        try:
            for chunk in chunks:
                if cancel and cancel():
                    result.cancelled = True
                    break
                take(*_work(chunk))
        finally:
            _release()
    else:
        context = multiprocessing.get_context('spawn')
        pool = context.Pool(workers, initializer=_init, initargs=(os.fspath(source_path), out_dir))
        try:
            for outcome in pool.imap_unordered(_work, chunks):
                take(*outcome)
                if cancel and cancel():
                    result.cancelled = True
                    pool.terminate()
                    break
            else:
                pool.close()
        finally:
            pool.terminate()
            pool.join()

    result.entries, result.textures, result.stats = done, len(merged), stats
    if not result.cancelled:
        for record in merged.values():
            record['at'].sort()
        manifest = {key: merged[key] for key in sorted(merged)}
        temporary = os.path.join(out_dir, MANIFEST + '.part')
        with open(temporary, 'w') as f:
            json.dump(manifest, f)
        os.replace(temporary, os.path.join(out_dir, MANIFEST))
    result.seconds = time.time() - started
    return result
