"""Entry point of the ModKit executable (PyInstaller builds it from this file; see packaging/linux/build.sh).

With a command (extract, compile, ...) it runs the ModKit; with none it will open the graphical interface, which is not built yet."""
import multiprocessing
import sys

from modkit.cli import main


if __name__ == '__main__':
    multiprocessing.freeze_support()  # the worker processes start from this same executable
    if len(sys.argv) == 1:
        print('The graphical interface is not available yet. Run "modkit --help" for the commands.', file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
