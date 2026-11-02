"""H7 — Integrity guard (trusted-baseline restore).

The other healers only recognise known *format* fault classes. This healer
closes the "unrecognised modification / malicious injection" gap: any byte
deviation from a trusted baseline is a fault, no matter what the content is.

Trusted baseline sources, in priority order:
  1. ``baseline.json`` in the target dir — a manifest of {relpath: sha256}
     (portable; created by ``make_baseline.py`` or ``integrity_guard.make_baseline``).
  2. Git HEAD blobs — for a git worktree, the committed version of each tracked
     source file is the canonical "healthy" state.

Detection: scan the same text extensions as the other healers, compute sha256,
and compare with the baseline. Any missing / extra / changed file is a fault
(repairable=True unless the file has no baseline entry).

Repair: restore the baseline bytes (from baseline store or ``git show``).
This is deterministic and makes ANY detected modification repairable —
including syntactically-valid malicious logic injections.

Scope mirrors the kit's other healers: production source only; demo/scratch
directories and tool caches are excluded (see base._SKIP_DIRS).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

from .base import Healer, Fault, RepairResult

_TEXT_EXTS = (".py", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini",
              ".md", ".csv")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return _sha256_bytes(fh.read())


def _git_root(path: str) -> str | None:
    """Return the git worktree root containing ``path``, or None."""
    try:
        r = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _git_root_exact(path: str) -> str | None:
    """Return the git root ONLY if ``path`` IS the worktree root.

    This prevents a subdirectory (e.g. a drill copy under work/) from using
    an outer repository's HEAD as its integrity baseline.
    """
    root = _git_root(path)
    if root is None:
        return None
    try:
        if os.path.abspath(path) == os.path.abspath(root):
            return root
    except Exception:
        return None
    return None


def _git_show_blob(repo: str, relpath: str) -> bytes | None:
    """Return the committed (HEAD) bytes of a tracked file."""
    try:
        r = subprocess.run(
            ["git", "-C", repo, "show", f"HEAD:{relpath}"],
            capture_output=True, timeout=30)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def _load_baseline_manifest(target_dir: str) -> dict | None:
    p = os.path.join(target_dir, "baseline.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def make_baseline(target_dir: str, manifest_path: str | None = None,
                  exts=_TEXT_EXTS) -> dict:
    """Compute a sha256 baseline for all in-scope text files under target_dir.

    Returns the manifest dict ``{relpath: sha256}`` and optionally writes it to
    ``manifest_path`` (default: ``<target_dir>/baseline.json``).
    """
    from .base import _SKIP_DIRS
    manifest = {}
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            p = os.path.join(root, fn)
            if not any(p.endswith(e) for e in exts):
                continue
            rel = os.path.relpath(p, target_dir).replace("\\", "/")
            manifest[rel] = _sha256_file(p)
    if manifest_path is None:
        manifest_path = os.path.join(target_dir, "baseline.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return manifest


class IntegrityGuardHealer(Healer):
    name = "integrity_guard"

    def __init__(self, baseline: dict | None = None):
        # If a baseline dict is injected (tests / runtime), it wins.
        self._baseline = baseline

    # -- baseline resolution ------------------------------------------------
    def _resolve_baseline(self, target_dir: str) -> dict | None:
        if self._baseline is not None:
            return self._baseline
        manifest = _load_baseline_manifest(target_dir)
        if manifest is not None:
            return manifest
        # Fall back: build the hash manifest from git HEAD for this worktree.
        return self._git_baseline(target_dir)

    def _git_baseline(self, target_dir: str) -> dict | None:
        """Build {relpath: sha256} from `git ls-tree -r HEAD`.

        Only used when target_dir IS the git worktree root (not a subdir).
        """
        repo = _git_root_exact(target_dir)
        if repo is None:
            return None
        try:
            r = subprocess.run(
                ["git", "-C", repo, "ls-tree", "-r", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return None
        except Exception:
            return None
        manifest = {}
        for rel in r.stdout.splitlines():
            if not rel.endswith(_TEXT_EXTS):
                continue
            blob = _git_show_blob(repo, rel)
            if blob is None:
                continue
            manifest[rel] = _sha256_bytes(blob)
        return manifest

    def _baseline_bytes(self, target_dir: str, relpath: str) -> bytes | None:
        """Return trusted bytes for one baseline entry."""
        if self._baseline is not None:
            raw = self._baseline.get("__bytes__", {}).get(relpath)
            if raw is None:
                return None
            if isinstance(raw, str):
                # stored as hex string (make_baseline.py --with-bytes)
                try:
                    return bytes.fromhex(raw)
                except Exception:
                    return None
            return raw if isinstance(raw, bytes) else None
        # Try git HEAD blob. Allow subdirectory faults (e.g. --self scanning
        # its own tests/) as long as the file is tracked in that repo.
        repo = _git_root(target_dir)
        if repo:
            return _git_show_blob(repo, relpath)
        return None

    # -- detect -------------------------------------------------------------
    def detect(self, target_dir: str):
        faults = []
        baseline = self._resolve_baseline(target_dir)
        if baseline is None:
            # No baseline available -> cannot assert integrity (not a fault).
            return faults

        # Build the set of files we can meaningfully check.
        seen = set()
        for p in self._iter_text_files(target_dir, exts=_TEXT_EXTS):
            rel = os.path.relpath(p, target_dir).replace("\\", "/")
            seen.add(rel)
            expected = baseline.get(rel)
            if expected is None:
                continue  # file not in baseline -> ignore (untracked/extra)
            actual = _sha256_file(p)
            if actual != expected:
                faults.append(Fault(
                    self.name, p,
                    f"integrity deviation: sha256 {actual[:12]} != "
                    f"baseline {expected[:12]}"))

        # Files present in baseline but missing on disk.
        for rel, expected in baseline.items():
            if rel == "__bytes__":
                continue
            p = os.path.join(target_dir, rel)
            if not os.path.exists(p):
                faults.append(Fault(
                    self.name, p,
                    f"integrity deviation: baseline file missing ({rel})"))

        return faults

    # -- repair -------------------------------------------------------------
    def repair(self, fault: Fault) -> RepairResult:
        target_dir = fault.path  # path is the file; we need the target root
        # The fault.path is absolute; derive target_dir as the git root or
        # the directory containing the baseline manifest.
        # Fall back: walk up from the file until we find baseline.json / git.
        base_dir = self._find_target_root(fault.path)
        if base_dir is None:
            return RepairResult(self.name, fault.path, False,
                                "cannot locate trusted baseline (no git / "
                                "baseline.json found)")

        rel = os.path.relpath(fault.path, base_dir).replace("\\", "/")
        data = self._baseline_bytes(base_dir, rel)
        if data is None:
            return RepairResult(self.name, fault.path, False,
                                f"no trusted baseline bytes for {rel}")

        try:
            with open(fault.path, "wb") as fh:
                fh.write(data)
        except Exception as e:
            return RepairResult(self.name, fault.path, False, f"write failed: {e}")
        return RepairResult(self.name, fault.path, True,
                            f"restored {rel} from trusted baseline")

    def _find_target_root(self, path: str) -> str | None:
        """Find the directory whose baseline.json / git root governs ``path``."""
        d = os.path.dirname(path)
        # Climb up to find baseline.json or a git root.
        repo = _git_root(d)
        if repo:
            return repo
        while True:
            if os.path.isfile(os.path.join(d, "baseline.json")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                return None
            d = parent