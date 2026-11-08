# Security Policy

This project is itself a file integrity and anti-tamper tool, so "how to report a finding" must be crystal clear.

## Reporting Channels (No Public Issues)

**Report privately. Do not post vulnerability details or PoCs in public Issues / Discussions / PRs.**

- **Preferred**: Use **Report a vulnerability** on this repository's GitHub page  
  (`Settings` → sidebar `Security and quality` → `Advanced Security` → `Private vulnerability reporting` → `Enable`; public repos only, requires admin).
- **Fallback**: Contact **GitHub repository owner (repository owner) via private channel**, subject: `security: self_heal_kit`.
- If both unreachable, open an issue **with zero details** requesting a private channel.

## What to Include

- Affected version / commit, OS, Python version.
- Reproduction steps or minimal PoC (stable reproduction is most important).
- Your assessed impact, and whether it involves capabilities boundaries declared in `THREAT_MODEL.md`.

## What Counts as a Security Issue

- **Bypass of declared defenses**: e.g., tampering with protected files without triggering H7 detection, silently re-sealing out-of-band trust anchor, bypassing `agent_guard` write/exec gates, defeating `baseline.json` seal without detection.
- **Repair logic causing destruction**: wrongful deletion, wrong quarantine, rolling back legitimate files to old versions, privilege escalation or OOB write via permission/symlink handling.
- **Exploitable issues in dependencies/toolchain** (runtime has zero third-party deps, but CI/packaging chain is in scope).

**NOT Security Issues** (use regular issue):

- **Blind spots honestly declared in `THREAT_MODEL.md`**: memory injection, interpreter/engine replacement, H7 silent when no baseline, hash-level (not key-level) trust root, cooperative gate can't control non-cooperative processes, legitimate new files outside whitelist flagged.
- "This tool is not an antivirus" / "Cannot fix business logic bugs" — these are design scope.
- Target project's business bugs, usage questions, feature requests, doc typos.

> This distinction matters: read `THREAT_MODEL.md` sections 3 & 4 first — saves everyone time.  
> But if you find "declared as protected, actually not" — that's exactly what we want.

## Response (Honest, No Unkeepable SLAs)

- Personal maintenance — **no fixed response time or commercial SLA committed**; will acknowledge receipt, confirm reproducibility, indicate fix intent & rough direction.
- If confirmed vulnerability: prioritize fix on default branch, add regression test, record in `CHANGELOG.md`; coordinate disclosure timing with reporter (typically request reasonable coordination window, industry standard 90 days).
- If assessed as declared boundary / design trade-off: explain rationale, consider improving docs to prevent future misunderstanding.
- Will credit reporter in release notes **only with explicit consent**; default: identity kept private.

## User Responsibility

This tool is **cooperative, hash-level** integrity protection — not an EDR, not an antivirus, no key-level trust root. Before deployment, read `THREAT_MODEL.md` trust assumptions & hardening guidance, and place out-of-band anchors where attackers cannot simultaneously write.
