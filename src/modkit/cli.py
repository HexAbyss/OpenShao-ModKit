"""usage:
    python -m modkit extract <game: .iso or folder> <out folder> [--workers N] [--limit N]
    python -m modkit check <game: .iso or folder>
    python -m modkit init <texture folder>
    python -m modkit compile <texture folder> <out.ostp> [--workers N] [--encoder rgbcx:18]
    python -m modkit verify <file.ostp>
    python -m modkit gui
"""
import argparse
import multiprocessing
import sys
import time

from . import __version__


def _clock(seconds):
    seconds = int(seconds)
    return '%d:%02d:%02d' % (seconds // 3600, seconds // 60 % 60, seconds % 60) if seconds >= 3600 else '%d:%02d' % (seconds // 60, seconds % 60)


def command_extract(args):
    from .textures.extract import extract, default_workers
    started = time.time()
    last = [0.0]

    def progress(done, total, textures):
        now = time.time()
        if now - last[0] < 1.0 and done < total:
            return
        last[0] = now
        elapsed = now - started
        eta = elapsed * (total - done) / done if done else 0
        print('\r%5.1f%%  %d of %d archive entries, %d textures, %s elapsed, about %s left   ' %
              (100.0 * done / total, done, total, textures, _clock(elapsed), _clock(eta)), end='', flush=True)

    cancelled = [False]

    def cancel():
        return cancelled[0]

    try:
        result = extract(args.game, args.out, workers=args.workers, limit=args.limit, progress=progress, cancel=cancel)
    except KeyboardInterrupt:
        print('\ncancelled')
        return 130
    except (ValueError, OSError) as error:
        print('\n' + str(error), file=sys.stderr)
        return 1
    print()
    print('%d textures from %d archive entries in %s with %d workers%s' %
          (result.textures, result.entries, _clock(result.seconds), result.workers, ' (cancelled)' if result.cancelled else ''))
    if result.stats:
        print('details:', ', '.join('%s %d' % kv for kv in sorted(result.stats.items())))
    failed = result.stats.get('ewdf_fail', 0) + result.stats.get('decode_fail', 0) + result.stats.get('pwf_bad', 0)
    if failed and not result.cancelled:
        print('WARNING: %d entries or textures could not be read, so the folder lacks some textures' % failed, file=sys.stderr)
        return 2
    return 0


def command_check(args):
    from .xbox.source import GameSource, SourceError
    try:
        source = GameSource(args.game)
    except SourceError as error:
        print(error, file=sys.stderr)
        return 1
    missing = source.check()
    source.close()
    if missing:
        print('the game is incomplete, it lacks: ' + ', '.join(missing))
        return 1
    print('the game is complete (%s)' % source.kind)
    return 0


def command_init(args):
    from .textures.compile import init_project
    try:
        path = init_project(args.folder)
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print('wrote %s: fill it in (id, name, version, authors, summary...), and put logo.png and preload.txt beside it if you have them' % path)
    return 0


def command_compile(args):
    from .textures.compile import compile_folder
    started = time.time()
    last = [0.0]

    def progress(done, total):
        now = time.time()
        if now - last[0] < 1.0 and done < total:
            return
        last[0] = now
        elapsed = now - started
        eta = elapsed * (total - done) / done if done else 0
        print('\r%5.1f%%  %d of %d textures, %s elapsed, about %s left   ' % (100.0 * done / total, done, total, _clock(elapsed), _clock(eta)),
              end='', flush=True)

    try:
        result = compile_folder(args.folder, args.out, workers=args.workers, encoder=args.encoder, progress=progress,
                                require_manifest=not args.no_manifest)
    except KeyboardInterrupt:
        print('\ncancelled')
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        print('\n' + str(error), file=sys.stderr)
        return 1
    print()
    if result.cancelled:
        print('cancelled; no pack was written')
        return 130
    scan = result.scan
    for warning in result.warnings:
        print('warning: ' + warning)
    print('%d textures into %s (%.1f MiB) in %s with %d workers' % (result.textures, args.out, result.size / 1048576, _clock(result.seconds), result.workers))
    print('looked at %d pictures: %d edited, %d as extracted%s' % (scan.files, len(scan.pictures), scan.unchanged,
          (', %d without a signature (counted as edited)' % scan.unsigned) if scan.unsigned else ''))
    for file, why in scan.refused[:10]:
        print('  refused: %s %s' % (file, why))
    for file, first in scan.duplicates[:10]:
        print('  duplicate: %s has the hash of %s, which is used' % (file, first))
    if scan.ignored:
        print('  %d PNG files do not have a texture name and were left out' % len(scan.ignored))
    print('verified: the file follows the format (%s)' % ('no problems' if result.verification.ok else 'PROBLEMS'))
    return 0


def command_verify(args):
    from .pack.reader import verify
    try:
        result = verify(args.file)
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    info = result.info
    if info:
        print('%s %s (%s), %d textures, %.1f MiB%s' % (info.get('name', '?'), info.get('version', '?'), info.get('id', '?'), result.textures,
              result.size / 1048576, ', logo %dx%d' % result.logo if result.logo else ', no logo'))
    if result.ok:
        print('the file follows the format')
        return 0
    for line in result.problems:
        print('problem: ' + line)
    return 1


def command_gui(args):
    try:
        from .gui.app import run
    except ImportError as error:
        print('the graphical interface needs imgui-bundle (%s)' % error, file=sys.stderr)
        return 1
    auto = 'extract' if args.auto_extract else ('compile' if args.auto_compile else None)
    return run(game=args.game or '', out=args.out or '', auto=auto, limit=args.limit, exit_when_done=args.exit_when_done, page=args.page,
               pictures=args.pictures or '', pack=args.pack or '', verify_file=args.verify or '')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='modkit', description='OpenShao ModKit %s' % __version__)
    sub = parser.add_subparsers(dest='command', required=True)
    e = sub.add_parser('extract', help='extract every texture of the game as PNG, with a manifest')
    e.add_argument('game'); e.add_argument('out')
    e.add_argument('--workers', type=int, help='processes to use (default: the cores, up to 8)')
    e.add_argument('--limit', type=int, help='look only at the first N archive entries (for tests)')
    e.set_defaults(run=command_extract)
    c = sub.add_parser('check', help='say whether the game has every file the tool needs')
    c.add_argument('game')
    c.set_defaults(run=command_check)
    i = sub.add_parser('init', help='write a pack.json to fill in, in a texture folder')
    i.add_argument('folder')
    i.set_defaults(run=command_init)
    k = sub.add_parser('compile', help='compile the edited pictures of a texture folder into a .ostp')
    k.add_argument('folder'); k.add_argument('out')
    k.add_argument('--workers', type=int, help='processes to use (default: the cores, up to 8)')
    k.add_argument('--encoder', help='rgbcx:0..18 (default rgbcx:18), stb, or pillow; rgbcx:10 is much faster, for trying things')
    k.add_argument('--no-manifest', action='store_true', help='allow a folder without manifest.json: every picture counts as edited')
    k.set_defaults(run=command_compile)
    v = sub.add_parser('verify', help='check that a .ostp follows the format')
    v.add_argument('file')
    v.set_defaults(run=command_verify)
    g = sub.add_parser('gui', help='open the graphical interface')
    g.add_argument('--game'); g.add_argument('--out')
    g.add_argument('--auto-extract', action='store_true', help=argparse.SUPPRESS)   # for tests of the interface
    g.add_argument('--limit', type=int, help=argparse.SUPPRESS)
    g.add_argument('--page', help=argparse.SUPPRESS)
    g.add_argument('--pictures', help=argparse.SUPPRESS); g.add_argument('--pack', help=argparse.SUPPRESS); g.add_argument('--verify', help=argparse.SUPPRESS)
    g.add_argument('--auto-compile', action='store_true', help=argparse.SUPPRESS)
    g.add_argument('--exit-when-done', action='store_true', help=argparse.SUPPRESS)
    g.set_defaults(run=command_gui)
    args = parser.parse_args(argv)
    return args.run(args)
