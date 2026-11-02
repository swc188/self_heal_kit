"""Self-heal drill: deliberately damage a COPY of the kit, then let the kit
heal ITSELF and prove it with its own pytest suite.

The drill proves three things:
  1. The engine can detect format/character faults in its own source.
  2. It repairs itself deterministically (snapshot/rollback guarded).
  3. Its completion promise is its own pytest: HEALED only when 14 tests pass.

Everything runs in a temp copy under work/ (gitignored); the canonical
self_heal_kit/ stays untouched. Nothing outside this directory is accessed.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _damage(dst):
    """Inject one deliberate format fault into a copy of the kit."""
    # Fault 1: CRLF + UTF-8 BOM in a python source file (H1 domain)
    src = os.path.join(dst, "engine.py")
    with open(src, "r", encoding="utf-8") as fh:
        text = fh.read()
    damaged = "\ufeff" + text.replace("\n", "\r\n")
    with open(src, "w", encoding="utf-8", newline="") as fh:
        fh.write(damaged)

    # Fault 2: escape-brace leak in a python source file (H2 domain)
    src2 = os.path.join(dst, "guards", "verify_gate.py")
    with open(src2, "r", encoding="utf-8") as fh:
        text2 = fh.read()
    damaged2 = text2.replace(
        'f"{len(faults)} fault(s) remain"',
        'f"{{ {len(faults)} }} fault(s) remain"', 1)
    with open(src2, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(damaged2)

    return [
        ("engine.py", "CRLF + UTF-8 BOM"),
        ("guards/verify_gate.py", "escape-brace leak {{ }}"),
    ]


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         timeout=300)


def main():
    print("=" * 72)
    print("SELF-HEAL DRILL — the kit damages itself, then heals itself")
    print("=" * 72)

    work = os.path.join(HERE, "work", "selfheal_drill")
    if os.path.exists(work):
        shutil.rmtree(work)
    dst = os.path.join(work, "self_heal_kit")
    # 只复制引擎"自身源码"（排除 fixtures 故意损坏样本、work、analysis、
    # README 文档示例、.git/.venv 等），这样自愈目标就是"引擎自身"而非演示样本。
    shutil.copytree(
        HERE, dst,
        ignore=shutil.ignore_patterns(
            "work", ".git", ".venv", "__pycache__", ".pytest_cache",
            "fixtures", "analysis", "README.md", "self_heal_demo.py",
            "run_integration_demo.py", "make_fixtures.py", "self_test.py",
        ))

    print(f"\n[1] STAGE a damaged copy at:\n    {dst}")
    faults = _damage(dst)
    for path, desc in faults:
        print(f"    injected -> {path}: {desc}")

    # Confirm damage is detectable BEFORE healing
    print("\n[2] BEFORE: engine.detect_all on the damaged copy")
    sys.path.insert(0, dst)
    from engine import SelfHealEngine
    before = SelfHealEngine().detect_all(dst)
    for f in before:
        print(f"    DETECTED [{f.healer}] {os.path.relpath(f.path, dst)}: {f.description}")
    print(f"    fault count = {len(before)}")

    # Heal with the kit's own pytest as completion promise
    print("\n[3] HEAL: run self-heal over the damaged copy (verify = pytest -q tests/)")
    test_cmd = [sys.executable, "-m", "pytest", "-q", "tests/"]
    res = SelfHealEngine(test_command=test_cmd).run(dst)
    print(f"    RESULT = {res['status']} (rounds={res['rounds']})")
    for line in res.get("log", [])[-4:]:
        print("      ", line)

    # Independent verification: after healing, pytest must pass on the copy
    print("\n[4] AFTER: run pytest on the healed copy (independent proof)")
    r = _run([sys.executable, "-m", "pytest", "-q", "tests/"], cwd=dst)
    print("    pytest exit =", r.returncode)
    tail = (r.stdout + r.stderr).strip().splitlines()
    print("    ", tail[-1] if tail else "")

    print("\n" + "=" * 72)
    ok = res["status"] == "HEALED" and r.returncode == 0
    print(f"SELF-HEAL DRILL : {'PASS' if ok else 'FAIL'}")
    print(f"  detected={len(before)} faults -> self-healed -> pytest "
          f"{'ALL GREEN' if r.returncode == 0 else 'NOT GREEN'}")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())