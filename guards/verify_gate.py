"""Verify gate — the all-green hard gate.

Self-healing only "completes" when the target is verifiably clean. Here
``green`` means no healer reports a remaining fault. A production deployment
would additionally run the project's own test suite as the gate; the contract
is identical: exit 0 == healed, anything else == not done.
"""

from __future__ import annotations


def is_green(faults) -> bool:
    return len(faults) == 0
