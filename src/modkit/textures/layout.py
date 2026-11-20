"""Puts the extracted pictures into subfolders by where the game uses each texture.

A texture's places are in the manifest (`at`, the archive entry first). Each place gives a context: a level, the front end, a character,
common resources or other. A texture with one context goes to its folder; with several it goes to Shared. Nothing is guessed: a texture
with no safe context stays in Common or Other. The character table comes from the game's executable."""
import os
import struct
from collections import defaultdict

from .. import fsutil
from ..xbox.xbe import XBE

LEVEL_FIRST, LEVEL_LAST, LEVEL_SPAN = 901, 6040, 20
CHARACTER_TABLE, CHARACTER_STRIDE, CHARACTER_COUNT, CHARACTER_FIRST_TYPE = 0x4FA9F0, 0x30, 91, 0x20004
GAME_ID_OFFSET = 20


def _u32(xbe, address):
    for _, va, vsize, raw, rsize, _ in xbe.secs:
        if va <= address and address + 4 <= va + min(vsize, rsize):
            return struct.unpack_from('<I', xbe.d, raw + address - va)[0]
    raise ValueError('address outside the executable')


def character_records(xbe_data):
    """{archive entry: [character indexes]} from the executable's character table; empty when the executable has no such table"""
    try:
        xbe = XBE(xbe_data)
        rows = []
        for k in range(CHARACTER_COUNT):
            at = CHARACTER_TABLE + k * CHARACTER_STRIDE
            rows.append([_u32(xbe, at + 4 * i) for i in range(12)])
        if rows[0][0] != CHARACTER_FIRST_TYPE or rows[-1][0] != CHARACTER_FIRST_TYPE + CHARACTER_COUNT - 1:
            return {}
    except (ValueError, struct.error, IndexError):
        return {}
    owners = defaultdict(list)
    for k, row in enumerate(rows):
        records = {r - GAME_ID_OFFSET for r in row[3:12] if r}
        if row[7]:
            records |= set(range(row[7] - GAME_ID_OFFSET, row[7] - GAME_ID_OFFSET + 12))
        for record in sorted(records):
            if record > 0 and k not in owners[record]:
                owners[record].append(k)
    return dict(owners)


def contexts(places, owners):
    """The set of contexts of a texture, from its places"""
    found = set()
    for place in places:
        record = place[0]
        if record in owners:
            found.update(('character', k) for k in owners[record])
        elif LEVEL_FIRST <= record <= LEVEL_LAST:
            level = (record - LEVEL_FIRST) // LEVEL_SPAN
            found.add(('front end', 0) if level == 0 else ('level', level))
        elif record < LEVEL_FIRST:
            found.add(('common', 0))
        else:
            found.add(('other', 0))
    return found


def folder_for(found):
    """The subfolder (with '/') for a set of contexts"""
    if len(found) == 1:
        kind, n = next(iter(found))
        return {'level': 'Levels/Room %03d' % n, 'front end': 'Levels/Front end (room 0)', 'character': 'Characters/Character %03d' % n,
                'common': 'Common', 'other': 'Other'}[kind]
    kinds = {kind for kind, _ in found}
    if kinds == {'level'}:
        return 'Shared/Between levels'
    if kinds == {'character'}:
        return 'Shared/Between characters'
    return 'Shared/Mixed'


def organize(out_dir, manifest, xbe_data):
    """Moves each picture of the manifest from the folder's top level to its subfolder; returns how many went to each folder"""
    owners = character_records(xbe_data)
    counts = defaultdict(int)
    for record in manifest.values():
        name = record.get('file')
        source = os.path.join(out_dir, name) if name else None
        if not source or not os.path.isfile(source):
            continue
        folder = folder_for(contexts(record['at'], owners))
        target_dir = os.path.join(out_dir, *folder.split('/'))
        os.makedirs(target_dir, exist_ok=True)
        fsutil.replace(source, os.path.join(target_dir, name))
        counts[folder] += 1
    return dict(sorted(counts.items()))
