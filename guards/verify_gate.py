"""Verify gate — the all-green hard gate.

Self-healing only "completes" when the target is verifiably clean. Two modes:

1. Self-contained (default): ``green`` means no healer reports a remaining
   fault. This is the demonstration default and needs no external project.

2. Real test-suite mode: when a ``test_command`` is supplied, the gate also runs
   that command (e.g. ``pytest``, ``npm test``) and treats exit 0 as the final
   criterion. This lets the engine delegate to a project's own test suite as the
   authoritative "healed" proof — the contract is identical: exit 0 == healed,
   anything else == not done.

The kit ships with this capability but is NOT wired to any real project; the
self-contained fixtures experiment never sets ``test_command``.
"""

from __future__ import annotations

import subprocess


def is_green(faults) -> bool:
    """Backward-compatible helper: green iff no faults remain."""
    return len(faults) == 0


class VerifyGate:
    def __init__(self, test_command=None, cwd=None, timeout: int = 120):
        self.test_command = test_command
        self.cwd = cwd
        self.timeout = timeout

    def evaluate(self, faults) -> tuple:
        """Return ``(green: bool, detail: str)``."""
        if faults:
            return (False, f"{len(faults)} fault(s) remain")
        if not self.test_command:
            return (True, "no faults (self-contained mode)")
        code, _out = self._run(self.test_command)
        if code == 0:
            return (True, "no faults + test command passed")
        return (False, f"test command failed (exit {code})")

    def _run(self, cmd: str):
        try:
            r = subprocess.run(
                cmd, shell=True, cwd=self.cwd,
                capture_output=True, text=True, timeout=self.timeout)
            return r.returncode, (r.stdout + r.stderr)
        except Exception as e:  # pragma: no cover - defensive
            return 1, str(e)
