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

# Tool/cache directories that must never be scanned or repaired.
# Mirrors loop_rollback.EXCLUDE_DIRS: touching these can corrupt tool state
# (e.g. .pytest_cache, __pycache__) and is never a legit self-heal action.
_SKIP_DIRS = {
    ".git", ".hg", ".svn",
    ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "node_modules",
    ".loop_snapshots", ".loop_state", ".loop_circuit_state",
    ".upgrade_backup", ".workbuddy", ".quarantine", "baselines",
    # 演示/样本/文档目录：其中的故意损坏样本、演练副本、文档示例属于
    # 教学素材，不是真实故障，绝不能修复（修复会破坏演示语义）。
    "fixtures", "work", "demo_project", "analysis", "docs", "examples",
    "sample_data", "testdata",
}


class Healer:
    name: str = "base"

    def detect(self, target_dir: str) -> List[Fault]:
        raise NotImplementedError

    def repair(self, fault: Fault) -> RepairResult:
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------
    def _iter_text_files(self, target_dir: str, exts=None,
                         exclude_binary: bool = True) -> List[str]:
        out: List[str] = []
        for root, dirs, files in os.walk(target_dir):
            # 剪枝：跳过工具/缓存目录（不进入）
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in files:
                p = os.path.join(root, fn)
                if exclude_binary and any(p.endswith(e) for e in _BINARY_EXTS):
                    continue
                if exts is not None and not any(p.endswith(e) for e in exts):
                    continue
                out.append(p)
        return out
