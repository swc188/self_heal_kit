"""H7 — Integrity guard (trusted-baseline restore).

The other healers only recognise known *format* fault classes. This healer
closes the "unrecognised modification / malicious injection" gap: any byte
deviation from a trusted baseline is a fault, no matter what the content is.

Trusted baseline sources, in priority order:
  1. ``baseline.json`` in the target dir — a manifest of {relpath: sha256}
     (portable; created by ``make_baseline.py`` or ``integrity_guard.make_baseline``).
     When created with ``--with-bytes`` the manifest also embeds the trusted
     file bytes under ``__bytes__``, enabling byte-exact restore WITHOUT git.
  2. Git HEAD blobs — for a git worktree, the committed version of each tracked
     source file is the canonical "healthy" state.

Detection: scan the same text extensions as the other healers, compute sha256,
and compare with the baseline. Any missing / changed file is a fault. When
``detect_new_files=True`` (strict mode), files that exist on disk but are NOT
in the baseline are also reported — this catches viruses that drop new
malicious files into the program directory.

Repair: restore the baseline bytes (from baseline store or ``git show``).
This is deterministic and makes ANY detected modification repairable —
including syntactically-valid malicious logic injections. Deleted files are
recreated (parents included). Unexpected new files (strict mode) are moved to
a ``.quarantine/`` folder instead of being hard-deleted, so the action is
reversible and safe.

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

# Quarantine dir for unexpected files removed in strict mode.  Also added to
# base._SKIP_DIRS so the engine never scans/re-pairs quarantined files.
_QUARANTINE_DIR = ".quarantine"


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
                  exts=_TEXT_EXTS, with_bytes: bool = False) -> dict:
    """Compute a sha256 baseline for all in-scope text files under target_dir.

    Returns the manifest dict ``{relpath: sha256}`` and optionally writes it to
    ``manifest_path`` (default: ``<target_dir>/baseline.json``).

    When ``with_bytes`` is True the manifest also embeds the trusted bytes of
    every file under ``__bytes__``, enabling byte-exact restore without git.
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
    if with_bytes:
        store = {}
        for rel in manifest:
            p = os.path.join(target_dir, rel)
            try:
                with open(p, "rb") as fh:
                    store[rel] = fh.read().hex()
            except Exception:
                continue
        manifest = {"__bytes__": store, **manifest}
    if manifest_path is None:
        manifest_path = os.path.join(target_dir, "baseline.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return manifest


def _decode_bytes(raw) -> bytes | None:
    """Decode a baseline byte entry (hex string or raw bytes)."""
    if isinstance(raw, str):
        try:
            return bytes.fromhex(raw)
        except Exception:
            return None
    return raw if isinstance(raw, bytes) else None


class IntegrityGuardHealer(Healer):
    name = "integrity_guard"

    def __init__(self, baseline: dict | None = None,
                 detect_new_files: bool = False):
        # If a baseline dict is injected (tests / runtime), it wins.
        self._baseline = baseline
        # Strict mode: files not present in the baseline are reported as
        # faults too (catches viruses dropping new malicious files).
        self.detect_new_files = detect_new_files

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
        """Return trusted bytes for one baseline entry.

        Priority: injected baseline dict -> baseline.json on disk -> git HEAD.
        """
        # 1. Injected baseline dict (tests / runtime).
        if self._baseline is not None:
            raw = self._baseline.get("__bytes__", {}).get(relpath)
            if raw is not None:
                data = _decode_bytes(raw)
                if data is not None:
                    return data
        # 2. baseline.json on disk (with embedded bytes).
        manifest = _load_baseline_manifest(target_dir)
        if manifest is not None:
            raw = manifest.get("__bytes__", {}).get(relpath)
            if raw is not None:
                data = _decode_bytes(raw)
                if data is not None:
                    return data
        # 3. git HEAD blob. Allow subdirectory faults (e.g. --self scanning
        #    its own tests/) as long as the file is tracked in that repo.
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
            if rel == "baseline.json":
                # The manifest itself is metadata, not program source.
                continue
            seen.add(rel)
            expected = baseline.get(rel)
            if expected is None:
                # File not in baseline.
                if self.detect_new_files:
                    faults.append(Fault(
                        self.name, p,
                        f"unexpected file not in baseline ({rel})"))
                continue
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
        base_dir = self._find_target_root(fault.path)
        if base_dir is None:
            return RepairResult(self.name, fault.path, False,
                                "cannot locate trusted baseline (no git / "
                                "baseline.json found)")

        rel = os.path.relpath(fault.path, base_dir).replace("\\", "/")

        # Unexpected new file (strict mode) -> quarantine instead of delete.
        if fault.description.startswith("unexpected file not in baseline"):
            return self._quarantine_file(fault.path, base_dir, rel)

        data = self._baseline_bytes(base_dir, rel)
        if data is None:
            return RepairResult(self.name, fault.path, False,
                                f"no trusted baseline bytes for {rel}")

        try:
            # Recreate parent dirs (deleted-file scenario).
            os.makedirs(os.path.dirname(fault.path), exist_ok=True)
            with open(fault.path, "wb") as fh:
                fh.write(data)
        except Exception as e:
            return RepairResult(self.name, fault.path, False, f"write failed: {e}")
        return RepairResult(self.name, fault.path, True,
                            f"restored {rel} from trusted baseline")

    def _quarantine_file(self, path: str, base_dir: str,
                         rel: str) -> RepairResult:
        """Move an unexpected file into ``<base>/.quarantine/`` (reversible)."""
        try:
            qdir = os.path.join(base_dir, _QUARANTINE_DIR)
            dest = os.path.join(qdir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(path, dest)
        except Exception as e:
            return RepairResult(self.name, path, False,
                                f"quarantine failed: {e}")
        return RepairResult(self.name, path, True,
                            f"quarantined unexpected file {rel}")

    def _find_target_root(self, path: str) -> str | None:
        """Find the directory whose baseline.json / git root governs ``path``.

        Priority: the NEAREST directory containing a ``baseline.json`` — that
        is the most specific integrity scope for this file (e.g. a drill copy
        under ``work/`` has its own baseline.json and must NOT fall back to an
        outer repository). Only when no baseline.json exists do we fall back to
        a git worktree root (the ``--self`` case).
        """
        d = os.path.dirname(path)
        start = d
        while True:
            if os.path.isfile(os.path.join(d, "baseline.json")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        # No baseline.json anywhere above -> fall back to git root.
        repo = _git_root(start)
        if repo:
            return repo
        return None