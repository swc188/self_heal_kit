"""H3 — Fake-YAML detector.

A file carrying a ``.yaml`` / ``.yml`` extension whose body is actually JSON
(a ``to_yaml`` helper emitted a JSON dump by mistake). Detect by attempting a
strict ``json.loads``; if it succeeds the file is *not* real YAML. Repair
converts the JSON object into a minimal, valid YAML document without any
third-party lib.
"""

from __future__ import annotations

import json

from .base import Healer, Fault, RepairResult

_YAML_EXTS = (".yaml", ".yml")


class YamlFormatHealer(Healer):
    name = "yaml_format"

    def detect(self, target_dir: str) -> List[Fault]:
        faults = []
        for p in self._iter_text_files(target_dir, exts=_YAML_EXTS):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    text = fh.read().strip()
            except Exception:
                continue
            if not text:
                continue
            try:
                json.loads(text)
            except Exception:
                continue  # not JSON -> assume genuine YAML
            faults.append(Fault(
                self.name, p,
                ".yaml extension but content is JSON (fake YAML)"))
        return faults

    def repair(self, fault: Fault) -> RepairResult:
        with open(fault.path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        obj = json.loads(text)
        yaml_text = _json_to_yaml(obj)
        with open(fault.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(yaml_text)
        return RepairResult(self.name, fault.path, True,
                            "converted JSON body to valid YAML")


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, str):
        return f'"{v}"' if (":" in v or "#" in v or v == "" or "," in v) else v
    return str(v)


def _json_to_yaml(obj, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(_json_to_yaml(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_scalar(v)}")
        return "\n".join(lines) + "\n"
    if isinstance(obj, list):
        lines = []
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_json_to_yaml(item, indent + 1))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return "\n".join(lines) + "\n"
    return f"{pad}{_scalar(obj)}\n"

# backdoor injected
