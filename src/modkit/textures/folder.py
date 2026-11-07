"""A folder of texture pictures, as `extract` writes it, for programs that read and edit them.

    folder = TextureFolder('textures')
    for texture in folder.find(format='DXT5', max_width=64):
        image = folder.image(texture)          # a PIL RGBA image
        folder.save(texture, image.resize((image.width * 2, image.height * 2)))
    folder.compile('pack.ostp', info=dict(id='MyPack', ...))

A texture is named by its hash, the 64-bit key the game swaps textures by: an integer, or 16 hexadecimal digits. The folder's
manifest.json says what each texture is and holds the signature of its pixels, which is how the tool knows what was edited."""
import json
import os
import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .compile import NAME, compile_folder, scan_folder
from .signature import pixel_signature


@dataclass
class Texture:
    hash: int
    file: str                  # the picture's file name in the folder
    format: str = ''           # the game's format (DXT5, A8R8G8B8): informative
    width: int = 0             # the original size, as the game has it
    height: int = 0
    places: list = field(default_factory=list)  # where it occurs in the game's archive
    signature: str = None      # the signature of the pixels as extracted; None when the folder has no manifest entry

    @property
    def key(self):
        return '%016x' % self.hash


class TextureFolder:
    def __init__(self, path):
        self.path = os.fspath(path)
        if not os.path.isdir(self.path):
            raise ValueError('%s is not a folder' % self.path)
        self.textures = {}
        self.has_manifest = False
        records = {}
        manifest = os.path.join(self.path, 'manifest.json')
        if os.path.isfile(manifest):
            try:
                with open(manifest) as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    records, self.has_manifest = loaded, True
            except (ValueError, OSError):
                pass
        for key, record in records.items():
            if isinstance(record, dict) and re.fullmatch(r'[0-9a-fA-F]{16}', key) and isinstance(record.get('file'), str):
                h = int(key, 16)
                self.textures[h] = Texture(h, record['file'], str(record.get('fmt', '')), int(record.get('w', 0)), int(record.get('h', 0)),
                                           list(record.get('at', [])), record.get('pixels') if isinstance(record.get('pixels'), str) else None)
        for file in sorted(os.listdir(self.path)):  # pictures the manifest does not list still count
            match = NAME.match(file)
            if match and int(match.group(1), 16) not in self.textures:
                h = int(match.group(1), 16)
                self.textures[h] = Texture(h, file, match.group(2), int(match.group(3)), int(match.group(4)))

    # ---- looking things up ----
    def __len__(self):
        return len(self.textures)

    def __iter__(self):
        return iter(sorted(self.textures.values(), key=lambda t: t.hash))

    def __contains__(self, hash):
        return self._hash(hash) in self.textures

    @staticmethod
    def _hash(texture):
        if isinstance(texture, Texture):
            return texture.hash
        if isinstance(texture, str):
            return int(texture, 16)
        return int(texture)

    def get(self, texture):
        """The Texture for a hash (integer or hexadecimal text) or a Texture; KeyError when the folder has none"""
        h = self._hash(texture)
        if h not in self.textures:
            raise KeyError('no texture %016x in %s' % (h, self.path))
        return self.textures[h]

    def find(self, format=None, min_width=0, max_width=None, min_height=0, max_height=None, where=None):
        """The textures that match all the given conditions (original size, game format, and `where(texture)` if given)"""
        found = []
        for t in self:
            if format and t.format != format:
                continue
            if t.width < min_width or t.height < min_height:
                continue
            if (max_width is not None and t.width > max_width) or (max_height is not None and t.height > max_height):
                continue
            if where and not where(t):
                continue
            found.append(t)
        return found

    # ---- reading and writing pictures ----
    def file_path(self, texture):
        return os.path.join(self.path, self.get(texture).file)

    def image(self, texture):
        """The picture as a PIL image in RGBA"""
        with Image.open(self.file_path(texture)) as picture:
            return picture.convert('RGBA')

    def array(self, texture):
        """The picture as a numpy array of shape (height, width, 4), uint8"""
        return np.asarray(self.image(texture))

    def save(self, texture, picture):
        """Replaces the texture's picture (a PIL image or a numpy array). The size may differ from the original (2x, 4x), in the same
        proportion and with both sides a multiple of 4; `compile` says what it cannot store."""
        t = self.get(texture)
        if isinstance(picture, np.ndarray):
            picture = Image.fromarray(np.ascontiguousarray(picture, dtype=np.uint8), 'RGBA')
        target = self.file_path(t)
        temporary = target + '.part'
        picture.convert('RGBA').save(temporary, format='PNG')
        os.replace(temporary, target)

    # ---- what was edited ----
    def is_edited(self, texture):
        """Whether the picture differs from what was extracted (a single pixel counts). Without a signature it counts as edited."""
        t = self.get(texture)
        return t.signature is None or pixel_signature(self.array(t)) != t.signature

    def edited(self, workers=None):
        """The edited textures, found the way `compile` finds them (several processes, so guard scripts with if __name__ == '__main__')"""
        scan = scan_folder(self.path, workers)
        return [self.textures[p.hash] for p in scan.pictures if p.hash in self.textures]

    # ---- making a pack ----
    def compile(self, out_path, **options):
        """Compiles the edited pictures into a pack; see compile_folder for the options (info, logo, preload, workers, encoder, progress...)"""
        return compile_folder(self.path, out_path, **options)
