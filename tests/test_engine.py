"""Engine-level tests: closed-loop healing + fail-closed escalation."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import SelfHealEngine
from healers.base import Healer, Fault, RepairResult


def _make_target():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "f.txt"), "wb") as fh:
        fh.write(b"\xef\xbb\xbf" + "a\r\nb\r\n".encode("utf-8"))
    with open(os.path.join(d, "g.py"), "w", encoding="utf-8") as fh:
        fh.write('x = "{{name}}"\n')
    with open(os.path.join(d, "c.yaml"), "w", encoding="utf-8") as fh:
        fh.write('{"name": "demo"}')
    return d


def test_engine_heals_repairable_target():
    d = _make_target()
    res = SelfHealEngine().run(d)
    assert res["status"] == "HEALED"
    assert res["rounds"] <= 2


class UnrepairableHealer(Healer):
    name = "unrepairable"

    def detect(self, target_dir):
        out = []
        for root, _, files in os.walk(target_dir):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        t = fh.read()
                except Exception:
                    continue
                if "NOPE" in t:
                    out.append(Fault(self.name, p, "unfixable", repairable=False))
        return out

    def repair(self, fault):
        return RepairResult(self.name, fault.path, False, "cannot fix")


def test_engine_fails_closed_on_unrepairable():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "z.txt"), "w", encoding="utf-8") as fh:
        fh.write("NOPE\n")
    res = SelfHealEngine(healers=[UnrepairableHealer()], patience=2).run(d)
    assert res["status"] == "FAILED_CLOSED"
    assert "circuit breaker" in res["reason"].lower()


def test_snapshot_rollback_on_regression():
    """A repair that does not remove its fault must be rolled back."""
    d = _make_target()
    eng = SelfHealEngine()
    before = open(os.path.join(d, "f.txt"), "rb").read()
    # Force a no-op repair path by using a broken healer that reports changed
    # but actually leaves the fault; engine must roll back to `before`.
    from healers.line_ending import LineEndingHealer

    class NoopLineEnding(LineEndingHealer):
        def repair(self, fault):
            return RepairResult(self.name, fault.path, True, "pretend fix")

    eng.healers = [NoopLineEnding()]
    res = eng.run(d)  # will not reach green -> fail-closed
    after = open(os.path.join(d, "f.txt"), "rb").read()
    # rolled back to original bytes because the fault persisted
    assert after == before
    assert res["status"] == "FAILED_CLOSED"


def test_verify_gate_passes_with_green_test_command():
    from guards.verify_gate import VerifyGate
    g = VerifyGate(test_command='python -c "import sys; sys.exit(0)"')
    green, detail = g.evaluate([])
    assert green is True
    assert "test command passed" in detail


def test_verify_gate_fails_with_failing_test_command():
    from guards.verify_gate import VerifyGate
    g = VerifyGate(test_command='python -c "import sys; sys.exit(1)"')
    green, detail = g.evaluate([])
    assert green is False
    assert "test command failed" in detail


def test_engine_heals_then_passes_real_test_command():
    # A target with a repairable fault AND a passing test command: the engine
    # repairs the fault, then the gate's test command passes -> HEALED.
    # (Synthetic command; not a real project.)
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "f.txt"), "wb") as fh:
        fh.write(b"\xef\xbb\xbf" + "a\r\n".encode("utf-8"))
    eng = SelfHealEngine(
        test_command='python -c "import sys; sys.exit(0)"')
    res = eng.run(d)
    assert res["status"] == "HEALED"
    assert "test command passed" in res["verify"]


def test_engine_fails_closed_when_test_command_fails():
    # Clean target, but a failing test command must not yield a false HEALED.
    d = tempfile.mkdtemp()
    eng = SelfHealEngine(
        test_command='python -c "import sys; sys.exit(1)"')
    res = eng.run(d)
    assert res["status"] == "FAILED_CLOSED"
    assert "test command" in res["reason"]
