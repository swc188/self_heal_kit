"""H5 — Key / mapping-gap filler (provenance: loop-framework v3.10.1, v3.22.0).

Two real faults in loop-framework-skill:
  * v3.10.1 — matching used a display name ("区块链 / Web3") to look up a
    generator keyed by "blockchain"; the lookup always missed, silently
    downgrading every hit.
  * v3.22.0 — Chinese terms ("列表 / 列举 / 列出") never mapped to the canonical
    method name "list_keys", so evidence search returned nothing.

Both are the same shape: "a known alias is present but its canonical key is
missing". This healer detects rows in a ``.csv`` alias table where the term is a
known alias but the canonical column is empty, and fills the canonical from a
built-in table.
"""

from __future__ import annotations

import csv
import io

from .base import Healer, Fault, RepairResult

# Built-in alias -> canonical key table (mirrors loop's _CN_TERM_MAP / domain_key).
ALIASES = {
    "区块链 / Web3": "blockchain",
    "区块链": "blockchain",
    "Web3": "blockchain",
    "列表": "list_keys",
    "列举": "list_keys",
    "列出": "list_keys",
}


class KeyMapGapHealer(Healer):
    name = "key_map_gap"

    def detect(self, target_dir: str) -> list:
        faults = []
        for p in self._iter_text_files(target_dir, exts=(".csv",)):
            try:
                with open(p, "r", encoding="utf-8", newline="") as fh:
                    rows = list(csv.DictReader(fh))
            except Exception:
                continue
            if not rows or "term" not in rows[0] or "canonical" not in rows[0]:
                continue
            for row in rows:
                term = (row.get("term") or "").strip()
                canonical = (row.get("canonical") or "").strip()
                if term in ALIASES and not canonical:
                    faults.append(Fault(
                        self.name, p,
                        f"alias '{term}' has empty canonical key"))
        return faults

    def repair(self, fault: Fault) -> RepairResult:
        with open(fault.path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames
            rows = list(reader)
        for row in rows:
            term = (row.get("term") or "").strip()
            canonical = (row.get("canonical") or "").strip()
            if term in ALIASES and not canonical:
                row["canonical"] = ALIASES[term]
        buf = io.StringIO()
        # Pin LF: csv's default lineterminator is "\r\n", which would
        # re-introduce CRLF and fight the line_ending healer.
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        with open(fault.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(buf.getvalue())
        return RepairResult(self.name, fault.path, True,
                            "filled missing canonical keys")
