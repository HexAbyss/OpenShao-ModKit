"""OpenShao ModKit: extracts the game's textures as PNG pictures and compiles edited ones into a texture pack (.ostp).

The game's own files are only read, from the ISO or the game folder the user points at; nothing of the game is stored here.

The public interface, for scripts (importing it is cheap: the parts load when first used):

    import modkit
    modkit.extract(game, folder)                  # the game's textures as PNG, with a manifest
    folder = modkit.TextureFolder(folder)         # find, read, edit and compile pictures
    modkit.compile_folder(folder, 'pack.ostp', info={...})
    modkit.verify('pack.ostp')                    # checks a file against the format
    modkit.pack_entries('pack.ostp')              # what a pack holds

Every function raises ValueError, with the reason in words, for what the user can fix (a missing file, an unusable picture)."""
__version__ = '0.1.0'

_EXPORTS = {
    'extract': ('.textures.extract', 'extract'),
    'compile_folder': ('.textures.compile', 'compile_folder'),
    'init_project': ('.textures.compile', 'init_project'),
    'TextureFolder': ('.textures.folder', 'TextureFolder'),
    'Texture': ('.textures.folder', 'Texture'),
    'pixel_signature': ('.textures.signature', 'pixel_signature'),
    'verify': ('.pack.reader', 'verify'),
    'pack_entries': ('.pack.reader', 'entries'),
    'check_game': ('.xbox.source', 'check_game'),
}
__all__ = ['__version__'] + sorted(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        import importlib
        module, attribute = _EXPORTS[name]
        value = getattr(importlib.import_module(module, __name__), attribute)
        globals()[name] = value
        return value
    raise AttributeError('module %r has no attribute %r' % (__name__, name))
