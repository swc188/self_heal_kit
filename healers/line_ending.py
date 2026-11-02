"""H1 — Line ending normalizer (CRLF -> LF, strip UTF-8 BOM).

A common fault: a file written without an explicit newline lets CRLF/LF drift
with the platform, so the on-disk bytes differ between machines and a documented
claim no longer matches the implementation. The fix is deterministic: normalise
to ``newline="\n"`` (LF, no BOM).
"""

from __future__ import annotations

from .base import Healer, Fault, RepairResult

_BOM = b"\xef\xbb\xbf"


class LineEndingHealer(Healer):
    name = "line_ending"

    def detect(self, target_dir: str) -> List[Fault]:
        faults = []
        for p in self._iter_text_files(target_dir):
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except Exception:
                continue
            has_crlf = b"\r\n" in data
            has_bom = data.startswith(_BOM)
            if has_crlf or has_bom:
                bits = []
                if has_crlf:
                    bits.append("CRLF line endings")
                if has_bom:
                    bits.append("UTF-8 BOM")
                faults.append(Fault(self.name, p, "; ".join(bits)))
        return faults

    def repair(self, fault: Fault) -> RepairResult:
        with open(fault.path, "rb") as fh:
            data = fh.read()
        # utf-8-sig transparently strips a leading BOM, then we normalize EOL.
        text = data.decode("utf-8-sig", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        with open(fault.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return RepairResult(self.name, fault.path, True,
                            "normalized to LF, no BOM")
