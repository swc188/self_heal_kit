# self_heal_kit — AI Agent Anti-Tamper Self-Protection Foundation

[![CI](https://github.com/swc188/self_heal_kit/actions/workflows/ci.yml/badge.svg)](https://github.com/swc188/self_heal_kit/actions/workflows/ci.yml)

**Version:** 1.0.0  
**License:** GPL-3.0-or-later OR LicenseRef-Commercial (Dual License, see Section 9)

A **standalone, zero-dependency** file integrity self-healing and anti-tamper foundation: take a trusted baseline snapshot of a target directory, and any file that deviates from that snapshot — **blocked at the gate, restored after the fact, and even a tampered baseline gets caught**.

Four layers of defense, tightening from entry point to trust root:

| Layer | Capability | Entry Point |
|-------|------------|-------------|
| ① Pre-Gate | Block unauthorized writes/commits/executions *before* they happen | `agent_guard.py` |
| ② Scope Guarding | Guard only `--agent-root` workspaces, zero false positives on host | `self_heal_watch.py --agent-guard` |
| ③ Post-Hoc Self-Healing | Deviation from baseline → byte-exact restore / rebuild / quarantine (H7) | `self_heal.py` / daemon |
| ④ Out-of-Band Trust Root | Detect tampered baseline itself; refuse to repair from a suspect baseline | `verify_trust.py` |

> Fully self-contained, Python standard library only (3.8+), no external dependencies, no other projects or skills required.

---

## 30-Second Demo

```bash
python3 self_heal_demo.py     # Full 4-act drill, all PASS (rc=0)
```

```
SELF-HEAL DRILL : PASS          # Self-heal loop: detect → repair → pytest verify
H7 INTEGRITY DRILL : PASS        # Syntactically-valid backdoor injection → byte-level detect → restore → pytest all green
H7 VIRUS DRILL : PASS            # Tamper restore / delete rebuild / add quarantine, all 3 infection classes detected
AGENT GUARD DRILL : PASS         # Full chain below ↓
```

AGENT GUARD Act 4 (flagship scenario) excerpt:

```
[2] WRITE POLICY     .agent/new.py -> ALLOW    host/app.py -> DENY (path escape)
[3] GATE BLOCKS      Tamper blocked: check exit 1, run refuses to execute
[4] H7 REPAIR        gen.py byte-exact restore, workspace clean again
[5] ADVANCED ATTACK  Tamper + rewrite baseline + recompute seal → on-disk 0 faults (seal defeated)
                     → Out-of-band anchor still catches it: TRUST ANCHOR BROKEN
[6] RECOVERY         Restore clean file + re-seal → TRUST OK
AGENT GUARD DRILL : PASS
```

**Use Cases**: AI Agent workspace hardening (flagship) · Deployment directory FIM · CI/CD supply chain poisoning prevention · Integrity compliance evidence · Accidental delete/modify emergency recovery.

**What It Is NOT (Honest Boundaries)**: Not an antivirus (no signatures, no system scan) · No memory injection detection · Does not prove code logic correctness · Pre-gate is cooperative (only guards processes that ask it). See `THREAT_MODEL.md` for full threat model.

---

## 1. What Problems It Solves

A recurring class of engineering failures are **format/character** issues (not business logic bugs), e.g.:

- Mixed CRLF/LF line endings, stray UTF-8 BOM
- Template/format-string `{` `}` escape leaks (literal `{` emitted instead of escaped)
- `.yaml` files containing JSON ("fake YAML")
- Unbalanced double quotes in config/data files
- Alias map "known alias but empty standard key" (display name ↔ standard key drift)
- Version drift between docs and code

These issues are **identifiable, automatically repairable, verifiable with deterministic rules** — the natural domain of "self-healing".

---

## 2. Self-Healing Capability Model (4 Layers)

| Layer | Capability | Implementation |
|-------|------------|----------------|
| **L1 Fault Domain Recognition** | Recognize high-frequency fault patterns | 7 `healers`, each owns one deterministic fault class (incl. integrity guard) |
| **L2 Closed-Loop Self-Heal** | detect → repair → verify, retry until green | `engine.py` closed loop |
| **L3 Anti-Regression Guardrails** | Prevent false green / prevent making things worse | `snapshot_rollback` (pre-repair snapshot, auto-rollback on regression) + `verify_gate` (all-green hard gate) |
| **L4 Convergence Boundaries** | No infinite spinning, fail-closed escalation | `circuit_breaker` (no progress / repeated fault set → trip) |

**Core Thesis**: Self-healing ≠ AGI self-rewriting. It is the institutionalization of "failure as data + deterministic verification gate + rollback/trip capability".

---

## 3. Built-in 7 Healers (L1 Fault Domains)

| # | Name | File | Fault Domain | Repair Action |
|---|------|------|--------------|---------------|
| H1 | Line Ending | `healers/line_ending.py` | CRLF / BOM | CRLF → LF, strip UTF-8 BOM |
| H2 | Brace Escape | `healers/brace_escape.py` | `{{ }}` leak, unmatched `{ }` | Collapse extra escapes, add missing pairs |
| H3 | Fake YAML | `healers/yaml_format.py` | `.yaml` containing JSON | Rewrite as valid YAML |
| H4 | Quote Balance | `healers/quote_balance.py` | Unbalanced double quotes | Add missing `"` to balance |
| H5 | Key Map Gap | `healers/key_map_gap.py` | Alias map standard key empty | Populate standard key from built-in alias table |
| H6 | Decl↔Impl | `healers/decl_impl.py` | README version ≠ code version | Align `__version__` to README |
| H7 | Integrity Guard | `healers/integrity_guard.py` | File bytes deviate from trusted baseline (incl. logic injection) | Restore original bytes from baseline; strict mode default-on + whitelist; baseline hash seal prevents self-tamper |

---

## 4. Four Guardrails

| Guardrail | File | Role |
|-----------|------|------|
| **Snapshot Rollback** | `engine.py` | Before each repair round, snapshot target; if verification fails, auto-rollback |
| **Verify Gate** | `engine.py` | External test command (e.g. `pytest`) must exit 0 to accept repair |
| **Circuit Breaker** | `engine.py` | Track fault signatures; repeated identical faults or no progress → trip, require human |
| **Out-of-Band Trust Anchor** | `verify_trust.py` | `sha256(baseline.json)` stored externally; detects baseline+seal co-tampering |

---

## 5. Quick Start

### Install (no dependencies)
```bash
pip install -e .
# or just run scripts directly — pure stdlib
```

### Self-Heal Your Own Project
```bash
# 1. Generate trusted baseline (run once in a clean state)
python make_baseline.py . --with-bytes

# 2. Self-heal (H7 only by default; adds format healers with --with-format-healers)
python self_heal.py --self
```

### CI Artifact Guard (Real-World Adoption Path)
```bash
# Build → Seal → Verify (see examples/ci-artifact-guard/ for GitHub Actions/GitLab/Jenkins/Azure)
python make_baseline.py dist/ --with-bytes --scan-binaries
python examples/ci-artifact-guard/ci_artifact_guard.py --target dist/ --scan-binaries
```

### Watch Daemon (Unattended)
```bash
# One-shot (cron/Task Scheduler)
python self_heal_watch.py --target /opt/myapp --once --strict

# Long-running with periodic self-maintenance
python self_heal_watch.py --target /opt/myapp --interval 300 --maintain-interval 86400 --maintain-first --trust-anchor /mnt/ro/anchor.json
```

### AI Agent Workspace Guard
```bash
# Pre-gate: authorize writes only inside .agent/
python agent_guard.py install-hook --agent-root .agent

# Runtime guard: verify scope before running agent command
python agent_guard.py run --agent-root .agent -- python agent.py
```

---

## 6. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    SelfHealEngine                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐  │
│  │  H1..H6 │ │   H7    │ │  ...    │ │  Custom Healer  │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────────┬────────┘  │
│       └──────────┼──────────┼────────────────┘            │
│                  ▼          ▼                              │
│         detect_all()  →  repair()  →  verify_gate()       │
│                  │          │          │                   │
│                  ▼          ▼          ▼                   │
│         ┌─────────────────────────────────────┐           │
│         │   Snapshot / Circuit Breaker /      │           │
│         │   Retry Loop (max 5 rounds default) │           │
│         └─────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
       ┌──────────┐    ┌──────────┐    ┌──────────┐
       │ baseline │    │  .git/   │    │  anchor  │
       │ .json    │    │  HEAD    │    │ (OOB)    │
       └──────────┘    └──────────┘    └──────────┘
```

**Baseline Priority**: `baseline.json` (with `__bytes__`) > Git HEAD > None

---

## 7. Key Features Deep Dive

### H7 Integrity Guard (`healers/integrity_guard.py`)
- **Trusted Baseline Sources**: `baseline.json` (portable, with embedded `__bytes__`) or Git HEAD
- **Detection Classes**: TAMPER (byte change), DELETE (missing), ADD (new file, strict mode), SEAL (baseline manifest tampered)
- **Repair**: Byte-exact restore from `__bytes__` or Git HEAD; ADD → `.quarantine/` (reversible); SEAL → restore from Git HEAD
- **Strict Mode**: `detect_new_files=True` by default, with `DEFAULT_NEW_FILE_WHITELIST` (dist/, build/, *.log, .venv/, etc.)
- **Binary Scanning**: `--scan-binaries` includes `.exe/.dll/.so/.bin/...`
- **Metadata Check**: `--check-metadata` records/restores permission mode & symlink status
- **Agent Guard Scope**: `--agent-guard --agent-root .agent` limits protection to agent workspace

### Out-of-Band Trust Anchor (`verify_trust.py`, `guards/trust_root.py`)
```bash
# Seal baseline to external anchor
python verify_trust.py seal --target . --anchor /mnt/readonly/project.anchor.json

# Verify (exit 1 on break)
python verify_trust.py verify --target . --anchor /mnt/readonly/project.anchor.json

# Snapshot & promote (rollback)
python make_baseline.py . --snapshot v1.0
python verify_trust.py promote --target . --name v1.0 --anchor /mnt/readonly/project.anchor.json
```
- Anchor stores `sha256(baseline.json)` — compromising chain now requires **two independent writes**
- Honest limit: hash-level, not key-level. If attacker writes anchor too, chain is defeated — keep anchor out of reach.

### Pre-Gate (`agent_guard.py`)
```python
from agent_guard import authorize_write, verify_scope

# In your agent's write tool
if not authorize_write(target_path, roots=[".agent", "generated"]):
    raise PermissionError("Write escapes guarded workspace")

# Before running any command in the workspace
exit_code = verify_scope(".")  # 0=clean, 1=deviation, 2=no baseline
```

- `install-hook` / `uninstall-hook` for git pre-commit integration
- Exit codes: 0=clean, 1=deviation blocked, 2=no baseline, 4=usage error

### Self-Maintenance (`self_heal_watch.py --maintain-interval`)
- Periodically regenerates baseline with embedded bytes (`make_baseline --with-bytes`)
- Re-seals out-of-band anchor to match new baseline
- Allows legitimate config changes to be absorbed into baseline automatically
- Emits `MAINTENANCE OK/FAILED` logs for observability

---

## 8. CI/CD Integration (Supply Chain Protection)

See `examples/ci-artifact-guard/` for ready-to-copy configs:

| CI System | File | Key Points |
|-----------|------|------------|
| **GitHub Actions** | `README.md` (flagship) | `build → seal → guard` in one job |
| **GitLab CI** | `.gitlab-ci.yml` | 4 stages, `needs` artifact passing, `allow_failure: false` |
| **Azure Pipelines** | `azure-pipelines.yml` | Explicit stage deps, Seal in protected pool |
| **Jenkins** | `Jenkinsfile` | `stash/unstash`, failure email, Seal trusted env comment |

**Critical**: For binary artifacts (`.exe`, `.so`, `.dll`), add `--scan-binaries` to **both** `make_baseline.py` and `ci_artifact_guard.py`.

**Enterprise Deployment Checklist**: See `examples/ci-artifact-guard/ENTERPRISE_DEPLOYMENT.md`

---

## 9. Licensing (Dual License)

This project is distributed under a **dual license**:

1. **GPL-3.0-or-later** — For open source use. See `LICENSE-GPL-3.0.txt`.
2. **LicenseRef-Commercial** — For proprietary embedding, closed-source distribution, or GPL exemption. See `LICENSE-COMMERCIAL.md`.

**Commercial License Scenarios**:
- Embedding in a closed-source product
- Distributing without conveying GPL rights
- Priority support / SLA / compliance packaging
- Contact: (add your email)

**Contributor License Agreement**: See `CLA.md`. All contributions require CLA sign-off (grants relicensing rights + patent grant).

---

## 10. Honest Threat Model & Limits

See `THREAT_MODEL.md` for full model. Summary:

| In Scope | Out of Scope |
|----------|--------------|
| File byte integrity vs. trusted baseline | Memory injection, runtime hooks |
| Baseline manifest tampering (via seal + OOB anchor) | Attacker who controls both target AND anchor |
| Permission mode / symlink substitution (with `--check-metadata`) | Hardware/firmware/BIOS attacks |
| New file detection (strict mode + whitelist) | Logic correctness, business bugs |
| AI Agent workspace scope isolation | Processes that don't cooperate with pre-gate |

**Fail-Closed Principle**: Any trust anchor mismatch → refuse to repair, alert `TRUST_BROKEN`.

---

## 11. Contributing

See `CONTRIBUTING.md`. Key rules:

1. **H7 Bootstrap Iron Law**: Commit first → regenerate baseline → re-seal → then run `--self`. Violating this reverts your uncommitted changes.
2. All tests must pass: `pytest -q tests/` (43 tests)
3. LF line endings, no BOM, UTF-8
4. Sign `CLA.md` before PR

---

## 12. Security

See `SECURITY.md`. Private vulnerability reporting only — no public issues for security bugs.

---

## 13. Project Status

| Metric | Status |
|--------|--------|
| Tests | 43/43 passing (Python 3.8/3.11/3.13 CI) |
| Demo | 4-act all PASS |
| CI Artifact Guard | Demo + 4 CI systems + Enterprise checklist |
| License | Dual (GPL-3.0 + Commercial) |
| Dependencies | Zero (Python stdlib only) |
| Maintenance | Active |

---

## 14. Links

- **GitHub**: https://github.com/swc188/self_heal_kit
- **Issues**: Bug reports, feature requests
- **Discussions**: Q&A, Show and tell, Commercial inquiries
- **Security**: Private reporting per `SECURITY.md`

---

> **One-Liner**: *Build → Seal → Guard in 3 commands. Zero deps. Works everywhere Python runs.*
