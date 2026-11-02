"""Integration demonstration.

Builds a small "sample target project" (demo_project/) and shows what happens
when it boots with the self-heal engine wired in:

  A) clean project
        -> engine: HEALED, app runs
  B) project ships a broken config (CRLF line endings + unbalanced quote)
        -> engine self-heals, app runs
  C) project ships an unfixable fault (a project-specific healer detects it but
     cannot fix it)
        -> engine FAILED_CLOSED, app ABORTS (no fake-heal)
  D) project files are clean but its own test command fails
        -> engine FAILED_CLOSED via the verify gate (test_command)

Everything runs inside temp copies under work/ (gitignored); the canonical
demo_project/ stays clean.
"""

import os
import sys
import shutil

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)

from demo_project.boot import boot
from demo_project.marker_healer import MarkerHealer

WORK = os.path.join(KIT, "work")
DEMO = os.path.join(KIT, "demo_project")


def _stage(name):
    dst = os.path.join(WORK, name, "demo_project")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(DEMO, dst)
    return dst


def _write_cfg(path, text, crlf=False):
    endings = "\r\n" if crlf else "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(endings.join(text.split("\n")))


def _scenario_a():
    d = _stage("A")
    return boot(app_dir=d)


def _scenario_b():
    d = _stage("B")
    cfg = os.path.join(d, "config", "settings.cfg")
    # Inject: CRLF line endings + one unbalanced quote (missing closing '"').
    broken = (
        'app_name = "demo-service"\n'
        'log_level = "info"\n'
        'port = 8080\n'
        'token = "abc123\n'
    )
    _write_cfg(cfg, broken, crlf=True)
    return boot(app_dir=d)


def _scenario_c():
    d = _stage("C")
    marker = os.path.join(d, "config", "broken_marker.txt")
    with open(marker, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("this config carries a %%UNREPAIRABLE%% marker\n")
    return boot(app_dir=d, extra_healers=[MarkerHealer()])


def _scenario_d():
    d = _stage("D")
    # Files are clean, but the project's own test command fails -> gate blocks.
    return boot(app_dir=d,
                test_command='python -c "import sys; sys.exit(1)"')


def main():
    report = []
    for name, fn in [("A", _scenario_a), ("B", _scenario_b),
                     ("C", _scenario_c), ("D", _scenario_d)]:
        try:
            res = fn()
        except Exception as e:  # pragma: no cover
            res = {"boot": "ERROR", "error": repr(e)}
        report.append((name, res))

    print("=" * 72)
    print("INTEGRATION DEMO — sample target project boots with self-heal engine")
    print("=" * 72)
    for name, res in report:
        ok = res.get("boot") == "OK"
        print(f"\n--- Scenario {name}: "
              f"{'SELF-HEALED & RAN' if ok else 'ABORTED (fail-closed)'} ---")
        if ok:
            print("  heal :", res["heal"])
            print("  app  :", res["app"])
        else:
            print("  status :", res.get("status"))
            print("  reason :", res.get("reason"))
            if res.get("log"):
                print("  log   :", res["log"][-3:])
    print("\n" + "=" * 72)
    heal_ran = all(r[1].get("boot") == "OK" for r in report if r[0] in ("A", "B"))
    aborted = all(r[1].get("boot") == "ABORTED"
                  for r in report if r[0] in ("C", "D"))
    verdict = "PASS" if (heal_ran and aborted) else "CHECK"
    print(f"INTEGRATION DEMO : {verdict}  (A/B self-heal+run, C/D fail-closed)")
    print("=" * 72)


if __name__ == "__main__":
    main()
