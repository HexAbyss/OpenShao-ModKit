"""Tests of the texture tool (src/modkit) on synthetic data: a small Xbox disc image, an executable, an archive and textures built
here, so nothing of the game is needed. The Unicorn path (EWDF entries) is checked against the real game by hand and, with
OPENSHAO_TEST_ISO set, by test_real_game below."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from modkit.pack import ostp
from modkit.pack.reader import verify
from modkit.textures import bc
from modkit.textures import compile as compilation
from modkit.textures import extract as extraction
from modkit.textures.signature import pixel_signature
from modkit.xbox import ewdf
from modkit.xbox.archive import Archive, entry
from modkit.xbox.source import GameSource, SourceError, VOLUMES
from modkit.xbox.xiso import XISO, XisoError, SECTOR
from modkit.xbox.xpr import FMT, parse_xpr, to_rgba, xhash


# ---- builders of synthetic game data ----
def disc_image(files):
    """Simple and explicit: builds the image with a flat root directory plus one level of folders, the shapes the game's disc has"""
    image = bytearray(32 * SECTOR)

    def pad(blob):
        return blob + b'\0' * (-len(blob) % SECTOR)

    # the file data first, after the descriptor sector (32) and a gap, so the sectors are known before the directory is written
    layout = {}
    cursor = 34
    data_blobs = []
    for name, data in files.items():
        layout[name] = (cursor, len(data))
        padded = pad(data) if data else b''
        data_blobs.append(padded)
        cursor += len(padded) // SECTOR
    # directories: the root holds the files with no slash and one record per folder; each folder holds its files
    folders = {}
    root_entries = []
    for name in files:
        if '/' in name:
            folders.setdefault(name.split('/')[0], []).append(name)
        else:
            root_entries.append(name)
    directory_sectors = {}
    directory_bytes = {}

    def records_of(entries):
        # entries: (display name, sector, size, attributes); balanced tree, root record first so the walk can start at offset 0
        entries = sorted(entries, key=lambda e: e[0].lower())
        order = []

        def arrange(low, high):
            if low > high:
                return
            middle = (low + high) // 2
            order.append(middle)
            arrange(low, middle - 1)
            arrange(middle + 1, high)

        arrange(0, len(entries) - 1)
        position = {}
        cursor_bytes = 0
        for index in order:
            position[index] = cursor_bytes // 4
            length = 14 + len(entries[index][0])
            cursor_bytes += length + (-length % 4)
        body = bytearray(cursor_bytes)

        def child(low, high):
            if low > high:
                return None
            return (low + high) // 2

        def write(low, high):
            middle = child(low, high)
            if middle is None:
                return 0
            left, right = write(low, middle - 1), write(middle + 1, high)
            name, sector, size, attributes = entries[middle]
            at = position[middle] * 4
            body[at:at + 14 + len(name)] = struct.pack('<HHIIBB', left, right, sector, size, attributes, len(name)) + name.encode('latin-1')
            return position[middle]

        assert write(0, len(entries) - 1) == 0
        return pad(bytes(body)), len(body)

    folder_blobs = {}
    for folder, names in folders.items():
        blob, size = records_of([(n.split('/', 1)[1], layout[n][0], layout[n][1], 0) for n in names])
        folder_blobs[folder] = (blob, size)
    directory_start = cursor
    for folder, (blob, size) in folder_blobs.items():
        directory_sectors[folder] = cursor
        cursor += len(blob) // SECTOR
    root_records = [(n, layout[n][0], layout[n][1], 0) for n in root_entries] + [(f, directory_sectors[f], folder_blobs[f][1], 0x10) for f in folders]
    root_blob, root_size = records_of(root_records)
    root_sector = cursor
    descriptor = bytearray(SECTOR)
    descriptor[:20] = b'MICROSOFT*XBOX*MEDIA'
    descriptor[20:28] = struct.pack('<II', root_sector, root_size)
    out = bytearray(image) + descriptor + bytearray(SECTOR)  # sector 32: descriptor, 33: spare
    for blob in data_blobs:
        out += blob
    for folder in folders:
        out += folder_blobs[folder][0]
    out += root_blob
    return bytes(out)


def xbe_bytes():
    """The smallest executable the tool accepts: one section, with a name"""
    base, header_size = 0x10000, 0x1000
    d = bytearray(header_size + 0x100)
    d[0:4] = b'XBEH'
    struct.pack_into('<I', d, 0x104, base)
    section_headers = base + 0x400
    struct.pack_into('<II', d, 0x11C, 1, section_headers)
    name_va = base + 0x800
    d[0x800:0x800 + 6] = b'.data\0'
    struct.pack_into('<IIIII', d, 0x400, 0, 0x400000, 0x100, header_size, 0x100)
    struct.pack_into('<I', d, 0x400 + 20, name_va)
    return bytes(d)


def xpr_dxt5(blocks):
    """An XPR0 with one 4 x 4 DXT5 texture per block (16 bytes each), non swizzled, as the game's packed resources hold them"""
    out = bytearray()
    records = bytearray()
    data = bytearray()
    for block in blocks:
        fmt = (0x0F << 8) | (1 << 16) | (2 << 20) | (2 << 24)  # DXT5, one level, width 1 << 2, height 1 << 2
        records += struct.pack('<5I', 0x40000, len(data), 0, fmt, 0)
        data += block
    header = 12 + len(records) + 4
    header += (-header) % 16
    out += b'XPR0' + struct.pack('<II', header + len(data), header)
    out += records + struct.pack('<I', 0xFFFFFFFF)
    out += b'\0' * (header - len(out))
    out += data
    return bytes(out)


def solid_dxt5(red, green, blue, alpha):
    r, g, b = red * 31 // 255, green * 63 // 255, blue * 31 // 255
    color = (r << 11) | (g << 5) | b
    return bytes([alpha, alpha, 0, 0, 0, 0, 0, 0]) + struct.pack('<HHI', color, color, 0)


def pwf(entries):
    """A version 2 archive table with plain entries (offset, size), the data after the table"""
    count = len(entries)
    table_end = 0x20 + 8 * count
    out = bytearray(b'PWF ' + struct.pack('<III', 0, 2, count) + b'\0' * 16)
    cursor = table_end + (-table_end % 16)
    data = bytearray()
    for blob in entries:
        out += struct.pack('<II', cursor + len(data), len(blob))
        data += blob + b'\0' * (-len(blob) % 16)
    out += b'\0' * (cursor - len(out))
    return bytes(out + data)


def game_folder(root, archive=None):
    """A folder with every file the tool needs: an executable and the eight volumes, the first holding `archive`"""
    root.mkdir(parents=True, exist_ok=True)
    (root / 'default.xbe').write_bytes(xbe_bytes())
    for i, name in enumerate(VOLUMES):
        (root / name).write_bytes(archive if (i == 0 and archive) else b'\0' * 64)
    return root


class SignatureTest(unittest.TestCase):
    def test_signature_is_the_one_the_game_computes(self):
        # the same two values the game's own test checks (tests/recomp_texture_dev_folder_test.cpp)
        self.assertEqual(pixel_signature(np.arange(1, 17, dtype=np.uint8).reshape(2, 2, 4)),
                         'c63575beb3bb0ea56abf587f4d589d2d85c6af225097b055bfdc4e26b85138a4')
        self.assertEqual(pixel_signature(np.array([[[255, 0, 0, 255]] * 4], dtype=np.uint8)),
                         'e90464c2d1fbe143790d1e66bb891f5658208a6861c2934ebb88b5f006b5d587')

    def test_the_size_is_part_of_it_and_one_bit_changes_it(self):
        a = np.zeros((2, 8, 4), np.uint8)
        self.assertNotEqual(pixel_signature(a), pixel_signature(a.reshape(8, 2, 4)))
        b = a.copy(); b[1, 3, 2] = 1
        self.assertNotEqual(pixel_signature(a), pixel_signature(b))

    def test_wrong_pictures_are_refused(self):
        with self.assertRaises(ValueError):
            pixel_signature(np.zeros((4, 4, 3), np.uint8))


class DiscTest(unittest.TestCase):
    def test_files_of_an_image_are_found_with_their_bytes(self):
        files = {'default.xbe': b'X' * 5000, 'GAMEDATA.WAD': b'W' * 100, 'media/a.bin': b'A' * 3000, 'media/b.bin': b'B' * 10, 'empty.bin': b''}
        image = disc_image(files)
        iso = XISO(image)
        for name, data in files.items():
            if not data:
                continue
            offset, size = iso.find(name)
            self.assertEqual(size, len(data), name)
            self.assertEqual(image[offset:offset + size], data, name)
        self.assertEqual(iso.find('DEFAULT.XBE')[1], 5000, 'names match without regard to case')
        self.assertEqual(iso.find('MEDIA/A.BIN')[1], 3000)

    def test_a_file_that_is_not_an_image_is_refused(self):
        with self.assertRaises(XisoError):
            XISO(b'\0' * (40 * SECTOR))

    def test_a_missing_file_is_a_clear_error(self):
        iso = XISO(disc_image({'default.xbe': b'X' * 10}))
        with self.assertRaises(KeyError):
            iso.find('nothing.bin')


class SourceTest(unittest.TestCase):
    def test_an_image_and_a_folder_give_the_same_files(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            files = {'default.xbe': xbe_bytes()}
            files.update({name: b'V' * 70 for name in VOLUMES})
            (root / 'game.iso').write_bytes(disc_image(files))
            folder = game_folder(root / 'folder')
            image, directory = GameSource(root / 'game.iso'), GameSource(folder)
            try:
                self.assertEqual((image.kind, directory.kind), ('iso', 'folder'))
                self.assertEqual(image.default_xbe(), directory.default_xbe())
                self.assertEqual(image.check(), [])
                self.assertEqual(directory.check(), [])
            finally:
                image.close(); directory.close()

    def test_what_is_missing_is_named(self):
        with tempfile.TemporaryDirectory() as t:
            folder = game_folder(Path(t) / 'g')
            (folder / 'GAMEDATA.WAG').unlink()
            (folder / 'default.xbe').unlink()
            source = GameSource(folder)
            try:
                self.assertEqual(source.check(), ['default.xbe', 'GAMEDATA.WAG'])
            finally:
                source.close()

    def test_a_path_that_does_not_exist_or_is_not_an_image(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SourceError):
                GameSource(Path(t) / 'nowhere')
            (Path(t) / 'bad.iso').write_bytes(b'\0' * (40 * SECTOR))
            with self.assertRaises(SourceError):
                GameSource(Path(t) / 'bad.iso')


class ArchiveTest(unittest.TestCase):
    def test_entries_plain_and_packed(self):
        self.assertEqual(entry(0x1000, 0x200), (0x1000, 0x200, 0x200, False))
        # a packed entry: the offset is lo in 2048-byte sectors, the first size is bits 22 to 43 of hi:lo, the second is bits 12 to 30 of hi
        lo, hi = 0x00000010, 0x80000000 | (0x45 << 12) | 0x123
        self.assertEqual(entry(lo, hi), (0x10 << 11, 0x123 << 10, 0x45 << 3, True))

    def test_reading_across_volumes(self):
        # volumes of 100 bytes: a read that starts in one and ends in the next is joined
        volumes = [bytes(range(100)), bytes(range(100, 200)) + b'\0' * 0]
        archive = Archive.__new__(Archive)
        archive.volumes, archive.volume_size = [memoryview(v) for v in volumes], 100
        self.assertEqual(archive.read(90, 20), bytes(range(90, 110)))
        self.assertEqual(archive.read(190, 50), bytes(range(190, 200)), 'a read past the end stops at the end')

    def test_the_first_volume_must_be_an_archive(self):
        with self.assertRaises(ValueError):
            Archive([memoryview(b'NOPE' + b'\0' * 60)])


class TextureTest(unittest.TestCase):
    def test_dxt5_decodes_to_its_color_and_alpha(self):
        data = xpr_dxt5([solid_dxt5(255, 0, 0, 200)])
        (info, raw), = parse_xpr(data)
        self.assertEqual((info['name'], info['w'], info['h']), ('DXT5', 4, 4))
        image = to_rgba(info, raw)
        self.assertEqual(image.shape, (4, 4, 4))
        self.assertTrue((image[..., 0] >= 248).all() and (image[..., 1] == 0).all() and (image[..., 2] == 0).all())
        self.assertTrue((image[..., 3] == 200).all())

    def test_the_hash_is_stable_and_depends_on_every_byte(self):
        raw = bytes(range(64))
        self.assertEqual(xhash(raw), xhash(bytes(raw)))
        for i in (0, 15, 16, 40, 63):
            changed = bytearray(raw); changed[i] ^= 1
            self.assertNotEqual(xhash(raw), xhash(bytes(changed)), 'byte %d' % i)
        self.assertNotEqual(xhash(raw), xhash(raw + b'\0'))

    def test_a_resource_that_is_not_xpr_gives_nothing(self):
        self.assertEqual(parse_xpr(b'NOTX' + b'\0' * 40), [])


class ExtractTest(unittest.TestCase):
    """The whole extraction on a synthetic game: textures in plain archive entries, and inside a nested archive"""

    def build(self, root):
        red, green, blue = solid_dxt5(255, 0, 0, 255), solid_dxt5(0, 255, 0, 128), solid_dxt5(0, 0, 255, 255)
        nested = pwf([xpr_dxt5([blue]), xpr_dxt5([red])])  # the red one occurs a second time here
        archive = pwf([xpr_dxt5([red, green]), b'not a texture', nested, b''])
        return game_folder(root / 'game', archive)

    def test_textures_are_written_with_a_manifest_and_signatures(self):
        with tempfile.TemporaryDirectory() as t:
            game, out = self.build(Path(t)), Path(t) / 'out'
            calls = []
            result = extraction.extract(game, out, workers=1, progress=lambda *a: calls.append(a))
            self.assertEqual((result.textures, result.cancelled), (3, False))
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(len(manifest), 3)
            for key, record in manifest.items():
                self.assertEqual(len(key), 16)
                self.assertEqual(record['file'], '%s_DXT5_4x4.png' % key)
                pixels = np.asarray(Image.open(out / record['file']).convert('RGBA'))
                self.assertEqual(record['pixels'], pixel_signature(pixels), 'the signature is that of the PNG as read back')
            places = sorted(len(r['at']) for r in manifest.values())
            self.assertEqual(places, [1, 1, 2], 'the red texture occurs twice and is written once')
            self.assertEqual(len([f for f in os.listdir(out) if f.endswith('.png')]), 3)
            self.assertEqual([f for f in os.listdir(out) if f.endswith('.part')], [])
            done = [c[0] for c in calls]
            self.assertEqual(done, sorted(done), 'progress only goes forward')
            self.assertEqual(calls[-1][:2], (4, 4))

    def test_several_processes_give_the_same_result(self):
        with tempfile.TemporaryDirectory() as t:
            game = self.build(Path(t))
            one, many = Path(t) / 'one', Path(t) / 'many'
            extraction.extract(game, one, workers=1)
            result = extraction.extract(game, many, workers=2)
            self.assertEqual(result.textures, 3)
            self.assertEqual((one / 'manifest.json').read_text(), (many / 'manifest.json').read_text())
            for f in os.listdir(one):
                if f.endswith('.png'):
                    self.assertEqual((one / f).read_bytes(), (many / f).read_bytes(), f)

    def test_cancelling_stops_without_a_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            # twelve entries, handed out two at a time: cancelling is looked at between the chunks
            archive = pwf([xpr_dxt5([solid_dxt5(20 * i, 0, 0, 255)]) for i in range(12)])
            game, out = game_folder(Path(t) / 'game', archive), Path(t) / 'out'
            seen = []
            with mock.patch.object(extraction, 'CHUNK', 2):
                result = extraction.extract(game, out, workers=1, cancel=lambda: len(seen) >= 2, progress=lambda *a: seen.append(a))
            self.assertTrue(result.cancelled)
            self.assertFalse((out / 'manifest.json').exists(), 'a partial manifest would mislead')
            self.assertEqual(result.entries, 4, 'it stopped after the second chunk')

    def test_a_limit_looks_only_at_the_first_entries(self):
        with tempfile.TemporaryDirectory() as t:
            game, out = self.build(Path(t)), Path(t) / 'out'
            result = extraction.extract(game, out, workers=1, limit=1)
            self.assertEqual((result.entries, result.textures), (1, 2))

    def test_an_incomplete_game_is_refused_with_the_names(self):
        with tempfile.TemporaryDirectory() as t:
            game = self.build(Path(t))
            (game / 'GAMEDATA.WAJ').unlink()
            with self.assertRaises(ValueError) as caught:
                extraction.extract(game, Path(t) / 'out', workers=1)
            self.assertIn('GAMEDATA.WAJ', str(caught.exception))
            self.assertFalse((Path(t) / 'out' / 'manifest.json').exists())


def texture_folder(root, count=4, edited=(0, 1, 2), scale=2):
    """A folder as the extraction leaves it (pictures and a manifest with signatures), then `edited` of them changed: a larger picture
    for the first, a recoloured one of the same size for the others"""
    root.mkdir(parents=True, exist_ok=True)
    manifest, names = {}, []
    for i in range(count):
        key = '%016x' % (0x1000 + i)
        pixels = np.zeros((8, 8, 4), np.uint8)
        pixels[..., 0] = 30 * i + 10
        pixels[..., 1] = np.arange(8)[None, :] * 20
        pixels[..., 2] = np.arange(8)[:, None] * 20
        pixels[..., 3] = 255 if i != 1 else np.arange(8)[:, None] * 30 + 20   # the second has transparency
        name = '%s_DXT5_8x8.png' % key
        Image.fromarray(pixels, 'RGBA').save(root / name)
        manifest[key] = dict(file=name, fmt='DXT5', w=8, h=8, levels=1, linear=False, at=[[0, i]], pixels=pixel_signature(pixels))
        names.append((name, pixels))
    (root / 'manifest.json').write_text(json.dumps(manifest))
    for position, i in enumerate(edited):
        name, pixels = names[i]
        changed = pixels.copy()
        changed[0, 0, 0] ^= 0x40
        picture = Image.fromarray(changed, 'RGBA')
        if position == 0:
            picture = picture.resize((8 * scale, 8 * scale), Image.LANCZOS)
        picture.save(root / name)
    return root


def write_project(folder, **changes):
    info = dict(id='Test_Pack', name='Test pack', version='1.0.0', authors=['Someone'], summary='A pack for the tests.', min_recomp='0.4.1',
                description='Longer text.', credits='Art by someone', logo='logo.png')
    info.update(changes)
    (folder / 'pack.json').write_text(json.dumps(info))
    Image.fromarray(np.full((20, 10, 4), (200, 50, 20, 255), np.uint8), 'RGBA').save(folder / 'logo.png')


def decode_bc1(data, w, h):
    """A reference BC1 decoder, written here so that the check does not depend on the code that encodes"""
    out = np.zeros((h, w, 4), np.uint8)
    blocks = np.frombuffer(data, np.uint8).reshape(-1, 8)
    for n, b in enumerate(blocks):
        c0, c1 = int(b[0]) | (int(b[1]) << 8), int(b[2]) | (int(b[3]) << 8)  # plain integers: a uint8 shifted by 8 would be lost
        def rgb(c):
            r, g, bl = (c >> 11) & 31, (c >> 5) & 63, c & 31
            return np.array([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (bl << 3) | (bl >> 2)], np.int32)
        p0, p1 = rgb(c0), rgb(c1)
        palette = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3] if c0 > c1 else [p0, p1, (p0 + p1) // 2, np.zeros(3, np.int32)]
        bits = int(b[4]) | (int(b[5]) << 8) | (int(b[6]) << 16) | (int(b[7]) << 24)
        bx, by = (n % (w // 4)) * 4, (n // (w // 4)) * 4
        for i in range(16):
            out[by + i // 4, bx + i % 4, :3] = palette[(bits >> (2 * i)) & 3]
            out[by + i // 4, bx + i % 4, 3] = 255
    return out


class CompileTest(unittest.TestCase):
    def build(self, t, **kwargs):
        folder = texture_folder(Path(t) / 'textures', **kwargs)
        write_project(folder)
        return folder

    def test_only_the_edited_pictures_go_into_the_pack(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t)
            out = Path(t) / 'pack.ostp'
            result = compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:2')
            self.assertEqual((result.textures, result.scan.unchanged, result.scan.files), (3, 1, 4))
            self.assertTrue(result.verification.ok, result.verification.problems)
            self.assertEqual(result.verification.logo, (10, 20), 'the logo is kept in its proportion')
            self.assertEqual(result.verification.info['texture_count'], 3)
            self.assertEqual(result.verification.info['max_scale'], 2)
            self.assertEqual(sorted(result.verification.info['formats']), ['BC1', 'BC3'])
            self.assertEqual(result.verification.info['credits'], 'Art by someone')
            self.assertEqual(verify(out).problems, [])

    def test_one_changed_pixel_is_an_edit_and_the_same_pixels_are_not(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(2,))
            scan = compilation.scan_folder(folder, workers=1)
            self.assertEqual([p.hash for p in scan.pictures], [0x1002])
            # saved again with the same pixels and another encoding: not an edit
            name = '%016x_DXT5_8x8.png' % 0x1003
            Image.open(folder / name).save(folder / name, optimize=True, compress_level=9)
            self.assertEqual([p.hash for p in compilation.scan_folder(folder, workers=1).pictures], [0x1002])

    def test_transparency_decides_the_format_and_the_sizes_are_exact(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0, 1))
            out = Path(t) / 'pack.ostp'
            compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:2')
            data = out.read_bytes()
            head = data[:128]
            index_offset, index_size = struct.unpack_from('<QQ', head, 56)
            entries = [struct.unpack_from('<QHHHHBBBBIQQ', data, index_offset + 40 * i) for i in range(index_size // 40)]
            by_hash = {e[0]: e for e in entries}
            first, second = by_hash[0x1000], by_hash[0x1001]
            self.assertEqual((first[1], first[2], first[3], first[4], first[5]), (16, 16, 8, 8, 5), 'a picture twice the size has five levels')
            self.assertEqual((first[6], first[7]), (ostp.BC1, 0), 'no transparency: BC1')
            self.assertEqual((second[6], second[7]), (ostp.BC3, 1), 'transparency: BC3')
            for e in entries:
                self.assertEqual(e[11], sum(ostp.level_size(e[1], e[2], l, e[6]) for l in range(e[5])))
                self.assertEqual(e[10] % 16, 0)

    def test_the_blocks_are_those_the_encoder_makes_and_are_always_the_same(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0,))
            first, second = Path(t) / 'a.ostp', Path(t) / 'b.ostp'
            compilation.compile_folder(folder, first, workers=1, encoder='rgbcx:2')
            compilation.compile_folder(folder, second, workers=2, encoder='rgbcx:2')
            self.assertEqual(first.read_bytes(), second.read_bytes(), 'one process and two give the same file')

    def test_preload_keeps_only_what_the_pack_has(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0, 1))
            (folder / 'preload.txt').write_text('# the menus\n%016x\n%016x  # not in the pack\n%016x\n%016x\n' % (0x1001, 0x1003, 0x1000, 0x1001))
            result = compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1, encoder='rgbcx:0')
            self.assertEqual(result.verification.info['preload'], ['%016x' % 0x1001, '%016x' % 0x1000], 'in order, without repeats or strangers')

    def test_refusals_say_what_is_wrong_and_write_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0,), scale=2)
            out = Path(t) / 'pack.ostp'
            name = '%016x_DXT5_8x8.png' % 0x1000
            Image.open(folder / name).resize((10, 10)).save(folder / name)          # not a multiple of 4, and in proportion
            with self.assertRaises(ValueError) as caught:
                compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:0')
            self.assertIn('not a multiple of 4', str(caught.exception))
            self.assertIn(name, str(caught.exception))
            Image.open(folder / name).resize((16, 8)).save(folder / name)           # not in proportion: refused at the scan
            scan = compilation.scan_folder(folder, workers=1)
            self.assertEqual([f for f, why in scan.refused], [name])
            self.assertFalse(out.exists())
            self.assertEqual([f for f in os.listdir(t) if f.endswith('.part')], [])

    def test_nothing_edited_a_missing_project_and_bad_information(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=())
            with self.assertRaisesRegex(ValueError, 'no picture was edited'):
                compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1)
            (folder / 'pack.json').unlink()
            with self.assertRaisesRegex(ValueError, 'no pack.json'):
                compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1)
            write_project(folder, id='not valid!', version='1.0', authors=[])
            with self.assertRaises(ValueError) as caught:
                compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1)
            for word in ('id must be', 'version must be', 'authors must be'):
                self.assertIn(word, str(caught.exception))

    def test_init_writes_a_project_that_can_be_filled_in_once(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(compilation.init_project(t).endswith('pack.json'))
            self.assertEqual(json.loads((Path(t) / 'pack.json').read_text())['version'], '1.0.0')
            with self.assertRaises(ValueError):
                compilation.init_project(t)

    def test_a_picture_without_a_signature_counts_as_edited(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=())
            manifest = json.loads((folder / 'manifest.json').read_text())
            del manifest['%016x' % 0x1002]['pixels']
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            scan = compilation.scan_folder(folder, workers=1)
            self.assertEqual(([p.hash for p in scan.pictures], scan.unsigned), ([0x1002], 1))


class EncoderTest(unittest.TestCase):
    def picture(self):
        y, x = np.mgrid[0:32, 0:32].astype(np.float32)
        return np.clip(np.stack([x * 8, y * 8, (x + y) * 4, 255 - x * 6], -1), 0, 255).astype(np.uint8)

    def test_sizes_determinism_and_the_names(self):
        a = self.picture()
        for name in ('rgbcx:0', 'rgbcx:18', 'stb', 'pillow'):
            for fmt, size in ((bc.BC1, 8), (bc.BC3, 16)):
                data = bc.encode(a, fmt, name)
                self.assertEqual(len(data), 64 * size, name)
                self.assertEqual(data, bc.encode(a, fmt, name), '%s gives the same blocks every time' % name)
        for bad in ('rgbcx:19', 'rgbcx:-1', 'rgbcx:x', 'stb:slow', 'unknown'):
            with self.assertRaises(ValueError, msg=bad):
                bc.parse(bad)

    def test_the_default_is_the_highest_level_and_it_is_never_worse_than_pillow(self):
        self.assertEqual(bc.parse(bc.DEFAULT), ('rgbcx', 18))
        if not bc.available():
            self.skipTest('the encoder library is not built (native/bc/build.sh)')
        def error(a, name):
            data = bc.encode(a, bc.BC1, name)
            return float(np.abs(decode_bc1(data, a.shape[1], a.shape[0])[..., :3].astype(int) - a[..., :3].astype(int)).mean())
        smooth = self.picture()
        self.assertLessEqual(error(smooth, 'rgbcx:18'), error(smooth, 'pillow'))
        # with detail and noise, as the game's pictures have, the difference is large
        noisy = np.clip(smooth.astype(int) + np.random.default_rng(5).integers(-25, 26, smooth.shape), 0, 255).astype(np.uint8)
        self.assertLess(error(noisy, 'rgbcx:18'), error(noisy, 'pillow') * 0.9)
        self.assertLessEqual(error(noisy, 'rgbcx:18'), error(noisy, 'rgbcx:0'))

    def test_a_wrong_picture_is_refused(self):
        for a in (np.zeros((6, 8, 4), np.uint8), np.zeros((8, 8, 3), np.uint8), np.zeros((8, 8, 4), np.float32)):
            with self.assertRaises(ValueError):
                bc.encode(a, bc.BC3)


class VerifyTest(unittest.TestCase):
    """Each way a file can be wrong is found, and named"""

    def good(self, t):
        folder = texture_folder(Path(t) / 'textures')
        write_project(folder)
        out = Path(t) / 'pack.ostp'
        compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:0')
        return out

    def damaged(self, path, edit):
        data = bytearray(path.read_bytes())
        edit(data)
        broken = path.with_name('broken.ostp')
        broken.write_bytes(bytes(data))
        return verify(broken)

    def test_each_kind_of_damage_is_found(self):
        with tempfile.TemporaryDirectory() as t:
            path = self.good(t)
            self.assertTrue(verify(path).ok)
            cases = {
                'magic': (lambda d: d.__setitem__(0, 0x58), 'magic'),
                'version': (lambda d: d.__setitem__(8, 9), 'version'),
                'size': (lambda d: d.extend(b'\0' * 16), 'bytes'),
                'index sha': (lambda d: d.__setitem__(96, d[96] ^ 1), 'SHA-256'),
                'flags': (lambda d: d.__setitem__(92, 1), 'flags'),
                'index': (lambda d: d.__setitem__(struct.unpack_from('<Q', d, 56)[0] + 5, 0x7f), 'SHA-256'),
                'metadata': (lambda d: d.__setitem__(struct.unpack_from('<Q', d, 24)[0] + 3, 0x00), 'JSON'),
            }
            for name, (edit, word) in cases.items():
                result = self.damaged(path, edit)
                self.assertFalse(result.ok, name)
                self.assertTrue(any(word in p for p in result.problems), '%s: %s' % (name, result.problems))

    def test_a_short_file_and_a_file_that_is_not_a_pack(self):
        with tempfile.TemporaryDirectory() as t:
            short, other = Path(t) / 's.ostp', Path(t) / 'o.ostp'
            short.write_bytes(b'OSTPACK\0' + b'\0' * 20)
            other.write_bytes(b'not a pack at all' + b'\0' * 200)
            self.assertFalse(verify(short).ok)
            self.assertIn('shorter', verify(short).problems[0])
            self.assertIn('magic', verify(other).problems[0])


def _find_reader_source():
    """The OpenShao source (for the game's own reader), when it sits beside this repository or OPENSHAO_REPO points at it"""
    for candidate in (os.environ.get('OPENSHAO_REPO'), str(Path(__file__).resolve().parents[2] / 'OpenShao-repo')):
        if candidate and (Path(candidate) / 'src' / 'texture_pack_file.cpp').is_file():
            return Path(candidate) / 'src'
    return None


@unittest.skipUnless(shutil.which('g++') and _find_reader_source(), 'needs g++ and the OpenShao source (set OPENSHAO_REPO)')
class GameReaderTest(unittest.TestCase):
    """The game's own reader opens what the tool writes and reads the blocks the tool encoded"""

    def test_the_pack_opens_in_the_game_and_the_blocks_are_the_same(self):
        source = _find_reader_source()
        with tempfile.TemporaryDirectory() as t:
            folder = texture_folder(Path(t) / 'textures', count=6, edited=(0, 1, 2, 3, 4))
            write_project(folder)
            out = Path(t) / 'pack.ostp'
            compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:2')
            exe = Path(t) / 'check'
            build = subprocess.run(['g++', '-std=c++20', '-O1', '-I', str(source), str(Path(__file__).parent / 'native' / 'ostp_reader_check.cpp'),
                                    str(source / 'texture_pack_file.cpp'), str(source / 'mods' / 'json.cpp'), str(source / 'mods' / 'sha256.cpp'),
                                    '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[:300])
            run = subprocess.run([str(exe), str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            lines = run.stdout.splitlines()
            self.assertIn('Test_Pack', lines[0])
            self.assertIn('logo yes', lines[0])
            read = {int(l.split()[0], 16): (int(l.split()[5]), int(l.split()[6], 16)) for l in lines[1:]}
            self.assertEqual(len(read), 5)
            scan = compilation.scan_folder(folder, workers=1)
            for p in scan.pictures:
                spec = ostp.Spec(p.hash, p.width, p.height, p.original_width, p.original_height, p.alpha)
                spec.levels = ostp.level_count(p.width, p.height)
                blocks = compilation._encode((p.path, spec.format, spec.levels, 'rgbcx:2'))
                h = 0xcbf29ce484222325
                for byte in blocks:
                    h = ((h ^ byte) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
                self.assertEqual(read[p.hash], (len(blocks), h), '%016x' % p.hash)


class ReviewFixesTest(unittest.TestCase):
    """Each problem the review of the tool found, kept from coming back"""
    def build(self, t, **kwargs):
        folder = texture_folder(Path(t) / 'textures', **kwargs)
        write_project(folder)
        return folder

    def test_a_picture_in_the_wrong_proportion_stops_the_compilation(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0, 1))
            name = '%016x_DXT5_8x8.png' % 0x1000
            Image.open(folder / name).resize((16, 8)).save(folder / name)
            out = Path(t) / 'pack.ostp'
            with self.assertRaisesRegex(ValueError, 'proportion') as caught:
                compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:0')
            self.assertIn(name, str(caught.exception))
            self.assertFalse(out.exists())

    def test_a_picture_that_cannot_be_read_stops_the_compilation(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0,))
            (folder / ('%016x_DXT5_8x8.png' % 0x1002)).write_bytes(b'not a picture')
            with self.assertRaisesRegex(ValueError, 'cannot be read'):
                compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1, encoder='rgbcx:0')

    def test_without_a_usable_manifest_nothing_is_compiled_unless_asked(self):
        for content in (None, '[]', '{not json', '"text"'):
            with tempfile.TemporaryDirectory() as t:
                folder = self.build(t, edited=(0,))
                if content is None:
                    (folder / 'manifest.json').unlink()
                else:
                    (folder / 'manifest.json').write_text(content)
                with self.assertRaisesRegex(ValueError, 'manifest'):
                    compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1, encoder='rgbcx:0')
                result = compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1, encoder='rgbcx:0', require_manifest=False)
                self.assertEqual(result.textures, 4, 'every picture counts as edited')

    def test_a_manifest_record_that_is_not_an_object_is_skipped(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=())
            manifest = json.loads((folder / 'manifest.json').read_text())
            manifest['%016x' % 0x1001] = 5
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            scan = compilation.scan_folder(folder, workers=1)
            self.assertEqual([p.hash for p in scan.pictures], [0x1001], 'no signature: edited')

    def test_a_failure_leaves_an_existing_pack_alone_and_no_leftovers(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0,))
            out = Path(t) / 'pack.ostp'
            out.write_bytes(b'the good pack')
            with mock.patch.object(compilation, 'verify', side_effect=lambda path: mock.Mock(ok=False, problems=['broken'])):
                with self.assertRaisesRegex(ValueError, 'does not verify'):
                    compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:0')
            self.assertEqual(out.read_bytes(), b'the good pack')
            self.assertEqual(sorted(os.listdir(t)), ['pack.ostp', 'textures'])

    def test_cancelling_gives_a_result_without_a_pack(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0, 1, 2))
            out = Path(t) / 'pack.ostp'
            out.write_bytes(b'the good pack')
            result = compilation.compile_folder(folder, out, workers=1, encoder='rgbcx:0', cancel=lambda: True)
            self.assertTrue(result.cancelled)
            self.assertIsNone(result.verification)
            self.assertEqual(out.read_bytes(), b'the good pack')
            self.assertEqual(sorted(os.listdir(t)), ['pack.ostp', 'textures'])

    def test_a_logo_that_cannot_be_read_does_not_stop_the_pack(self):
        with tempfile.TemporaryDirectory() as t:
            folder = self.build(t, edited=(0,))
            (folder / 'logo.png').write_bytes(b'broken')
            result = compilation.compile_folder(folder, Path(t) / 'p.ostp', workers=1, encoder='rgbcx:0')
            self.assertTrue(result.verification.ok)
            self.assertIsNone(result.verification.logo)
            self.assertTrue(any('logo' in w for w in result.warnings))

    def test_colour_under_transparent_pixels_does_not_bleed_into_the_mips(self):
        pixels = np.zeros((8, 8, 4), np.uint8)
        pixels[:, :4] = (255, 0, 0, 255)
        pixels[:, 4:] = (0, 255, 0, 0)  # invisible, but bright green
        chain = compilation._mip_chain(Image.fromarray(pixels, 'RGBA'), 3)
        self.assertEqual([c.size for c in chain], [(8, 8), (4, 4), (2, 2)])
        for level in chain[1:]:
            a = np.asarray(level)
            visible = a[..., 3] > 8
            self.assertTrue(visible.any())
            self.assertLessEqual(int(a[visible][:, 1].max()), 3, 'visible pixels keep their red, none turns green')
        opaque = np.zeros((8, 8, 4), np.uint8) + 255
        self.assertEqual(len(compilation._mip_chain(Image.fromarray(opaque, 'RGBA'), 4)), 4)

    def test_an_encoder_asked_for_by_name_is_never_swapped_silently(self):
        rgba = np.zeros((4, 4, 4), np.uint8)
        with mock.patch.object(bc, '_library', return_value=None), mock.patch.dict(os.environ):
            os.environ.pop('OPENSHAO_BC_ENCODER', None)
            with self.assertRaisesRegex(RuntimeError, 'not built'):
                bc.encode(rgba, bc.BC1, 'rgbcx:18')
            os.environ['OPENSHAO_BC_ENCODER'] = 'stb'
            with self.assertRaisesRegex(RuntimeError, 'not built'):
                bc.encode(rgba, bc.BC1)
            self.assertEqual(len(bc.encode(rgba, bc.BC1, 'pillow')), 8, 'pillow by name is what was asked')
            del os.environ['OPENSHAO_BC_ENCODER']
            with self.assertWarns(RuntimeWarning):
                self.assertEqual(len(bc.encode(rgba, bc.BC1)), 8)  # the default may fall back, and says so

    def test_a_game_source_error_is_a_value_error(self):
        self.assertTrue(issubclass(SourceError, ValueError))
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                extraction.extract(Path(t) / 'missing.iso', Path(t) / 'out', workers=1)

    def test_the_channels_of_the_32_bit_formats_follow_the_dword_names(self):
        raw = bytes([1, 2, 3, 4]) * 4
        def decode(name):
            info = dict(fmt=[k for k, v in FMT.items() if v[0] == name][0], name=name, w=4, h=1, lin=True, pitch=16)
            return to_rgba(info, raw)[0, 0].tolist()
        self.assertEqual(decode('A8R8G8B8'), [3, 2, 1, 4], 'bytes B,G,R,A')
        self.assertEqual(decode('A8B8G8R8'), [1, 2, 3, 4], 'bytes R,G,B,A')
        self.assertEqual(decode('R8G8B8A8'), [4, 3, 2, 1], 'bytes A,B,G,R')


class DecompressorTest(unittest.TestCase):
    def make(self, flags=1, vsize=0x200):
        d = bytearray(xbe_bytes() + b'\0' * 0x400)
        struct.pack_into('<IIIII', d, 0x400, flags, 0x400000, vsize, 0x1000, 0x100)
        d[0x1000:0x1100] = b'\xaa' * 0x100
        return ewdf.Decompressor(bytes(d))

    def test_writable_sections_come_back_whole_including_the_part_past_the_file(self):
        decompressor = self.make()
        self.assertEqual([(va, len(data)) for va, data in decompressor.init], [(0x400000, 0x200)])
        self.assertEqual(decompressor.init[0][1][0x100:], b'\0' * 0x100, 'the zero-filled part')
        decompressor.mu.mem_write(0x400000, b'\x55' * 0x200)  # the decoder dirtied its globals
        decompressor.run(b'x', 10)  # fails (no routine in this image) but restores first
        self.assertEqual(bytes(decompressor.mu.mem_read(0x400000, 0x200)), b'\xaa' * 0x100 + b'\0' * 0x100)
        self.assertEqual(self.make(flags=0).init, [], 'a section the program cannot write is left alone')

    def test_what_does_not_fit_or_does_not_return_is_a_failure_with_a_reason(self):
        decompressor = self.make()
        result, why = decompressor.run(b'x' * (ewdf.MAX_INPUT + 1), 10)
        self.assertIsNone(result)
        self.assertIn('compressed', why)
        result, why = decompressor.run(b'x', ewdf.MAX_OUTPUT)
        self.assertIsNone(result)
        self.assertIn('decompressed', why)
        # a routine that loops forever spends the budget without reaching the return
        decompressor.mu.mem_map(ewdf.DECOMPRESS & ~0xfff, 0x1000)
        decompressor.mu.mem_write(ewdf.DECOMPRESS, b'\xeb\xfe')  # jmp $
        with mock.patch.object(ewdf, 'BUDGET', 1000):
            result, why = decompressor.run(b'x', 10)
        self.assertIsNone(result)
        self.assertIn('did not return', why)


@unittest.skipUnless(os.environ.get('OPENSHAO_TEST_ISO'), 'set OPENSHAO_TEST_ISO to the game image to check against the real game')
class RealGameTest(unittest.TestCase):
    def test_the_first_entries_match_what_was_extracted_before(self):
        reference = os.environ.get('OPENSHAO_TEST_REFERENCE')
        with tempfile.TemporaryDirectory() as t:
            result = extraction.extract(os.environ['OPENSHAO_TEST_ISO'], Path(t) / 'out', workers=2, limit=220)
            self.assertGreater(result.textures, 0)
            self.assertEqual(result.stats.get('ewdf_fail', 0), 0)
            if reference:
                old = json.loads((Path(reference) / 'manifest.json').read_text())
                new = json.loads((Path(t) / 'out' / 'manifest.json').read_text())
                for key, record in new.items():
                    self.assertEqual(record['pixels'], old[key]['pixels'], key)


if __name__ == '__main__':
    unittest.main()
