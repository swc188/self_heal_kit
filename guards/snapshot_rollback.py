"""Snapshot / rollback guard.

Before mutating a file we record its bytes. If a repair does not actually
remove the fault (a regression), we restore the original content so the engine
never leaves the target in a worse state than it found it. Provenance:
loop-framework-skill ``loop_rollback.py``.
"""

from __future__ import annotations

import os


class Snapshot:
    def __init__(self):
        self._store = {}

    def take(self, path: str) -> None:
        key = os.path.normpath(path)
        try:
            with open(path, "rb") as fh:
                self._store[key] = fh.read()
        except Exception:
            self._store[key] = None  # file missing -> restore = delete

    def restore(self, path: str) -> None:
        key = os.path.normpath(path)
        if key not in self._store:
            return
        data = self._store[key]
        if data is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "wb") as fh:
                fh.write(data)
