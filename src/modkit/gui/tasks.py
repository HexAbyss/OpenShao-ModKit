"""Runs a long job (extraction, compilation) on a thread and lets the interface, which draws every frame, read how it is going."""
import threading
import time


class Task:
    def __init__(self, name, function):
        """`function(progress, cancel)` does the work; `progress(done, total, extra=None)` reports and `cancel()` says whether to stop.
        Its return value becomes `result`; a ValueError, OSError or RuntimeError becomes `error` (words the user can read)."""
        self.name = name
        self.done, self.total, self.extra = 0, 0, None
        self.result, self.error = None, ''
        self.finished = False
        self.cancel_requested = False
        self.started = time.time()
        self.ended = None
        self._function = function
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _progress(self, done, total, extra=None):
        self.done, self.total, self.extra = done, total, extra

    def _run(self):
        try:
            self.result = self._function(self._progress, lambda: self.cancel_requested)
        except (ValueError, OSError, RuntimeError) as error:
            self.error = str(error)
        except Exception as error:  # a bug: say so, do not hide it
            self.error = 'unexpected error (%s): %s' % (type(error).__name__, error)
        self.ended = time.time()
        self.finished = True

    def cancel(self):
        self.cancel_requested = True

    @property
    def fraction(self):
        return min(1.0, self.done / self.total) if self.total else 0.0

    @property
    def elapsed(self):
        return (self.ended or time.time()) - self.started

    @property
    def eta(self):
        return self.elapsed * (self.total - self.done) / self.done if self.done and not self.finished else 0.0


def clock(seconds):
    seconds = int(seconds)
    return '%d:%02d:%02d' % (seconds // 3600, seconds // 60 % 60, seconds % 60) if seconds >= 3600 else '%d:%02d' % (seconds // 60, seconds % 60)
