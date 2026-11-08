"""Prints where the installed unicorn package keeps its library (the one PyInstaller does not find, because it is loaded by path)."""
import os

import unicorn

print(os.path.join(os.path.dirname(unicorn.__file__), 'lib', 'unicorn.dll'))
