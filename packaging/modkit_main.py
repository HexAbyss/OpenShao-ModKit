"""Entry point of the ModKit executable (PyInstaller builds it from this file; see packaging/linux/build.sh).

With a command (extract, compile, ...) it runs the ModKit; with none it opens the graphical interface."""
import multiprocessing
import sys

from modkit.cli import main


if __name__ == '__main__':
    multiprocessing.freeze_support()  # the worker processes start from this same executable
    if len(sys.argv) == 1:
        sys.argv.append('gui')
    sys.exit(main())
