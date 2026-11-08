"""Where the game's files come from: a disc image (.iso) or a folder that holds them (default.xbe and the GAMEDATA volumes)."""
import gc
import mmap
import os

from .xiso import XISO, XisoError

# the logical archive is these eight files, one after another
VOLUMES = ['GAMEDATA.WAD', 'GAMEDATA.WAE', 'GAMEDATA.WAF', 'GAMEDATA.WAG', 'GAMEDATA.WAH', 'GAMEDATA.WAI', 'GAMEDATA.WAJ', 'GAMEDATA.WAK']


class SourceError(ValueError):
    pass


class GameSource:
    """Reads files by name. Close it when done: it keeps the files mapped."""

    def __init__(self, path):
        self.path = os.fspath(path)
        self._files = []
        self._maps = {}
        self._mmaps = []
        self._image = None
        if os.path.isdir(self.path):
            self.kind = 'folder'
            self._iso = None
        elif os.path.isfile(self.path):
            self.kind = 'iso'
            handle = open(self.path, 'rb')
            self._files.append(handle)
            self._image = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            self._mmaps.append(self._image)
            try:
                self._iso = XISO(self._image)
            except XisoError as error:
                self.close()
                raise SourceError('%s: %s' % (os.path.basename(self.path), error))
        else:
            raise SourceError('%s does not exist' % self.path)

    def view(self, name):
        """The bytes of a file, without reading all of them into memory"""
        if self.kind == 'iso':
            try:
                offset, size = self._iso.find(name)
            except KeyError:
                raise SourceError('the image has no %s' % name)
            return memoryview(self._image)[offset:offset + size]
        if name in self._maps:
            return self._maps[name]
        for entry in os.listdir(self.path):
            if entry.lower() == name.lower():
                handle = open(os.path.join(self.path, entry), 'rb')
                self._files.append(handle)
                if os.fstat(handle.fileno()).st_size == 0:
                    view = memoryview(b'')
                else:
                    mapping = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
                    self._mmaps.append(mapping)
                    view = memoryview(mapping)
                self._maps[name] = view
                return view
        raise SourceError('the folder has no %s' % name)

    def default_xbe(self):
        """The game's executable, as bytes: its own decompressor is what reads the archive"""
        return bytes(self.view('default.xbe'))

    def volumes(self):
        return [self.view(name) for name in VOLUMES]

    def check(self):
        """What is missing for an extraction, in words; an empty list when the game is complete"""
        missing = []
        for name in ['default.xbe'] + VOLUMES:
            try:
                self.view(name)
            except SourceError:
                missing.append(name)
        return missing

    def close(self):
        # Windows cannot delete or move a file while any part of it is mapped, so the maps are closed here and not left to the
        # garbage collector. A map cannot close while a view of it lives: the views this object holds are dropped first, and a view
        # a caller still holds keeps its map (and so its file) until the caller lets it go.
        self._maps.clear()
        self._iso = None
        self._image = None
        gc.collect()
        for mapping in self._mmaps:
            try:
                mapping.close()
            except (BufferError, ValueError):
                pass
        self._mmaps = []
        for handle in self._files:
            try:
                handle.close()
            except Exception:
                pass
        self._files = []


def check_game(path):
    """What the game at `path` (an ISO or a folder) lacks for an extraction, as a list of file names; empty when it is complete.
    Raises SourceError (a ValueError) when the path is not a usable game location at all."""
    source = GameSource(path)
    try:
        return source.check()
    finally:
        source.close()
