"""H2 — Brace / escape leak detector.

A classic fault class: an f-string or template literal wrote
``{{`` / ``}}`` where the *unescaped* ``{`` / ``}`` was intended, so the
delimiters leaked verbatim into the generated source. We also catch stray
surrounding ``{{ }}`` pairs.

Repair is deterministic for the leak case: collapse ``{{`` -> ``{`` and
``}}`` -> ``}``. (A production tool would scope this to template/f-string
contexts; this kit demonstrates the detect->fix->verify closed loop.)
"""

from __future__ import annotations

from .base import Healer, Fault, RepairResult

_TEXT_EXTS = (".py", ".txt", ".md", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini")


class BraceEscapeHealer(Healer):
    name = "brace_escape"

    def detect(self, target_dir: str) -> List[Fault]:
        faults = []
        for p in self._iter_text_files(target_dir, exts=_TEXT_EXTS):
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
