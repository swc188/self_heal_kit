"""Circuit breaker — anti-spin guard.

If the closed loop makes *no progress* for ``patience`` consecutive rounds, or
the exact same fault signature set repeats ``patience`` times (a semantic
dead-loop), the breaker trips and the engine escalates to a human instead of
spinning forever.
"""

from __future__ import annotations


class CircuitBreaker:
    def __init__(self, patience: int = 3):
        self.patience = patience
        self._no_progress = 0
        self._last_sig = None
        self._repeat = 0

    def observe(self, fault_signatures, progress: int) -> bool:
        """Feed one round's outcome. Returns True if the breaker should trip."""
        if progress == 0:
            self._no_progress += 1
        else:
            self._no_progress = 0

        sig = frozenset(fault_signatures)
        if sig and sig == self._last_sig:
            self._repeat += 1
        else:
            self._repeat = 0
        self._last_sig = sig

        return self.tripped()

    def tripped(self) -> bool:
        return self._no_progress >= self.patience or self._repeat >= self.patience
