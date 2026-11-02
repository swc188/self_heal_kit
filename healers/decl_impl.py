"""H6 — Declaration vs implementation consistency (provenance: loop v3.19.1, v3.10.3).

v3.19.1 — the README claim no longer matched the implementation (after the CRLF
fix). v3.10.3 — root cause was "passing strings between stages instead of
structured objects", i.e. a declared contract drifted from the code.

This healer checks a declared version in a README / markdown file against the
``__version__`` in Python modules. The README is treated as the source of truth;
the implementation is updated to match. Deterministic and scoped (only README.md
plus ``.py`` files carrying ``__version__``).
"""

from __future__ import annotations

import os
import re

from .base import Healer, Fault, RepairResult

_DECL_RE = re.compile(r"^Version:\s*([0-9][0-9A-Za-z.\-]*)", re.MULTILINE)
_IMPL_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


class DeclImplHealer(Healer):
    name = "decl_impl"

    def detect(self, target_dir: str) -> list:
        faults = []
        declared = self._read_declared(target_dir)
        if declared is None:
            return faults
        for p in self._iter_text_files(target_dir, exts=(".py",)):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except Exception:
                continue
            m = _IMPL_RE.search(text)
            if m and m.group(1) != declared:
                faults.append(Fault(
                    self.name, p,
                    f"__version__ '{m.group(1)}' != declared '{declared}'"))
        return faults

    def _read_declared(self, target_dir: str):
        for p in self._iter_text_files(target_dir, exts=(".md",)):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except Exception:
                continue
            m = _DECL_RE.search(text)
            if m:
                return m.group(1)
        return None

    def repair(self, fault: Fault) -> RepairResult:
        declared = self._read_declared(os.path.dirname(fault.path) or ".")
        if declared is None:
            mm = re.search(r"declared '([^']+)'", fault.description)
            declared = mm.group(1) if mm else None
        with open(fault.path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new_text, _ = _IMPL_RE.subn(
            lambda m: f'__version__ = "{declared}"', text, count=1)
        with open(fault.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_text)
        return RepairResult(self.name, fault.path, True,
                            f"aligned __version__ to '{declared}'")
