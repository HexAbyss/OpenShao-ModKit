"""File operations that survive what Windows does to a file that was just written."""
import os
import time


def replace(source, target, attempts=12, delay=0.05):
    """`os.replace`, tried again when it is refused: on Windows an antivirus scan, the search indexer or a preview pane can hold a new file for a moment and
    the rename fails with "access denied". The wait grows, about four seconds in all, and the last error is raised."""
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay * (attempt + 1))
