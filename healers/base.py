"""Healer base class and data structures for the self-heal kit.

A Healer is a deterministic, replayable repair strategy for one *fault domain*.
Each healer implements three pure-ish operations:

    detect(target_dir) -> List[Fault]      # what is broken
    repair(fault)      -> RepairResult     # how to fix it (deterministic)

The engine drives detect -> repair -> verify in a bounded closed loop, so a
healer never needs to know about loops, circuit breakers or snapshots.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


@dataclass
class Fault:
    healer: str
    path: str
    description: str
    repairable: bool = True

    def signature(self) -> str:
        return f"{self.healer}|{os.path.normpath(self.path)}|{self.description}"


@dataclass
class RepairResult:
    healer: str
    path: str
    changed: bool
    detail: str


# Binary extensions we must never treat as text.
_BINARY_EXTS = (".png", ".zip", ".gz", ".exe", ".bin", ".pdf", ".pyc")


class Healer:
    name: str = "base"

    def detect(self, target_dir: str) -> List[Fault]:
        raise NotImplementedError

    def repair(self, fault: Fault) -> RepairResult:
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------
    def _iter_text_files(self, target_dir: str, exts=None) -> List[str]:
        out: List[str] = []
        for root, _, files in os.walk(target_dir):
            for fn in files:
                p = os.path.join(root, fn)
                if any(p.endswith(e) for e in _BINARY_EXTS):
                    continue
                if exts is not None and not any(p.endswith(e) for e in exts):
                    continue
                out.append(p)
        return out
