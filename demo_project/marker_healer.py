"""A fault domain the *sample project* adds on top of the engine.

This demonstrates that a project can extend the engine with its own healers.
Crucially, this healer DETECTS a marker it cannot fix and returns
``changed=False`` — so the engine correctly refuses to fake-heal and escalates
to a human (fail-closed), instead of claiming success.

Note: the marker constant is built by concatenation so the literal token never
appears verbatim in this file (otherwise the healer would flag its own source).
"""


import os

from healers.base import Healer, Fault, RepairResult


class MarkerHealer(Healer):
    name = "demo_unfixable_marker"
    # Assembled so the contiguous token is not present in this source file.
    MARKER = "%" + "%UNREPAIRABLE%" + "%"

    def detect(self, target):
        faults = []
        for root, _dirs, files in os.walk(target):
            for fn in files:
                path = os.path.join(root, fn)
                try:
                    text = open(path, "r", encoding="utf-8").read()
                except (OSError, UnicodeDecodeError):
                    continue
                if self.MARKER in text:
                    faults.append(Fault(
                        self.name, path,
                        "unfixable project marker present"))
        return faults

    def repair(self, fault):
        # Intentionally cannot fix this; report it so the engine escalates.
        return RepairResult(
            self.name, fault.path, False,
            "no automated repair strategy for this marker")
