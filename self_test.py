"""End-to-end self-healing demonstration (rich, before/after visible).

This is the *showcase* of the four-layer self-healing model distilled from
loop-framework-skill:

    L1 fault-domain recognition  -> healers (H1/H2/H3)
    L2 closed-loop healing       -> engine loop (detect->repair->verify)
    L3 anti-regression guards    -> snapshot/rollback + verify gate
    L4 convergence boundary      -> circuit breaker (fail-closed)

Scenario A — three repairable faults in one dir. The engine should detect ->
repair -> verify to green and report HEALED within one round.

Scenario B — a fault no healer can fix (detect-only marker). The engine must
NOT spin forever; the circuit breaker trips and it reports FAILED_CLOSED
(escalate), proving the fail-closed convergence boundary.

Run:  python3 self_test.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import SelfHealEngine
from healers.base import Healer, Fault, RepairResult

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "fixtures")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _build_work(label: str, only=None) -> str:
    wd = tempfile.mkdtemp(prefix=f"selfheal_{label}_")
    names = only if only is not None else sorted(os.listdir(FX))
    for fn in names:
        shutil.copy(os.path.join(FX, fn), os.path.join(wd, fn))
    return wd


def summarize(path: str) -> str:
    """Short human-readable fault-state of a single file (before/after view)."""
    name = os.path.basename(path)
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception:
        return f"{name}: <unreadable>"
    notes = []
    if raw.startswith(b"\xef\xbb\xbf"):
        notes.append("UTF-8 BOM")
    if b"\r\n" in raw:
        notes.append(f"{raw.count(b'\r\n')}x CRLF")
    text = raw.decode("utf-8", errors="replace")
    if "{{" in text or "}}" in text:
        notes.append("escape-brace leak '{{ }}'")
    if name.endswith((".yaml", ".yml")):
        try:
            json.loads(text.strip())
            notes.append("FAKE YAML (JSON body)")
        except Exception:
            notes.append("real YAML")
    if "%%UNREPAIRABLE%%" in text:
        notes.append("UNREPAIRABLE marker")
    if not notes:
        notes.append("clean")
    return f"{name}: " + ", ".join(notes)


# --------------------------------------------------------------------------
# detect-only healer used by Scenario B
# --------------------------------------------------------------------------
class UnrepairableHealer(Healer):
    name = "unrepairable"

    def detect(self, target_dir: str):
        faults = []
        for p in self._iter_text_files(target_dir):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except Exception:
                continue
            if "%%UNREPAIRABLE%%" in text:
                faults.append(Fault(
                    self.name, p,
                    "marker %%UNREPAIRABLE%% (no automated fix known)",
                    repairable=False))
        return faults

    def repair(self, fault: Fault):
        return RepairResult(self.name, fault.path, False,
                            "no automated repair strategy")


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------
def run_scenario_a() -> dict:
    wd = _build_work("A")
    files = [os.path.join(wd, f) for f in sorted(os.listdir(wd))]

    print("=" * 70)
    print("SCENARIO A - repairable faults (CRLF/BOM, brace leak, fake YAML)")
    print("provenance: loop-framework v3.19.1 / v3.16.0 / v3.19.0")
    print("=" * 70)
    print("\n[BEFORE HEALING] detect phase - faults the engine sees:")
    for p in files:
        print("   " + summarize(p))

    eng = SelfHealEngine()
    res = eng.run(wd)

    print("\n[ENGINE LOG] closed-loop rounds:")
    for line in res["log"]:
        print("   " + line)

    print("\n[AFTER HEALING] verify phase - target state:")
    for p in files:
        print("   " + summarize(p))

    # independent byte-level assertions
    with open(os.path.join(wd, "sample_crlf.txt"), "rb") as fh:
        data = fh.read()
    assert b"\r\n" not in data and not data.startswith(b"\xef\xbb\xbf")
    with open(os.path.join(wd, "sample_leak.py"), "r", encoding="utf-8") as fh:
        assert "{{" not in fh.read()
    with open(os.path.join(wd, "sample_fake.yaml"), "r", encoding="utf-8") as fh:
        y = fh.read()
    assert y.lstrip().startswith("name:") and "{" not in y

    assert res["status"] == "HEALED"
    print(f"\n>>> RESULT: {res['status']} in {res['rounds']} round(s) "
          f"- L1+L2+L3 proved, target fully healed.")
    return res


def run_scenario_b() -> dict:
    # Focus the demo on a single unrepairable fault so the fail-closed
    # behaviour is unambiguous (no other healers are in play here).
    wd = _build_work("B", only=["sample_unrepairable.txt"])
    files = [os.path.join(wd, f) for f in sorted(os.listdir(wd))]

    print("\n" + "=" * 70)
    print("SCENARIO B - UNREPAIRABLE fault (no healer can fix it)")
    print("provenance: loop-framework loop_circuit.py fail-closed boundary")
    print("=" * 70)
    print("\n[BEFORE] the only fault present:")
    for p in files:
        print("   " + summarize(p))

    eng = SelfHealEngine(healers=[UnrepairableHealer()])
    res = eng.run(wd)

    print("\n[ENGINE LOG] circuit breaker watches for no-progress / repeat:")
    for line in res["log"]:
        print("   " + line)

    print("\n[AFTER] fault still present (engine refused to fake a fix):")
    for p in files:
        print("   " + summarize(p))

    assert res["status"] == "FAILED_CLOSED"
    print(f"\n>>> RESULT: {res['status']} after {res['rounds']} round(s)")
    print(f">>> REASON: {res.get('reason')}")
    print(">>> L4 proved: bounded loop, no infinite spin, no false green.")
    return res


if __name__ == "__main__":
    a = run_scenario_a()
    b = run_scenario_b()
    ok = a["status"] == "HEALED" and b["status"] == "FAILED_CLOSED"
    print("\n" + "=" * 70)
    print(f"SUMMARY  Scenario A = {a['status']} | Scenario B = {b['status']}")
    print("SELF-HEAL DEMO : " +
          ("PASS - detect->repair->verify + fail-closed both work"
           if ok else "FAIL"))
    print("=" * 70)
    sys.exit(0 if ok else 1)
