"""Lists what a texture pack holds.

    python examples/inspect_pack.py <pack.ostp>"""
import sys

import modkit

if len(sys.argv) != 2:
    sys.exit(__doc__)
result = modkit.verify(sys.argv[1])
print('follows the format:', result.ok, *result.problems)
for entry in modkit.pack_entries(sys.argv[1])[:20]:
    print('%016x  %4dx%-4d (original %dx%d)  %s, %d levels' % (entry['hash'], entry['width'], entry['height'], entry['original_width'],
          entry['original_height'], entry['format'], entry['levels']))
print('%d textures in all' % result.textures)
