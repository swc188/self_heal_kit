"""H4 — Quote-balance normalizer.

A line in a simple ``key = "value"`` config-style file whose double quotes are
unbalanced (a missing closing quote), which leaks the rest of the line / file
into one string.

Deterministic repair: append the missing closing quote on lines that have an
odd count of ``"`` within scope.

Scope is intentionally narrow (config / ini-style files) so we never touch
source code or JSON, where an odd quote count can be legitimate.
"""

from __future__ import annotations

from .base import Healer, Fault, RepairResult

_CFG_EXTS = (".cfg", ".ini", ".conf", ".properties")


class QuoteBalanceHealer(Healer):
    name = "quote_balance"

    def detect(self, target_dir: str) -> list:
        faults = []
        for p in self._iter_text_files(target_dir, exts=_CFG_EXTS):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except Exception:
                continue
            bad = []
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                if line.count('"') % 2 == 1:
                    bad.append(i)
            if bad:
                faults.append(Fault(
                    self.name, p,
                    f"unbalanced double quotes on line(s) {bad}"))
        return faults

    def repair(self, fault: Fault) -> RepairResult:
        with open(fault.path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        out = []
        for line in lines:
            if line.lstrip().startswith("#") or line.count('"') % 2 == 0:
                out.append(line)
            else:
                # append the missing closing quote
                out.append(line.rstrip("\n").rstrip("\r") + '"\n')
        with open(fault.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(out))
        return RepairResult(self.name, fault.path, True,
                            "balanced double quotes")
