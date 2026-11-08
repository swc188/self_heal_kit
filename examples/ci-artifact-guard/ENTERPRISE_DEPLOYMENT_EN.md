# Enterprise Deployment Checklist: CI Build Artifact Integrity Guard

> For teams integrating `ci_artifact_guard.py` into production pipelines.  
> **Core Principle**: Baselines must be generated in the **"trusted moment"**, anchors must live where **attackers cannot reach**.

---

## 1. Baseline Generation Timing — The Trusted Window

| Phase | Action | Trust Level | Notes |
|-------|--------|-------------|-------|
| **Build Complete** | `python make_baseline.py dist/ --with-bytes --scan-binaries` | **Highest** — Artifacts fresh from builder, no third-party touch | Must run in same CI job/stage; no intermediate write to shared storage |
| **Pre-Publish** | `python ci_artifact_guard.py --target dist/ --scan-binaries` | High — Artifacts traversed pipeline, re-verify | Optional `--no-repair` for gate-only; default auto-heals |

> ⚠️ **FORBIDDEN**: Do not copy artifacts elsewhere after build, then come back to generate baseline. The intermediate write IS the attack window. **Build → Seal atomically in place**.

---

## 2. Out-of-Band Anchor Storage

| Solution | Pros | Cons | Best For |
|----------|------|------|----------|
| **Read-Only NFS / SMB Mount** | Simple, low cost, existing infra | Needs network isolation, prevent remount | Private on-prem CI, existing read-only storage |
| **HashiCorp Vault KV v2** | Audit logs, versioning, ACL, dynamic creds | Requires Vault ops | Teams already using Vault for secrets |
| **AWS S3 Object Lock / Azure Immutable Blob / GCS Object Versioning + Retention** | Cloud vendor compliance backing, WORM legal force | Cross-cloud cost, policy config | Cloud-native teams, strong compliance needs |
| **Offline Media (USB / Optical / Paper QR)** | Physical air-gap, absolutely tamper-proof | Manual ops, not for high frequency | Core releases, finance/military grade |

**Minimum Viable**: Private Git repo `protected branch` + `signed commit` storing anchor JSON, verified via `verify_trust.py verify --anchor`. Still far stronger than "everything inside the pipeline".

---

## 3. Rotation Strategy

| Frequency | Action | Command | Notes |
|-----------|--------|---------|-------|
| **Every Release** | Regenerate baseline + re-seal | `make_baseline.py dist/ --with-bytes --scan-binaries && verify_trust.py seal --target dist/ --anchor $ANCHOR` | Automated in release pipeline, no human |
| **Weekly/Daily** | Periodic self-maintenance (watchdog mode) | `self_heal_watch.py --target /opt/app --maintain-interval 86400 --maintain-first --trust-anchor $ANCHOR` | Long-running services, edge devices |
| **Cert/Key Rotation** | Sync anchor update | Same as above | Align with certificate lifecycle |

> `self_heal_watch.py --maintain-interval` auto: regenerates baseline (with `__bytes__`) → re-seals anchor. This absorbs **legitimate config changes** (e.g. `config.yaml` edits) into baseline, stopping false alerts.

---

## 4. Incident Response SOP

| Event | Symptom | Response Steps | Owner |
|-------|---------|----------------|-------|
| **TRUST_BROKEN** | `verify_trust.py verify` exits 1 / watch logs `TRUST_BROKEN` | 1. Immediately isolate build/release env<br>2. Compare `baseline.json` vs anchor sha256, identify tampered files<br>3. Restore clean files from trusted source (Git HEAD / archived artifacts)<br>4. `make_baseline.py --with-bytes --scan-binaries` regenerate baseline<br>5. `verify_trust.py seal` re-seal anchor<br>6. Post-mortem: entry point? (CI cred leak? Build node compromise?) | Sec/Ops |
| **HEALED (Auto-Repair)** | Watch logs `HEALED rounds=1` | 1. Log alert, don't block<br>2. Periodic audit: same file repeatedly healing = persistent attack or config drift<br>3. If config drift → add to rotation strategy or whitelist | Ops |
| **ALERT (--no-repair Gate)** | CI stage exits 1, `DEVIATIONS: N` | 1. Block release<br>2. Manual triage: malicious tamper or legitimate change missed rotation?<br>3. Follow "Incident Response" or "Rotation Strategy" | Release Manager |

---

## 5. Pre-Launch Checklist (Tick All Before Go-Live)

- [ ] **Trusted Window**: `build → seal` same CI job/stage, no intermediate writes, no human touch
- [ ] **Anchor Offline**: Anchor storage **completely isolated** from build network/storage/auth domain
- [ ] **Binary Coverage**: Artifacts include `.exe/.so/.dll/.bin` → `--scan-binaries` on BOTH commands
- [ ] **Whitelist Minimal**: `DEFAULT_NEW_FILE_WHITELIST` only truly volatile dirs (`dist/`, `build/`, `*.log`)
- [ ] **Rotation Automated**: Release pipeline auto re-seals; long-running services run `self_heal_watch --maintain-interval`
- [ ] **Alerting Wired**: `TRUST_BROKEN` / `HEALED` / `ALERT` → monitoring (Prometheus/Grafana/DingTalk/WeCom)
- [ ] **Drill Done**: Deliberately tamper artifact + baseline + anchor, verify `TRUST_BROKEN` → recover → `TRUST OK` full loop
- [ ] **Docs Archived**: This checklist + pipeline YAML + SOP in team knowledge base, versioned

---

## 6. Common Pitfalls (Anti-Patterns)

| Pitfall | Consequence | Correct Approach |
|---------|-------------|------------------|
| `baseline.json` only in artifact dir, no OOB anchor | Attacker tampers both artifact and baseline, integrity defeated | **Must** `verify_trust.py seal` to offline location |
| `--target` points to repo root not `dist/` | New files under `dist/` swallowed by whitelist, drop attacks missed | **Must** target artifact directory itself |
| Binaries present but no `--scan-binaries` | Binaries skipped by default, tampering invisible | Add `--scan-binaries` to **BOTH** commands |
| Using `self_heal.py --target` instead of `ci_artifact_guard.py` | H1-H6 format healers "fix" legitimate artifacts | H7 only (IntegrityGuardHealer) |
| Baseline generated, then artifacts copied elsewhere to seal | Copy moment is replaceable | Seal in place, use CI-native artifact passing |

---

## 7. Version Compatibility Matrix

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| Python | 3.8 | 3.11+ | Stdlib only, no third-party deps |
| Git | 2.30+ | 2.40+ | `core.quotepath=false` needs recent version |
| CI System | Any | See examples | Just needs Python + artifact passing |

---

## 8. Support & Contact

- **Private Vulnerability Reporting**: See `SECURITY.md`
- **Commercial License Inquiry**: See `LICENSE-COMMERCIAL.md`
- **Contributing Guide**: See `CONTRIBUTING.md` (includes H7 Bootstrap Iron Law: commit → baseline → seal → `--self`)

---

> **One-Liner**: *Build is Seal, Seal is Anchor, Anchor Offline, Anchor Rotates, Alerts Investigated.*
