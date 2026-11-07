"""Write guard — pre-flight authorization + pre-commit / pre-run gate.

Phase 2, step 2 of the kit: move the integrity check *in front of* the action
instead of only repairing afterwards.

Two deterministic checks, stdlib only:

1. ``authorize_write(path, target_dir, roots)`` — path policy. A write is
   allowed only when the target file is inside one of the guarded roots.
   Anything else (the host project, ``..`` traversal, an absolute system path)
   is denied. This is what stops an agent from "helpfully" rewriting a file it
   was never asked to touch.

2. ``verify_scope(target_dir, roots, ...)`` — byte policy. Runs the H7
   integrity guard restricted to the guarded roots and returns the faults.
   Used by the git ``pre-commit`` hook and by ``agent_guard.py run`` so a
   tampered workspace can neither be committed nor executed.

Honest limit: this is a *cooperative* gate. It constrains the workflows that
call it (agent shell wrapper, git hooks, CI). It cannot stop a process that
never asks — that needs kernel/EDR-level interception, which is out of scope
and documented in THREAT_MODEL.md.
"""

from __future__ import annotations

import os

__all__ = ["normalize_rel", "is_path_in_scope", "authorize_write",
           "verify_scope"]


def normalize_rel(rel) -> str:
    """Normalise a relative path to POSIX form, no leading/trailing '/'."""
    return str(rel).replace("\\", "/").strip().strip("/")


def is_path_in_scope(path: str, target_dir: str, roots) -> bool:
    """True iff ``path`` lives under one of ``roots`` (relative to target)."""
    norm_roots = [r for r in (normalize_rel(x) for x in (roots or [])) if r]
    if not norm_roots:
        # Fail-safe: no roots configured means nothing is in scope — never
        # silently fall back to "protect everything".
        return False
    try:
        rel = os.path.relpath(os.path.abspath(path),
                              os.path.abspath(target_dir))
    except Exception:
        return False
    rel = normalize_rel(rel)
    if not rel or rel == "." or rel.startswith(".."):
        return False
    for root in norm_roots:
        if rel == root or rel.startswith(root + "/"):
            return True
    return False


def authorize_write(path: str, target_dir: str, roots):
    """Return ``(allowed: bool, reason: str)`` for writing ``path``."""
    if is_path_in_scope(path, target_dir, roots):
        return True, "in scope"
    scope = ", ".join(
        sorted(r for r in (normalize_rel(x) for x in (roots or [])) if r))
    return False, ("path escapes the guarded roots: "
                   f"{os.path.abspath(path)} is not under "
                   f"[{scope or '(none)'}]")


def verify_scope(target_dir: str, roots, strict: bool = True,
                 scan_binaries: bool = False,
                 check_metadata: bool = False):
    """Run the H7 guard restricted to ``roots`` and return remaining faults."""
    from healers.integrity_guard import (
        IntegrityGuardHealer, DEFAULT_NEW_FILE_WHITELIST)
    healer = IntegrityGuardHealer(
        detect_new_files=strict,
        new_file_whitelist=DEFAULT_NEW_FILE_WHITELIST,
        scan_binaries=scan_binaries,
        check_metadata=check_metadata,
        agent_guard=True,
        agent_guard_roots=list(roots or []))
    return healer.detect(target_dir)
