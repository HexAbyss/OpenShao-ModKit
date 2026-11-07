"""The signature of a picture's pixels, which tells an edited texture from one that is as it was extracted.

    SHA-256 of "<width>x<height>:" followed by the RGBA bytes, 8 bits a channel, row by row, top row first.

The game's developer mode computes the same value in C++ (src/texture_dev_folder.cpp), so the two must agree byte for byte."""
import hashlib

import numpy as np


def pixel_signature(rgba):
    """`rgba`: a numpy array of shape (height, width, 4), uint8"""
    a = np.ascontiguousarray(rgba, dtype=np.uint8)
    if a.ndim != 3 or a.shape[2] != 4:
        raise ValueError('the picture must be RGBA')
    height, width = a.shape[:2]
    return hashlib.sha256(('%dx%d:' % (width, height)).encode('ascii') + a.tobytes()).hexdigest()
