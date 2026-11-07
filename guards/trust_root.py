"""Trust root — out-of-band sealing of baseline files, and snapshot helpers.

The manifest seal (``__seal__``) inside ``baseline.json`` proves internal
consistency, but an attacker who edits the baseline can recompute the seal too
— same disk, same algorithm. The missing piece is a trust anchor the attacker
has to touch *in a second, separate place*: this module writes a small
"anchor" file recording ``sha256(baseline)`` to an **out-of-band path** (a
different volume / read-only share / backup). Verification then answers one
question: *does the on-disk baseline still hash to what the anchor says?*

Honest limit (documented in THREAT_MODEL.md): hash-level, not key-level.
If the attacker also has write access to the anchor location, they can
re-seal. Mitigations are operational (read-only mount, remote copy), not
cryptographic. This is still strictly stronger than a self-sealed manifest
because compromising the chain now requires two independent writes.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

__all__ = ["sha256_file", "seal_file", "verify_file",
           "snapshot_path", "list_snapshots", "promote_snapshot"]


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def seal_file(baseline_path: str, anchor_path: str) -> dict:
    """Record sha256(``baseline_path``) into ``anchor_path`` (created/overwritten).

    The anchor is a plain JSON file — put it somewhere the writer of the
    baseline cannot casually reach (read-only mount, remote, backup).
    """
    if not os.path.isfile(baseline_path):
        raise FileNotFoundError(baseline_path)
    record = {
        "baseline": os.path.abspath(baseline_path),
        "sha256": sha256_file(baseline_path),
        "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    d = os.path.dirname(os.path.abspath(anchor_path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(anchor_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return record


def verify_file(baseline_path: str, anchor_path: str):
    """Return ``(ok: bool, detail: str)`` comparing baseline vs anchor."""
    if not os.path.isfile(anchor_path):
        return False, f"anchor missing: {anchor_path}"
    if not os.path.isfile(baseline_path):
        return False, f"baseline missing: {baseline_path}"
    try:
        with open(anchor_path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except Exception as e:
        return False, f"anchor unreadable: {e}"
    expected = rec.get("sha256")
    if not expected:
        return False, "anchor has no sha256 field"
    actual = sha256_file(baseline_path)
    if actual == expected:
        return True, f"baseline matches anchor ({actual[:12]}…)"
    return False, (f"TRUST ANCHOR BROKEN — baseline sha256 {actual[:12]}… "
                   f"!= anchor {expected[:12]}…")


# ---------------------------------------------------------------------------
# Snapshots — baselines/<name>.json, any number, promoted to baseline.json
# ---------------------------------------------------------------------------

SNAPSHOT_DIRNAME = "baselines"


def snapshot_path(target_dir: str, name: str) -> str:
    safe = name.strip().strip("/")
    if not safe or "/" in safe or "\\" in safe or safe.startswith("."):
        raise ValueError(f"invalid snapshot name: {name!r}")
    return os.path.join(target_dir, SNAPSHOT_DIRNAME, safe + ".json")


def list_snapshots(target_dir: str) -> list:
    d = os.path.join(target_dir, SNAPSHOT_DIRNAME)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-len(".json")] for f in os.listdir(d)
                  if f.endswith(".json"))


def promote_snapshot(target_dir: str, name: str) -> str:
    """Copy baselines/<name>.json over <target>/baseline.json, return dst path."""
    import shutil
    src = snapshot_path(target_dir, name)
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    dst = os.path.join(target_dir, "baseline.json")
    shutil.copyfile(src, dst)
    return dst
