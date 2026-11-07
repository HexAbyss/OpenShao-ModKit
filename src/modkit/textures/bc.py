"""BC1 and BC3 encoding: the blocks a texture pack stores, which the graphics card reads as they are.

    blocks = encode(rgba, BC3)            # rgba: numpy uint8, shape (height, width, 4), both sides multiples of 4

The pack is built once by the person who makes it, so the encoder is the best one: rgbcx at its highest level (0 to 18), about 1.5 s a
megapixel. The player never pays that time. Encoders, by name (`name` argument, or the OPENSHAO_BC_ENCODER variable):
    rgbcx:18    the default
    rgbcx:10    ten times faster for a little less quality: for quick tests of the tool itself
    stb         stb_dxt in its high quality mode
    pillow      Pillow's own encoder, for when the library is not built; it makes visible errors in soft transparency
The first three come from the library built from native/bc (build.sh), which travels inside the tool's executable."""
import ctypes
import io
import os
import sys
import warnings
from pathlib import Path

import numpy as np
from PIL import Image

BC1, BC3 = 1, 2
DEFAULT = 'rgbcx:18'
_lib = None
_tried = False
_warned = False


def _library():
    global _lib, _tried
    if _tried:
        return _lib
    _tried = True
    folder = Path(__file__).resolve().parents[1] / '_native'
    candidates = [Path(os.environ['BC_LIB'])] if os.environ.get('BC_LIB') else [folder / n for n in ('libbc.so', 'bcenc.dll', 'libbc.dylib')]
    for path in candidates:
        if path.is_file():
            try:
                lib = ctypes.CDLL(str(path))
                lib.bc_init()
                lib.bc_encode_rgbcx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
                lib.bc_encode_stb.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
                _lib = lib
                return _lib
            except OSError:
                pass
    return None


def available():
    return _library() is not None


def encoder_name():
    return os.environ.get('OPENSHAO_BC_ENCODER', DEFAULT)


def parse(name):
    """('rgbcx', level), ('stb', quality) or ('pillow', 0); a mistake in the name is an error, never a silent change of encoder"""
    kind, _, arg = name.partition(':')
    if kind == 'rgbcx':
        try:
            level = int(arg) if arg else 18
        except ValueError:
            raise ValueError('rgbcx has levels 0 to 18, not %r' % arg)
        if not 0 <= level <= 18:
            raise ValueError('rgbcx has levels 0 to 18, not %d' % level)
        return 'rgbcx', level
    if kind == 'stb' and arg in ('', 'hq', 'fast'):
        return 'stb', 0 if arg == 'fast' else 1
    if kind == 'pillow' and not arg:
        return 'pillow', 0
    raise ValueError('unknown BC encoder %r (rgbcx:0..18, stb, stb:fast, pillow)' % name)


def _pillow(rgba, fmt):
    out = io.BytesIO()
    Image.fromarray(rgba, 'RGBA').save(out, format='DDS', pixel_format='DXT1' if fmt == BC1 else 'DXT5')
    return out.getvalue()[128:]


def encode(rgba, fmt, name=None):
    global _warned
    if fmt not in (BC1, BC3):
        raise ValueError('the format must be BC1 or BC3')
    a = np.ascontiguousarray(rgba)
    if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 4:
        raise ValueError('the picture must be uint8 RGBA')
    h, w = a.shape[:2]
    if w % 4 or h % 4 or w < 4 or h < 4:
        raise ValueError('both sides must be a multiple of 4')
    explicit = bool(name or os.environ.get('OPENSHAO_BC_ENCODER'))
    kind, arg = parse(name or encoder_name())
    lib = _library() if kind != 'pillow' else None
    if kind == 'pillow':
        return _pillow(a, fmt)
    if lib is None:
        if explicit:
            raise RuntimeError('the encoder %s was asked for but the BC library is not built (run native/bc/build.sh)' % (name or encoder_name()))
        if not _warned:
            _warned = True
            warnings.warn('the BC encoders are not built (run native/bc/build.sh); using Pillow, which is worse in quality', RuntimeWarning, stacklevel=2)
        return _pillow(a, fmt)
    out = np.empty((w // 4) * (h // 4) * (8 if fmt == BC1 else 16), np.uint8)
    fn = lib.bc_encode_rgbcx if kind == 'rgbcx' else lib.bc_encode_stb
    fn(a.ctypes.data_as(ctypes.c_void_p), w, h, fmt, arg, out.ctypes.data_as(ctypes.c_void_p))
    return out.tobytes()
