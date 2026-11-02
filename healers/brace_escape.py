"""H2 — Brace / escape leak detector.

A classic fault class: an f-string or template literal wrote a doubled
opening/closing brace (two consecutive left braces, or two consecutive right
braces) where the *unescaped* single brace was intended, so the delimiters
leaked verbatim into the generated source. We also catch stray surrounding
doubled-brace pairs.

Repair is deterministic for the leak case: collapse each doubled brace back to
a single brace.

Scope: only *production source* is scanned. Documentation (``.md``),
test directories (``tests/``), fixtures (``fixtures/``) and demo/scratch
directories are excluded, because doubled braces there are usually a
legitimate literal (doc examples, test fixtures). This mirrors the "generator
hygiene" guard: scan generated artifacts, not docs/tests.
"""

from __future__ import annotations

import os

from .base import Healer, Fault, RepairResult

_TEXT_EXTS = (".py", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini")

# 目录/文件里出现双花括号（两个连续左花括号或两个连续右花括号）通常是
# 合法的（文档示例、测试夹具、故意样本），跳过。
_SKIP_DIR_NAMES = {"tests", "fixtures", "docs", "work", "analysis", "__pycache__",
                   ".git", ".venv", ".pytest_cache"}
_SKIP_FILE_NAMES = {"README.md", "self_heal_demo.py", "self_test.py",
                    "make_fixtures.py", "run_integration_demo.py",
                    "sample_leak.py",
                    # 自举排除：检测器自身源码必然含 "{{"/"}}" 字符串字面量
                    # （用于匹配），若不自排除会被自己误报并破坏检测逻辑。
                    "brace_escape.py"}


class BraceEscapeHealer(Healer):
    name = "brace_escape"

    def detect(self, target_dir: str):
        faults = []
        for p in self._iter_text_files(target_dir, exts=_TEXT_EXTS):
            rel = os.path.relpath(p, target_dir)
            parts = set(rel.replace("\\", "/").split("/"))
            if parts & _SKIP_DIR_NAMES:
                continue
            if os.path.basename(p) in _SKIP_FILE_NAMES:
                continue
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except Exception:
                continue
            if "{{" in text or "}}" in text:
                faults.append(Fault(
                    self.name, p,
                    "escape brace leak: literal '{{' or '}}' present in source"))
        return faults

    def repair(self, fault: Fault) -> RepairResult:
        with open(fault.path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new = text.replace("{{", "{").replace("}}", "}")
        with open(fault.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        return RepairResult(self.name, fault.path, True,
                            "collapsed '{{'->'{' and '}}'->'}'")
