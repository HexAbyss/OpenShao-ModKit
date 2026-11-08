"""Compiles a folder of texture pictures into a texture pack (.ostp).

The folder is the one the extraction wrote: PNG files named <hash>_<format>_<width>x<height>.png and a manifest.json
with the signature of each picture's pixels. Only the pictures whose pixels differ from their signature go into the pack, the same rule the
game's developer mode uses. Each is stored with all its mip levels as BC1 (no transparency) or BC3 (transparency), encoded with rgbcx at
its highest level; the work is spread over several processes.

The pack's information comes from pack.json in the folder, and the logo and the list of textures to have ready for the menus from logo.png
and preload.txt beside it (`init` writes a pack.json to fill in)."""
import json
import multiprocessing
import os
import re
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from ..pack import ostp
from ..pack.reader import verify
from . import bc
from .extract import default_workers
from .signature import pixel_signature

NAME = re.compile(r'^([0-9a-fA-F]{16})_([A-Za-z0-9]+)_(\d+)x(\d+)\.png$', re.IGNORECASE)
TEMPLATE = dict(id='MyTextures', name='My textures', version='1.0.0', authors=['Your name'],
                summary='What the pack does, in one sentence (up to 200 characters).', min_recomp='0.4.1',
                description='A longer description, shown on the Mods page when the player opens the details.',
                credits='Who made the pictures, and where they come from.', license='', website='', logo='logo.png')


@dataclass
class Picture:
    hash: int
    file: str
    path: str
    width: int
    height: int
    original_width: int
    original_height: int
    alpha: bool
    signed: bool


@dataclass
class Scan:
    pictures: list = field(default_factory=list)   # the edited ones
    files: int = 0
    unchanged: int = 0
    unsigned: int = 0
    refused: list = field(default_factory=list)    # (file, why)
    ignored: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    manifest: bool = False
    manifest_problem: str = ''


@dataclass
class CompileResult:
    textures: int = 0
    size: int = 0
    seconds: float = 0.0
    workers: int = 1
    scan: Scan = None
    verification: object = None
    cancelled: bool = False
    warnings: list = field(default_factory=list)


_signatures = {}


def _set_signatures(signatures):
    global _signatures
    _signatures = signatures


def _look(item):
    """Decodes one picture: (file, edited / unchanged / refused, details)"""
    file, path, name = item
    try:
        with Image.open(path) as image:
            rgba = np.asarray(image.convert('RGBA'))
    except Exception as error:
        return file, 'refused', 'cannot be read as a picture (%s)' % str(error)[:80]
    h, w = rgba.shape[:2]
    key = int(name[0], 16)
    ow, oh = int(name[2]), int(name[3])
    if w * oh != h * ow:
        return file, 'refused', 'is %dx%d, not in the proportion of the original %dx%d' % (w, h, ow, oh)
    signature = _signatures.get(key)
    if signature is not None and pixel_signature(rgba) == signature:
        return file, 'unchanged', None
    return file, 'edited', (key, w, h, ow, oh, bool((rgba[..., 3] < 255).any()), signature is not None)


def scan_folder(folder, workers=None):
    """Which pictures of the folder are edited, and what was refused or odd"""
    scan = Scan()
    signatures = {}
    manifest_path = os.path.join(folder, 'manifest.json')
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path) as f:
                records = json.load(f)
            if not isinstance(records, dict):
                raise ValueError('it is not a JSON object')
            for key, record in records.items():
                if len(key) == 16 and isinstance(record, dict) and isinstance(record.get('pixels'), str):
                    signatures[int(key, 16)] = record['pixels']
            scan.manifest = True
        except (ValueError, OSError) as error:
            scan.manifest_problem = 'manifest.json cannot be used (%s)' % error
    else:
        scan.manifest_problem = 'the folder has no manifest.json'
    items = []
    for file in sorted(os.listdir(folder)):
        if not os.path.isfile(os.path.join(folder, file)):
            continue
        match = NAME.match(file)
        if not match:
            if file.lower().endswith('.png'):
                scan.ignored.append(file)
            continue
        items.append((file, os.path.join(folder, file), match.groups()))
    scan.files = len(items)
    workers = workers or default_workers()
    if workers == 1 or len(items) < 8:
        _set_signatures(signatures)
        outcomes = [_look(i) for i in items]
    else:
        context = multiprocessing.get_context('spawn')
        with context.Pool(workers, initializer=_set_signatures, initargs=(signatures,)) as pool:
            outcomes = pool.map(_look, items, chunksize=16)
    seen = {}
    paths = {file: path for file, path, _ in items}
    for file, kind, details in outcomes:
        if kind == 'refused':
            scan.refused.append((file, details))
        elif kind == 'unchanged':
            scan.unchanged += 1
        else:
            key, w, h, ow, oh, alpha, signed = details
            if key in seen:
                scan.duplicates.append((file, seen[key]))
                continue
            seen[key] = file
            scan.unsigned += 0 if signed else 1
            scan.pictures.append(Picture(key, file, paths[file], w, h, ow, oh, alpha, signed))
    scan.pictures.sort(key=lambda p: p.hash)
    return scan


def _mip_chain(image, levels):
    """The levels of a picture, each halved from the one before. With transparency the halving is done on premultiplied colour, so that
    the colour hidden under fully transparent pixels does not bleed into the smaller levels."""
    premultiplied = image.getextrema()[3][0] < 255
    source = image.convert('RGBa') if premultiplied else image
    chain = [image]
    for _ in range(levels - 1):
        w, h = source.size
        source = source.resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS)
        chain.append(source.convert('RGBA') if premultiplied else source)
    return chain


def _encode(job):
    """The blocks of one texture, every level, largest first"""
    path, fmt, levels, encoder = job
    with Image.open(path) as source:
        image = source.convert('RGBA')
    out = []
    for level in _mip_chain(image, levels):
        a = np.asarray(level)
        h, w = a.shape[:2]
        if w % 4 or h % 4:  # a side under 4 is padded by repeating its edge: one block holds it
            a = np.pad(a, ((0, -h % 4), (0, -w % 4), (0, 0)), mode='edge')
        out.append(bc.encode(a, fmt, encoder))
    return b''.join(out)


def read_preload(folder):
    """The hashes in preload.txt (one a line, `#` starts a comment), as lower-case text; empty when there is no file"""
    preload = []
    path = os.path.join(folder, 'preload.txt')
    if os.path.isfile(path):
        with open(path, encoding='utf-8-sig') as f:  # a BOM from Notepad is not part of the text
            for line in f:
                line = line.split('#')[0].strip()
                if line:
                    preload.append(line.lower())
    return preload


def load_project(folder):
    """(information, logo picture or None, preload hashes, warnings) from pack.json, logo.png and preload.txt in the folder"""
    path = os.path.join(folder, 'pack.json')
    if not os.path.isfile(path):
        raise ValueError('there is no pack.json in the folder; run "init" to write one and fill it in')
    try:
        with open(path, encoding='utf-8-sig') as f:  # a BOM from Notepad is not part of the text
            info = json.load(f)
    except ValueError as error:
        raise ValueError('pack.json is not valid JSON: %s' % error)
    logo, warnings = None, []
    logo_name = info.pop('logo', None)
    if logo_name:
        logo_path = os.path.join(folder, logo_name)
        if os.path.isfile(logo_path):
            try:
                logo = Image.open(logo_path)
                logo.load()
            except Exception as error:  # the logo is optional: the pack goes without it
                logo = None
                warnings.append('the logo %s cannot be read (%s); the pack has none' % (logo_name, str(error)[:80]))
        elif logo_name != TEMPLATE['logo']:
            raise ValueError('the logo %s named in pack.json is not in the folder' % logo_name)
    info = {k: v for k, v in info.items() if v not in ('', None)}
    return info, logo, read_preload(folder), warnings


def init_project(folder):
    path = os.path.join(folder, 'pack.json')
    if os.path.exists(path):
        raise ValueError('pack.json already exists')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(TEMPLATE, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return path


def compile_folder(folder, out_path, workers=None, encoder=None, progress=None, cancel=None, require_manifest=True,
                   info=None, logo=None, preload=None):
    """Builds `out_path` from the edited pictures of `folder`. `progress(done, total)` is called per texture. Raises ValueError, with
    the reasons in words, when the folder cannot make a pack.

    By default the pack's information, logo and preload list come from pack.json, logo.png and preload.txt in the folder. A program can give
    them instead: `info` (a dict with the same keys as pack.json, which then needs not exist), `logo` (a path or a PIL image) and `preload`
    (hashes, as integers or 16 hexadecimal digits)."""
    started = time.time()
    warnings = []
    if info is None:
        info, project_logo, project_preload, warnings = load_project(folder)
        logo = project_logo if logo is None else logo
        preload = project_preload if preload is None else preload
    else:
        info = {k: v for k, v in dict(info).items() if v not in ('', None)}
        info.pop('logo', None)
    if isinstance(logo, (str, os.PathLike)):
        try:
            logo = Image.open(logo)
            logo.load()
        except Exception as error:
            warnings.append('the logo cannot be read (%s); the pack has none' % str(error)[:80])
            logo = None
    preload = [p if isinstance(p, str) else '%016x' % p for p in (preload or [])]
    preload = [p.lower() for p in preload]
    problems = ostp.validate_info(info)
    if problems:
        raise ValueError('pack information: ' + '; '.join(problems))
    scan = scan_folder(folder, workers)
    if scan.manifest_problem and require_manifest:
        raise ValueError('%s, so there is no way to tell which pictures were edited and the whole game would go in the pack. Extract the game '
                         'into the folder with "extract", or pass --no-manifest if every picture here is yours' % scan.manifest_problem)
    if scan.refused:
        raise ValueError('%d pictures cannot be used:\n  ' % len(scan.refused) + '\n  '.join('%s %s' % r for r in scan.refused[:30]) +
                         ('\n  ...' if len(scan.refused) > 30 else ''))
    if not scan.pictures:
        raise ValueError('no picture was edited: every one of the %d pictures has the pixels it was extracted with' % scan.files
                         if scan.files else 'the folder has no pictures named <hash>_<format>_<width>x<height>.png')
    specs, bad = [], []
    for p in scan.pictures:
        spec = ostp.Spec(p.hash, p.width, p.height, p.original_width, p.original_height, p.alpha)
        reason = ostp.check_spec(spec)
        if reason:
            bad.append('%s %s' % (p.file, reason))
        specs.append(spec)
    if bad:
        raise ValueError('%d edited pictures cannot be stored:\n  ' % len(bad) + '\n  '.join(bad[:30]) + ('\n  ...' if len(bad) > 30 else ''))
    have = {'%016x' % s.hash for s in specs}
    info = dict(info)
    wanted = [h for h in preload if h in have]
    if wanted:
        info['preload'] = list(dict.fromkeys(wanted))
    plan = ostp.layout(info, specs, logo)  # sets each spec's levels; raises on anything the format refuses
    by_hash = {p.hash: p for p in scan.pictures}
    jobs = [(by_hash[s.hash].path, s.format, s.levels, encoder) for s in plan['specs']]
    workers = workers or default_workers()
    cancelled = [False]

    def blocks():
        if workers == 1 or len(jobs) < 2:
            for job in jobs:
                if cancel and cancel():
                    cancelled[0] = True
                    raise _Cancelled()
                yield _encode(job)
            return
        context = multiprocessing.get_context('spawn')
        with context.Pool(workers) as pool:
            for blocks_of_one in pool.imap(_encode, jobs, chunksize=1):
                if cancel and cancel():
                    cancelled[0] = True
                    pool.terminate()
                    raise _Cancelled()
                yield blocks_of_one

    result = CompileResult(workers=workers, scan=scan, warnings=warnings)
    # built beside the destination and moved into place only when it verifies: a bad pack never replaces a good one
    candidate = os.fspath(out_path) + '.new'
    try:
        ostp.write_pack(candidate, info, plan['specs'], blocks(), logo, progress)
        result.verification = verify(candidate)
        if not result.verification.ok:
            raise ValueError('the pack does not verify, so it was not written: ' + '; '.join(result.verification.problems[:5]))
        result.textures = len(specs)
        result.size = os.path.getsize(candidate)
        os.replace(candidate, out_path)
    except _Cancelled:
        result.cancelled = True
    finally:
        if os.path.exists(candidate):
            os.remove(candidate)
    result.seconds = time.time() - started
    return result


class _Cancelled(Exception):
    pass
