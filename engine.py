"""Self-heal engine — the closed-loop orchestrator.

Pipeline per round:
    detect_all -> for each fault: snapshot, repair, verify the fault is gone
               -> if not gone: rollback (regression guard)
    if no faults remain after a round: HEALED
    else feed (signature set, progress) to the circuit breaker
    breaker trips (no progress / repeated) -> FAILED_CLOSED (escalate)

This encodes a four-layer self-healing model:
    L1 fault-domain recognition  -> healers
    L2 closed-loop healing       -> this loop
    L3 anti-regression guards    -> snapshot/rollback + verify gate
    L4 convergence boundary      -> circuit breaker (fail-closed)
"""

from __future__ import annotations

from healers.base import Fault
from healers.line_ending import LineEndingHealer
from healers.brace_escape import BraceEscapeHealer
from healers.yaml_format import YamlFormatHealer
from healers.quote_balance import QuoteBalanceHealer
from healers.key_map_gap import KeyMapGapHealer
from healers.decl_impl import DeclImplHealer
from healers.integrity_guard import IntegrityGuardHealer
from guards.circuit_breaker import CircuitBreaker
from guards.snapshot_rollback import Snapshot
from guards.verify_gate import VerifyGate, is_green


class SelfHealEngine:
    def __init__(self, healers=None, max_rounds: int = 6, patience: int = 3,
                 test_command: str = None, integrity_strict: bool = True,
                 integrity_whitelist=None):
        # integrity_strict: H7 reports unexpected new files (virus-dropped
        # files) by default. A whitelist of known-good new artefacts keeps it
        # from false-positiving on benign additions; pass integrity_strict=False
        # to disable (legacy behaviour).
        self.integrity_strict = integrity_strict
        self.integrity_whitelist = integrity_whitelist
        if healers is None:
            from healers.integrity_guard import (
                IntegrityGuardHealer, DEFAULT_NEW_FILE_WHITELIST)
            healers = [
                LineEndingHealer(),
                BraceEscapeHealer(),
                YamlFormatHealer(),
                QuoteBalanceHealer(),
                KeyMapGapHealer(),
                DeclImplHealer(),
                IntegrityGuardHealer(
                    detect_new_files=integrity_strict,
                    new_file_whitelist=integrity_whitelist
                    or DEFAULT_NEW_FILE_WHITELIST),
            ]
        self.healers = healers
        self.max_rounds = max_rounds
        self.patience = patience
        # The verify gate may delegate to a real project test suite. The
        # self-contained fixtures experiment never sets this (None).
        self.verifier = VerifyGate(test_command=test_command)

    # -- public API ----------------------------------------------------------
    def detect_all(self, target: str):
        faults = []
        for h in self.healers:
            faults.extend(h.detect(target))
        return faults

    def run(self, target: str) -> dict:
        breaker = CircuitBreaker(patience=self.patience)
        log = []
        for rnd in range(1, self.max_rounds + 1):
            faults = self.detect_all(target)
            green, detail = self.verifier.evaluate(faults, target_dir=target)
            if green:
                return {"status": "HEALED", "rounds": rnd - 1,
                        "verify": detail, "log": log}
            log.append(f"[r{rnd}] {detail}")
            if faults:
                sig = [f.signature() for f in faults]
                progress = 0
                for f in faults:
                    snap = Snapshot()
                    snap.take(f.path)
                    res = self._repair_for(f)
                    if res is None:
                        continue
                    if res.changed:
                        after = self.detect_all(target)
                        if not any(x.signature() == f.signature() for x in after):
                            progress += 1
                        else:
                            snap.restore(f.path)  # regression -> roll back
                            log.append(f"[r{rnd}] rollback {f.path}: "
                                       f"repair did not resolve fault")
                    else:
                        log.append(f"[r{rnd}] unrepairable {f.path}: {res.detail}")
                log.append(f"[r{rnd}] faults={len(faults)} progress={progress}")
                if breaker.observe(sig, progress):
                    return {
                        "status": "FAILED_CLOSED",
                        "rounds": rnd,
                        "reason": "circuit breaker tripped (no progress / "
                                  "repeated fault set) -> escalate to human",
                        "log": log,
                    }
            else:
                # No faults, but an external test command (if configured) failed.
                if breaker.observe([detail], 0):
                    return {
                        "status": "FAILED_CLOSED",
                        "rounds": rnd,
                        "reason": f"{detail} -> escalate to human",
                        "log": log,
                    }
        return {
            "status": "FAILED_CLOSED",
            "rounds": self.max_rounds,
            "reason": "exceeded max rounds without reaching green",
            "log": log,
        }

    # -- internals -----------------------------------------------------------
    def _repair_for(self, fault: Fault):
        for h in self.healers:
            if h.name == fault.healer:
                return h.repair(fault)
        return None
