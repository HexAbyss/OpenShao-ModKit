import multiprocessing
import sys

from .cli import main

if __name__ == '__main__':
    multiprocessing.freeze_support()  # the worker processes start from the same program
    sys.exit(main())
