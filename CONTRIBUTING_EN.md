# Contributing Guide

Welcome to submit Issues, bug reports, and Pull Requests. This project has **zero third-party dependencies**, requiring only **Python 3.8+**.

---

## 1. Read the License First

This project is **dual-licensed (GPLv3-or-later / Commercial)**. Submitting any contribution implies you have read and agreed to `CLA.md` (Contributor grants **sublicensable** rights — the prerequisite for dual licensing). Corporate contributions must be authorized by an authorized representative in the PR. See:

- `LICENSE` — Dual license declaration
- `LICENSE-GPL-3.0.txt` — Community edition full text
- `LICENSE-COMMERCIAL.md` — Commercial license terms
- `CLA.md` — Contributor License Agreement
- `README.md` Section 9 — Selection guide

---

## 2. Local Verification

```bash
python -m pytest -q                # Regression tests (currently 43)
                                   # pyproject.toml testpaths=["tests"]
                                   # prevents collecting work/ drill copies
python self_heal_demo.py            # 4-act drill, all must PASS, rc=0
python self_heal.py --self          # H7 integrity self-check on own dir
python verify_trust.py verify --target . --anchor <your-anchor-path>
```

`self_heal.py --self` runs **H7 only** (integrity guard) by default — H1–H6 format healers won't rewrite legitimate source. Legacy behavior: add `--with-format-healers`.

---

## 3. Bootstrap Iron Law (Project-Specific, Mandatory)

H7 trusts **`baseline.json` or git HEAD**. Any uncommitted change is treated as "deviation from baseline", and `--self` will **revert it to HEAD**. Therefore the **only correct order** is:

1. Edit code / docs;
2. **`git commit` FIRST**;
3. If added/deleted protected files, regenerate baseline:
   `python make_baseline.py . --with-bytes`;
4. If out-of-band anchor configured, re-seal:
   `python verify_trust.py seal --target . --anchor <anchor>`;
5. **Only then** run `python self_heal.py --self` / daemon.

> Wrong order = your changes reverted by your own security mechanism. Not a bug — by design.

---

## 4. Submission Process

1. Fork / create branch, keep changes focused;
2. Run all commands from Section 2;
3. PR description: what changed, why, how verified; include `I have read and agree to the CLA.`;
4. New files must not trigger H7 false positives: protected extensions in `healers/integrity_guard.py` `_TEXT_EXTS`, whitelist in `DEFAULT_NEW_FILE_WHITELIST`.

---

## 5. Boundaries

- This project **does not fix business logic bugs**, is not an antivirus, does not scan memory;
  capabilities & trust assumptions in `THREAT_MODEL.md`.
- Doc changes are also H7-protected (`.md` / `.txt` in scan scope) — follow Section 3.
- Extensionless files (`LICENSE`, `NOTICE`) are **not** in `baseline.json` scan scope — they rely on git history + out-of-band trust anchor. Edit with extra care.
