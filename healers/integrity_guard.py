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

Detection covers, relative to a trusted baseline, four fault kinds:
  * TAMPER  — a baseline file's bytes changed (incl. syntactically-valid
              malicious logic injections that format healers cannot see).
  * DELETE  — a baseline file is missing on disk.
  * ADD     — a file exists that is NOT in the baseline (strict mode only,
              with a whitelist of known-good new artefacts to avoid false
              positives on benign additions).
  * SEAL    — the baseline manifest itself was tampered (its hash seal does
              not match), which would otherwise silently defeat TAMPER/DELETE.

Repair:
  * TAMPER / DELETE -> restore the baseline bytes (from ``__bytes__`` or git
    HEAD). Deterministic, makes ANY detected modification repairable.
  * ADD -> move to ``.quarantine/`` instead of hard-deleting (reversible).
  * SEAL -> restore ``baseline.json`` from git HEAD when available.

Scope mirrors the kit's other healers: production source only; demo/scratch
directories and tool caches are excluded (see base._SKIP_DIRS).

Known limits (honest): the seal protects against accidental corruption and
unsophisticated tampering of the manifest; a sophisticated attacker who edits
both the target file AND the manifest hash AND the seal can defeat it — true
root-of-trust needs an external key / out-of-band storage. Likewise, files
outside ``_TEXT_EXTS`` / ``_SKIP_DIRS``, runtime-memory injection, permissions
and symlink substitution are out of scope (see README).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
import subprocess

from .base import Healer, Fault, RepairResult, _BINARY_EXTS

# Extended scope: source / config / script files whose integrity matters.
# (Binaries are excluded by base._BINARY_EXTS and never scanned.)
_TEXT_EXTS = (".py", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini",
              ".md", ".csv", ".xml", ".html", ".css", ".env",
              ".sh", ".bat", ".cmd", ".ps1")

# Quarantine dir for unexpected files removed in strict mode.  Also added to
# base._SKIP_DIRS so the engine never scans/re-pairs quarantined files.
_QUARANTINE_DIR = ".quarantine"

# Default whitelist of path patterns that are NOT treated as malicious "new"
# files even in strict mode. These are volatile / generated / known-safe
# artefacts. A genuinely unexpected new file (e.g. a dropped evil.py) is still
# flagged. Patterns:
#   "x/"        -> any file at or under directory x
#   "*.ext"     -> any file with that extension, anywhere
#   "exact/rel" -> an exact relative path
DEFAULT_NEW_FILE_WHITELIST = {
    "baseline.json",
    "*.log", "*.tmp", "*.bak", "*.swp", "*.orig", "*.pyc", "*.pyo",
    ".venv/", "venv/", "env/", "node_modules/",
    "dist/", "build/", "*.egg-info/", "*.dist-info/",
    "__pycache__/", ".pytest_cache/", ".mypy_cache/",
    ".tox/", ".git/", "work/", ".quarantine/", ".workbuddy/", "baselines/",
    "fixtures/", "demo_project/", "analysis/", "docs/",
    "examples/", "testdata/", "sample_data/",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return _sha256_bytes(fh.read())


def _git_root(path: str) -> str | None:
    """Return the git worktree root containing ``path``, or None."""
    try:
        # Decode as UTF-8 explicitly: on Windows ``text=True`` would use the
        # locale codepage (e.g. GBK) and mangle non-ASCII repo paths.
        r = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, timeout=30)
        if r.returncode == 0:
            root = r.stdout.decode("utf-8", "replace").strip()
            return root or None
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


def _seal_manifest(manifest: dict) -> str:
    """Hash-seal the manifest (excluding the seal and embedded bytes).

    Tampering with any tracked file's hash in the manifest breaks this seal,
    so an attacker cannot silently re-point the baseline at malicious bytes.
    ``__bytes__`` is excluded from the seal to keep it stable / lightweight.
    """
    core = {k: v for k, v in manifest.items()
            if k not in ("__seal__", "__bytes__")}
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_baseline_manifest(target_dir: str) -> dict | None:
    p = os.path.join(target_dir, "baseline.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    if isinstance(data, dict) and "__seal__" in data:
        if data.get("__seal__") != _seal_manifest(data):
            data = dict(data)
            data["__tampered__"] = True
    return data


def make_baseline(target_dir: str, manifest_path: str | None = None,
                  exts=_TEXT_EXTS, with_bytes: bool = False,
                  scan_binaries: bool = False,
                  check_metadata: bool = False,
                  scope_roots: list | None = None) -> dict:
    """Compute a sha256 baseline for all in-scope files under target_dir.

    Returns the manifest dict ``{relpath: sha256}`` and writes it to
    ``manifest_path`` (default: ``<target_dir>/baseline.json``). The manifest is
    hash-sealed (``__seal__``) so that tampering with it is itself detectable.

    Options:
      * ``with_bytes`` — also embed the trusted bytes of every file under
        ``__bytes__``, enabling byte-exact restore WITHOUT git.
      * ``scan_binaries`` — also include binary artefacts (``.exe``/``.dll``/
        ``.so``/``.bin``/...) in the baseline so they get integrity protection
        too. By default binaries are skipped (they rarely change and bloat the
        manifest).
      * ``check_metadata`` — additionally record each file's permission mode and
        whether it is a symlink under ``__meta__``; deviations are then detected
        and the permission mode is auto-restored.
      * ``scope_roots`` — restrict the baseline to files under these relative
        roots (e.g. ``[".agent", "generated"]``). Used by agent-guard mode so
        the manifest only describes the agent workspace instead of the whole
        host project.
    """
    from .base import _is_skipped_dir
    manifest = {}
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if not _is_skipped_dir(d)]
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, target_dir).replace("\\", "/")
            # The manifest is metadata, not program source. Baselining itself
            # is meaningless (its hash changes on every regeneration) and
            # actively harmful: with_bytes would hex-embed the PREVIOUS
            # manifest, roughly DOUBLING baseline.json on each regeneration
            # (4 MB -> 8 MB -> 17 MB ...). It is protected by __seal__ and the
            # out-of-band trust anchor instead; detect() already skips it.
            if rel == "baseline.json":
                continue
            # Agent-guard scope: only baselined roots (when configured).
            if scope_roots and not _is_under(rel, scope_roots):
                continue
            if not scan_binaries:
                # Default: skip binaries and only keep known text/source exts.
                if any(p.endswith(e) for e in _BINARY_EXTS):
                    continue
                if not any(p.endswith(e) for e in exts):
                    continue
            manifest[rel] = _sha256_file(p)
    if check_metadata:
        meta = {}
        for rel in manifest:
            p = os.path.join(target_dir, rel)
            try:
                st = os.lstat(p)
                meta[rel] = {
                    "mode": stat.S_IMODE(st.st_mode),
                    "link": os.path.islink(p),
                }
            except Exception:
                continue
        manifest["__meta__"] = meta
    if with_bytes:
        store = {}
        for rel in manifest:
            if rel.startswith("__") or rel == "baseline.json":
                continue
            p = os.path.join(target_dir, rel)
            try:
                with open(p, "rb") as fh:
                    store[rel] = fh.read().hex()
            except Exception:
                continue
        manifest["__bytes__"] = store
    # Seal AFTER assembling all entries (incl. __meta__ and __bytes__).
    manifest["__seal__"] = _seal_manifest(manifest)
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


def _is_under(rel: str, roots: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    for root in roots:
        root = root.strip().strip("/").replace("\\", "/")
        if not root:
            continue
        if rel == root or rel.startswith(root + "/"):
            return True
    return False


def _is_whitelisted(rel: str, whitelist) -> bool:
    # Normalise Windows separators to "/".
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    for pat in whitelist:
        if pat.endswith("/"):
            # Directory pattern: match the named directory at ANY nesting
            # level (e.g. ".pytest_cache/" must cover both ".pytest_cache/..."
            # and "tests/.pytest_cache/..."). A component match is enough
            # because any file under that directory carries the component in
            # its relpath.
            stem = pat[:-1]
            # fnmatch keeps exact directory names behaving exactly as before
            # while also allowing patterns such as "*.egg-info/".
            if any(fnmatch.fnmatch(p, stem) for p in parts):
                return True
        elif pat.startswith("*."):
            if rel.endswith(pat[1:]):
                return True
        else:
            if rel == pat:
                return True
    return False


class IntegrityGuardHealer(Healer):
    name = "integrity_guard"

    def __init__(self, baseline: dict | None = None,
                 detect_new_files: bool = False,
                 new_file_whitelist: set | None = None,
                 scan_binaries: bool = False,
                 check_metadata: bool = False,
                 agent_guard: bool = False,
                 agent_guard_roots: list | None = None):
        # If a baseline dict is injected (tests / runtime), it wins.
        self._baseline = baseline
        # Strict mode: files not present in the baseline are reported as
        # faults too (catches viruses dropping new malicious files).
        self.detect_new_files = detect_new_files
        # Whitelist of known-good new file patterns (strict mode only).
        self.new_file_whitelist = new_file_whitelist
        # Include binary artefacts (.exe/.dll/.so/...) in integrity scope.
        self.scan_binaries = scan_binaries
        # Detect/restore permission-mode and symlink-substitution changes.
        self.check_metadata = check_metadata
        # Agent-guard: when enabled, ONLY files under one of agent_guard_roots
        # are in scope (TAMPER / DELETE / ADD / metadata). Everything else is
        # ignored. Rationale: an AI agent usually lives inside a large or
        # unrelated project; guarding the whole thing produces noise. This
        # narrows the blast radius to the workspace the agent actually writes
        # to (e.g. ``.agent/`` or ``generated/``).
        self.agent_guard = agent_guard
        self.agent_guard_roots = list(agent_guard_roots or [])
        # Remembered from the last detect(): an INJECTED baseline (tests /
        # library use) has no baseline.json on disk, so repair() cannot resolve
        # the base directory from the filesystem and needs this instead.
        self._last_target = None
        # Set during detect() when the on-disk manifest seal is broken.
        self._baseline_tampered = False

    # -- helpers -------------------------------------------------------------
    def _eff_whitelist(self):
        return self.new_file_whitelist or DEFAULT_NEW_FILE_WHITELIST

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
        Uses ``core.quotepath=false`` + UTF-8 decoding so non-ASCII
        filenames (e.g. Chinese-named reports) are captured instead of being
        silently escaped (``\\345...``) and dropped by the ``.endswith`` check.
        """
        repo = _git_root_exact(target_dir)
        if repo is None:
            return None
        try:
            r = subprocess.run(
                ["git", "-c", "core.quotepath=false", "-C", repo,
                 "ls-tree", "-r", "--name-only", "HEAD"],
                capture_output=True, timeout=30)
            if r.returncode != 0:
                return None
        except Exception:
            return None
        text = r.stdout.decode("utf-8", "replace")
        manifest = {}
        for rel in text.splitlines():
            rel = rel.strip()
            if not rel or not rel.endswith(_TEXT_EXTS):
                continue
            blob = _git_show_blob(repo, rel)
            if blob is None:
                continue
            manifest[rel] = _sha256_bytes(blob)
        return manifest

    def _baseline_bytes(self, target_dir: str, relpath: str) -> bytes | None:
        """Return trusted bytes for one baseline entry.

        Priority: injected baseline dict -> baseline.json on disk (trusted
        unless its seal is broken) -> git HEAD (last resort).

        This mirrors ``_resolve_baseline``: when a ``baseline.json`` governs
        the target, its embedded ``__bytes__`` are authoritative; git HEAD is
        only used when no trusted disk baseline exists. Preferring the disk
        manifest over git HEAD matters because a target may sit *inside* a git
        repo (e.g. a drill copy under ``work/``) while carrying its own
        ``baseline.json`` — using the outer repo's HEAD bytes would restore
        out-of-sync content and the repair would never converge.
        """
        # 1. Injected baseline dict (tests / runtime).
        if self._baseline is not None:
            raw = self._baseline.get("__bytes__", {}).get(relpath)
            if raw is not None:
                data = _decode_bytes(raw)
                if data is not None:
                    return data
        # 2. baseline.json on disk (trusted unless its seal is broken).
        if not self._baseline_tampered:
            manifest = _load_baseline_manifest(target_dir)
            if manifest is not None:
                raw = manifest.get("__bytes__", {}).get(relpath)
                if raw is not None:
                    data = _decode_bytes(raw)
                    if data is not None:
                        return data
        # 3. git HEAD blob (last resort). Used when no trusted disk baseline
        #    exists and the file is tracked in the enclosing repo.
        repo = _git_root(target_dir)
        if repo:
            blob = _git_show_blob(repo, relpath)
            if blob is not None:
                return blob
        return None

    def _in_scope(self, rel: str) -> bool:
        """Return True when ``rel`` is inside the guarded scope.

        Normal mode protects everything the baseline covers. Agent-guard mode
        protects ONLY files under one of ``agent_guard_roots`` — this keeps a
        large host project (and its tool caches) free of false positives while
        still locking down the workspace the agent actually writes to. With no
        roots configured nothing is in scope (fail-safe: guard nothing rather
        than silently guarding the whole tree).
        """
        if not self.agent_guard:
            return True
        return _is_under(rel, self.agent_guard_roots)

    # -- detect -------------------------------------------------------------
    def detect(self, target_dir: str):
        self._last_target = target_dir
        faults = []
        baseline = self._resolve_baseline(target_dir)
        if baseline is None:
            # No baseline available -> cannot assert integrity (not a fault).
            return faults

        # Trust-anchor fault: the manifest itself was tampered.
        self._baseline_tampered = bool(baseline.get("__tampered__"))
        if self._baseline_tampered:
            faults.append(Fault(
                self.name, os.path.join(target_dir, "baseline.json"),
                "integrity deviation: baseline.json seal mismatch — "
                "trust anchor compromised"))

        # Files present on disk: TAMPER (changed) or ADD (unexpected, strict).
        seen = set()
        scan_exts = None if self.scan_binaries else _TEXT_EXTS
        for p in self._iter_text_files(target_dir, exts=scan_exts,
                                       exclude_binary=not self.scan_binaries):
            rel = os.path.relpath(p, target_dir).replace("\\", "/")
            if rel == "baseline.json":
                # The manifest itself is metadata, not program source.
                continue
            if not self._in_scope(rel):
                # Agent-guard: ignore files outside the guarded workspace.
                continue
            seen.add(rel)
            expected = baseline.get(rel)
            if expected is None:
                # File not in baseline.
                if self.detect_new_files and not _is_whitelisted(
                        rel, self._eff_whitelist()):
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

        # Metadata deviations (permission mode / symlink substitution).
        if self.check_metadata:
            meta = baseline.get("__meta__") or {}
            for rel, m in meta.items():
                if not self._in_scope(rel):
                    continue
                p = os.path.join(target_dir, rel)
                if not os.path.exists(p):
                    continue  # missing file handled by DELETE branch below
                try:
                    st = os.lstat(p)
                    is_link = os.path.islink(p)
                    was_link = m.get("link", False)
                    if was_link and not is_link:
                        faults.append(Fault(
                            self.name, p,
                            f"metadata deviation: baseline symlink {rel} "
                            f"replaced by a regular file"))
                        continue
                    if (not was_link) and is_link:
                        faults.append(Fault(
                            self.name, p,
                            f"metadata deviation: {rel} replaced by a symlink"))
                        continue
                    if stat.S_IMODE(st.st_mode) != m.get("mode"):
                        faults.append(Fault(
                            self.name, p,
                            "metadata deviation: permission mode changed "
                            f"{oct(stat.S_IMODE(st.st_mode))} != baseline "
                            f"{oct(m.get('mode'))}"))
                except Exception:
                    continue

        # Files present in baseline but missing on disk (DELETE).
        for rel, expected in baseline.items():
            if rel in ("__bytes__", "__seal__", "__tampered__", "__meta__"):
                continue
            if not self._in_scope(rel):
                # Agent-guard: a baseline entry outside the workspace is not
                # this guard's business (the host project owns it).
                continue
            p = os.path.join(target_dir, rel)
            if not os.path.exists(p):
                faults.append(Fault(
                    self.name, p,
                    f"integrity deviation: baseline file missing ({rel})"))

        return faults

    # -- repair -------------------------------------------------------------
    def repair(self, fault: Fault) -> RepairResult:
        # Preferred root: the directory the last detect() scanned. detect()
        # resolved its baseline FROM that directory (its own baseline.json or
        # ITS OWN git root via _git_root_exact), so repairing relative to the
        # same root is consistent with what was compared. Without this, a
        # drill copy whose baseline is its own git HEAD would walk up and
        # find an OUTER baseline.json (different project!) and fail.
        base_dir = None
        last = getattr(self, "_last_target", None)
        if last and os.path.isdir(last):
            try:
                rel_chk = os.path.relpath(fault.path, last)
                if not rel_chk.startswith(".."):
                    base_dir = last
            except Exception:
                pass
        if base_dir is None:
            base_dir = self._find_target_root(fault.path)
        if base_dir is None and self._baseline is not None:
            # Injected baseline (tests / library use): there is no
            # baseline.json on disk to locate, so fall back to the directory
            # the last detect() scanned.
            base_dir = self._last_target
        if base_dir is None:
            return RepairResult(self.name, fault.path, False,
                                "cannot locate trusted baseline (no git / "
                                "baseline.json found)")

        rel = os.path.relpath(fault.path, base_dir).replace("\\", "/")

        # Trust-anchor fault: try to restore baseline.json from git HEAD.
        if fault.description.startswith(
                "integrity deviation: baseline.json seal mismatch"):
            repo = _git_root(base_dir)
            if repo:
                blob = _git_show_blob(repo, rel)  # rel == "baseline.json"
                if blob is not None:
                    try:
                        with open(fault.path, "wb") as fh:
                            fh.write(blob)
                        return RepairResult(self.name, fault.path, True,
                                            "restored baseline.json from git HEAD")
                    except Exception as e:
                        return RepairResult(self.name, fault.path, False,
                                            f"write failed: {e}")
            return RepairResult(self.name, fault.path, False,
                                "baseline.json tampered and no git source to "
                                "restore from")

        # Unexpected new file (strict mode) -> quarantine instead of delete.
        if fault.description.startswith("unexpected file not in baseline"):
            return self._quarantine_file(fault.path, base_dir, rel)

        # Metadata deviation (permission mode / symlink substitution).
        if fault.description.startswith("metadata deviation:"):
            return self._repair_metadata(fault, base_dir, rel)

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

    def _repair_metadata(self, fault: Fault, base_dir: str,
                         rel: str) -> RepairResult:
        """Restore permission mode, or undo a symlink substitution."""
        manifest = self._resolve_baseline(base_dir)
        if manifest is None:
            return RepairResult(self.name, fault.path, False,
                                "cannot locate trusted baseline metadata")
        m = (manifest.get("__meta__") or {}).get(rel)
        if m is None:
            return RepairResult(self.name, fault.path, False,
                                "no baseline metadata for this file")

        if "permission mode changed" in fault.description:
            try:
                os.chmod(fault.path, m["mode"])
                return RepairResult(self.name, fault.path, True,
                                    f"restored permission mode {oct(m['mode'])}")
            except Exception as e:
                return RepairResult(self.name, fault.path, False,
                                    f"chmod failed: {e}")

        if "symlink" in fault.description:
            # Restore the trusted bytes as a regular file (undo link swap).
            data = self._baseline_bytes(base_dir, rel)
            if data is None:
                return RepairResult(self.name, fault.path, False,
                                    "no trusted baseline bytes to restore")
            try:
                if os.path.islink(fault.path) or os.path.exists(fault.path):
                    os.remove(fault.path)
                os.makedirs(os.path.dirname(fault.path), exist_ok=True)
                with open(fault.path, "wb") as fh:
                    fh.write(data)
                os.chmod(fault.path, m["mode"])
                return RepairResult(self.name, fault.path, True,
                                    "restored regular file from baseline "
                                    "(link substitution undone)")
            except Exception as e:
                return RepairResult(self.name, fault.path, False,
                                    f"restore failed: {e}")
        return RepairResult(self.name, fault.path, False,
                            "unrecognized metadata fault")

    def _find_target_root(self, path: str) -> str | None:
        """Find the directory whose baseline.json / git root governs ``path``.

        Priority: the NEAREST directory containing a ``baseline.json`` — that
        is the most specific integrity scope for this file (e.g. a drill copy
        under ``work/`` has its own baseline.json and must NOT fall back to an
        outer repository). Only when no baseline.json exists do we fall back to
        a git worktree root (the ``--self`` case).

        The upward walk STOPS at any nested git repository boundary: files
        inside an inner repo are governed by that repo (its HEAD or its own
        baseline.json), never by an outer project's baseline.json above it.
        Without this, a git-baselined drill copy inside the kit's own tree
        would attach to the kit's committed baseline.json — a different
        project's trust data.
        """
        d = os.path.dirname(path)
        start = d
        while True:
            if os.path.isfile(os.path.join(d, "baseline.json")):
                return d
            if os.path.isdir(os.path.join(d, ".git")) or \
               os.path.isfile(os.path.join(d, ".git")):
                break  # inner git repo boundary — outer baselines don't govern
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        # No baseline.json anywhere above -> fall back to git root.
        repo = _git_root(start)
        if repo:
            return repo
        return None
