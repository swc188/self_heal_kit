"""End-to-end self-healing demonstration (rich, before/after visible).

This is the *showcase* of the four-layer self-healing model distilled from
loop-framework-skill:

    L1 fault-domain recognition  -> healers (H1..H6)
    L2 closed-loop healing       -> engine loop (detect->repair->verify)
    L3 anti-regression guards    -> snapshot/rollback + verify gate
    L4 convergence boundary      -> circuit breaker (fail-closed)

Scenario A — six repairable faults in one dir (one per healer). The engine
should detect -> repair -> verify to green and report HEALED.

Scenario B — a fault no healer can fix (detect-only marker). The engine must
NOT spin forever; the circuit breaker trips and it reports FAILED_CLOSED
(escalate), proving the fail-closed convergence boundary.

Scenario C — the verify gate CAN delegate to a real project test suite via a
``test_command``. This is a *capability* demo only: we use trivial synthetic
commands (exit 0 / exit 1). The kit is NOT wired to any real project.

Run:  python3 self_test.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import SelfHealEngine
from healers.base import Healer, Fault, RepairResult
from healers.key_map_gap import ALIASES

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
    # H4 — unbalanced quotes in config-style files
    if name.endswith((".cfg", ".ini", ".conf", ".properties")):
        odd = [i + 1 for i, l in enumerate(text.splitlines())
               if not l.lstrip().startswith("#") and l.count('"') % 2 == 1]
        if odd:
            notes.append(f"unbalanced quotes line {odd}")
    # H5 — mapping gap in alias csv
    if name.endswith(".csv"):
        try:
            rows = list(csv.DictReader(io.StringIO(text)))
            gaps = [r["term"] for r in rows
                    if "term" in r and "canonical" in r
                    and r.get("term", "").strip() in ALIASES
                    and not r.get("canonical", "").strip()]
            if gaps:
                notes.append(f"mapping gap: {gaps}")
        except Exception:
            pass
    # H6 — declared vs implemented version (cross-file)
    if name == "README.md":
        m = re.search(r"^Version:\s*([0-9A-Za-z.\-]+)", text, re.M)
        if m:
            notes.append(f"declared version {m.group(1)}")
    if name.endswith(".py") and "__version__" in text:
        m = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", text)
        if m:
            parent = os.path.dirname(path)
            rmd = os.path.join(parent, "README.md")
            mism = ""
            if os.path.exists(rmd):
                rt = open(rmd, encoding="utf-8", errors="replace").read()
                dm = re.search(r"^Version:\s*([0-9A-Za-z.\-]+)", rt, re.M)
                if dm and dm.group(1) != m.group(1):
                    mism = f" MISMATCH vs declared {dm.group(1)}"
            notes.append(f"impl version {m.group(1)}{mism}")
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
    print("SCENARIO A - repairable faults (one per healer H1..H6)")
    print("provenance: loop-framework v3.19.1 / v3.16.0 / v3.19.0 / "
          "v3.10.1 / v3.22.0")
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

    # independent byte-level assertions for all six healers
    with open(os.path.join(wd, "sample_crlf.txt"), "rb") as fh:
        data = fh.read()
    assert b"\r\n" not in data and not data.startswith(b"\xef\xbb\xbf")
    with open(os.path.join(wd, "sample_leak.py"), "r", encoding="utf-8") as fh:
        assert "{{" not in fh.read()
    with open(os.path.join(wd, "sample_fake.yaml"), "r", encoding="utf-8") as fh:
        y = fh.read()
    assert y.lstrip().startswith("name:") and "{" not in y
    # H4
    with open(os.path.join(wd, "sample_quotes.cfg"), "r", encoding="utf-8") as fh:
        for line in fh:
            if line.lstrip().startswith("#"):
                continue
            assert line.count('"') % 2 == 0
    # H5
    with open(os.path.join(wd, "sample_terms.csv"), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["term"].strip() in ALIASES:
                assert row["canonical"].strip(), row["term"]
    # H6
    with open(os.path.join(wd, "README.md"), encoding="utf-8") as fh:
        dver = re.search(r"Version:\s*([0-9A-Za-z.\-]+)", fh.read()).group(1)
    with open(os.path.join(wd, "sample_impl.py"), encoding="utf-8") as fh:
        iver = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']",
                         fh.read()).group(1)
    assert iver == dver, (iver, dver)

    assert res["status"] == "HEALED"
    print(f"\n>>> RESULT: {res['status']} in {res['rounds']} round(s) "
          f"- L1+L2+L3 proved, all 6 fault domains healed.")
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


def run_scenario_c() -> dict:
    print("\n" + "=" * 70)
    print("SCENARIO C - verify_gate can delegate to a REAL test suite "
          "(hook demo)")
    print("NOTE: NOT wired to any project; trivial synthetic commands prove "
          "the hook.")
    print("=" * 70)

    # C1: an empty (already clean) target + a PASSING test command => HEALED.
    wd1 = tempfile.mkdtemp(prefix="selfheal_C1_")
    eng_pass = SelfHealEngine(
        test_command='python -c "import sys; sys.exit(0)"')
    res_pass = eng_pass.run(wd1)
    print("\n[C1] clean target + passing test command:")
    for line in res_pass["log"]:
        print("   " + line)
    print(f"   >>> {res_pass['status']} | verify: {res_pass.get('verify')}")

    # C2: an empty (already clean) target + a FAILING test command =>
    # not healed; the gate reports the test failure and escalates.
    wd2 = tempfile.mkdtemp(prefix="selfheal_C2_")
    eng_fail = SelfHealEngine(
        test_command='python -c "import sys; sys.exit(1)"')
    res_fail = eng_fail.run(wd2)
    print("\n[C2] clean target + FAILING test command:")
    for line in res_fail["log"]:
        print("   " + line)
    print(f"   >>> {res_fail['status']} | reason: {res_fail.get('reason')}")

    assert res_pass["status"] == "HEALED"
    assert "test command passed" in res_pass["verify"]
    assert res_fail["status"] == "FAILED_CLOSED"
    assert "test command" in res_fail["reason"]
    print("\n>>> RESULT: gate CAN delegate to a test suite (exit 0 == healed, "
          "exit != 0 == escalate). Not connected to any project.")
    return {"C1": res_pass, "C2": res_fail}


if __name__ == "__main__":
    a = run_scenario_a()
    b = run_scenario_b()
    c = run_scenario_c()
    ok = (a["status"] == "HEALED"
          and b["status"] == "FAILED_CLOSED"
          and c["C1"]["status"] == "HEALED"
          and c["C2"]["status"] == "FAILED_CLOSED")
    print("\n" + "=" * 70)
    print(f"SUMMARY  A={a['status']} | B={b['status']} | "
          f"C1={c['C1']['status']} | C2={c['C2']['status']}")
    print("SELF-HEAL DEMO : " +
          ("PASS - 6 healers + fail-closed + verify-gate hook all work"
           if ok else "FAIL"))
    print("=" * 70)
    sys.exit(0 if ok else 1)
