"""CI artifact guard — a reproducible, reusable integrity example.

Two modes:

    python ci_artifact_guard.py --demo
        Build a throwaway artifact directory, seal it with make_baseline.py,
        inject tamper + delete + dropped-file, then detect / repair / verify.
        This is the reproducible proof that the guard works end to end.

    python ci_artifact_guard.py --target dist/ [--no-repair]
        Check a real artifact directory with a H7-only engine. By default
        deviations are repaired (byte-exact restore from the sealed baseline);
        --no-repair makes it a pure CI gate that only reports and fails.

Design notes:
  * H7 only. Build artifacts are opaque bytes; running the H1-H6 format
    healers on them would rewrite legitimate output.
  * Point --target AT the artifact directory (e.g. dist/), not at the repo
    root: the built-in whitelist treats "dist/" as a known-safe volatile
    directory, so new files under a root-relative dist/ would be ignored.
  * The baseline must be produced by a trusted step (right after the build).
    Whoever can rewrite both the artifacts and the baseline defeats any
    in-band integrity scheme; use verify_trust.py for an out-of-band anchor.

Exit codes: 0 clean or fully healed, 1 deviations remain / fail-closed,
2 no trusted baseline or bad usage.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.dirname(os.path.dirname(HERE))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)

TRUSTED = {
    "bundle.py": (
        "# trusted build output\n"
        "def checksum():\n"
        "    return 'clean'\n"
    ),
    "SHA256SUMS.txt": "bundle.py  <sealed at build time>\n",
}
BACKDOOR = (
    "\n# injected by an untrusted step\n"
    "def checksum():\n"
    "    return 'pwned'\n"
)
DROPPED = "unexpected file dropped after the build\n"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _write(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def _make_baseline(dist):
    script = os.path.join(KIT_ROOT, "make_baseline.py")
    proc = subprocess.run(
        [sys.executable, script, dist, "--with-bytes"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError("make_baseline failed: " + proc.stdout.strip())
    return proc.stdout.strip()


def _engine():
    from engine import SelfHealEngine
    from healers.integrity_guard import (
        IntegrityGuardHealer, DEFAULT_NEW_FILE_WHITELIST)

    guard = IntegrityGuardHealer(
        detect_new_files=True,
        new_file_whitelist=DEFAULT_NEW_FILE_WHITELIST)
    return SelfHealEngine(healers=[guard], test_command=None)


def _show_faults(faults):
    for f in faults:
        print("    - " + os.path.basename(f.path) + ": " + f.description)


def _quarantined(dist, name):
    root = os.path.join(dist, ".quarantine")
    for cur, _dirs, files in os.walk(root):
        if name in files:
            return os.path.join(cur, name)
    return None


def check(target, repair=True):
    manifest = os.path.join(target, "baseline.json")
    if not os.path.isfile(manifest):
        print("ERROR: no trusted baseline.json in " + target)
        print("       generate one first: python make_baseline.py "
              + target + " --with-bytes")
        return 2

    eng = _engine()
    faults = eng.detect_all(target)
    if not faults:
        print("CLEAN — artifacts match the trusted baseline (" + target + ")")
        return 0

    print("DEVIATIONS: " + str(len(faults)) + " in " + target)
    _show_faults(faults)
    if not repair:
        print("ALERT — --no-repair: deviations reported, pipeline should fail")
        return 1

    res = eng.run(target)
    print("HEAL: " + res["status"] + " (rounds=" + str(res.get("rounds")) + ")")
    left = eng.detect_all(target)
    if left:
        print("FAILED — deviations remain:")
        _show_faults(left)
        return 1
    print("RESTORED — all artifacts match the trusted baseline again")
    return 0


def demo():
    print("=" * 68)
    print("CI ARTIFACT GUARD — reproducible demo (H7 only, zero deps)")
    print("=" * 68)
    with tempfile.TemporaryDirectory() as tmp:
        dist = os.path.join(tmp, "dist")
        os.makedirs(dist)

        # 1) A trusted build step produces artifacts.
        for name, text in TRUSTED.items():
            _write(os.path.join(dist, name), text.encode("utf-8"))
        original = dict((name, _sha(text.encode("utf-8")))
                        for name, text in TRUSTED.items())
        print("[1] BUILD     " + ", ".join(sorted(TRUSTED)))

        # 2) Seal them immediately, while the tree is still trusted.
        print("[2] BASELINE  " + _make_baseline(dist))

        # 3) An untrusted step tampers, deletes and drops a file.
        bundle = os.path.join(dist, "bundle.py")
        _write(bundle, _read(bundle) + BACKDOOR.encode("utf-8"))
        os.remove(os.path.join(dist, "SHA256SUMS.txt"))
        _write(os.path.join(dist, "evil.txt"), DROPPED.encode("utf-8"))
        print("[3] ATTACK    tamper bundle.py / delete SHA256SUMS.txt "
              "/ drop evil.txt")

        # 4) Detect before repairing: all three deviation classes must show.
        eng = _engine()
        faults = eng.detect_all(dist)
        descs = " ".join(f.description for f in faults)
        # Match H7's real fault descriptions, not invented labels.
        classes = [
            ("tamper", "!=" in descs and "baseline" in descs),
            ("delete", "baseline file missing" in descs),
            ("new file", "unexpected file" in descs),
        ]
        print("[4] DETECT    " + str(len(faults)) + " deviation(s)")
        _show_faults(faults)
        for label, ok in classes:
            print("      " + ("OK  " if ok else "MISS") + " " + label)
        if not all(ok for _label, ok in classes):
            print("FAILED — expected tamper/delete/add were not all detected")
            return 1

        # 5) Repair and verify byte-exactly.
        res = eng.run(dist)
        print("[5] HEAL      " + res["status"]
              + " (rounds=" + str(res.get("rounds")) + ")")
        checks = []
        for name, digest in original.items():
            path = os.path.join(dist, name)
            ok = os.path.isfile(path) and _sha(_read(path)) == digest
            checks.append((name + " byte-exact restored", ok))
        q = _quarantined(dist, "evil.txt")
        checks.append(("evil.txt quarantined (reversible)", q is not None))
        checks.append(("no remaining deviations",
                       len(eng.detect_all(dist)) == 0))
        for label, ok in checks:
            print("      " + ("OK  " if ok else "FAIL") + " " + label)
        good = res["status"] == "HEALED" and all(ok for _l, ok in checks)
        print("RESULT: " + ("PASS" if good else "FAIL"))
        return 0 if good else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="CI artifact integrity guard (H7 only)")
    ap.add_argument("--demo", action="store_true",
                    help="run the self-contained tamper/delete/drop drill")
    ap.add_argument("--target", default=None,
                    help="artifact directory to check (contains baseline.json)")
    ap.add_argument("--no-repair", action="store_true",
                    help="report deviations only, do not restore (CI gate)")
    args = ap.parse_args(argv)

    if args.demo and args.target:
        ap.error("--demo and --target are mutually exclusive")
    if args.demo:
        return demo()
    if not args.target:
        ap.error("specify --demo or --target <artifact dir>")
    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        print("ERROR: not a directory: " + target)
        return 2
    return check(target, repair=not args.no_repair)


if __name__ == "__main__":
    sys.exit(main())
