# Commercial License Terms

> **This document is not a contract and does not grant any license.** It only explains: when GPLv3+ is insufficient, what a commercial license typically covers, and how to apply. **Until you sign a written agreement with the copyright holder, you only have the rights granted by `LICENSE` Option A (GPLv3-or-later).**

Applicable to: `self_heal_kit`, Copyright Holder: `self_heal_kit Authors` (repository owner).  
Main declaration in `LICENSE`, SPDX: `GPL-3.0-or-later OR LicenseRef-Commercial`.

---

## 1. When a Commercial License Is Required

| Use Case | GPLv3+ Sufficient? | Commercial License Needed? |
|----------|-------------------|---------------------------|
| Personal / internal corporate use, no distribution to third parties | Yes (GPL distribution obligation not triggered) | No |
| Your open-source project, released entirely under GPLv3+ with corresponding source published | Yes | No |
| Research, evaluation, teaching, articles, demos | Yes | No |
| Embedding this software (or modified versions) **into closed-source / proprietary products distributed** to customers | No — GPLv3 §5/§6 requires entire derivative work under GPLv3 with corresponding source | **Yes** |
| Delivery via OEM / rebrand / private build to third parties | No | **Yes** |
| Need warranty, IP indemnification, liability cap, SLA beyond GPLv3 | No (GPLv3 explicitly disclaims) | **Yes** |
| Need explicit patent grant, custom development, long-term support, or compliance attestation | No | **Yes** |
| Pure network service (SaaS), no program copy distributed to users, need deterministic legal opinion | Usually doesn't trigger GPLv3 source delivery obligation, but not automatic compliance | Advised / Optional commercial license |

> **Honest Boundary**: The table above is general guidance, not legal advice. GPLv3 **does not** treat "network use" as distribution like AGPLv3 does; therefore pure SaaS without binary delivery typically doesn't trigger source provision. However, once "delivery of client / agent runtime / device firmware" is involved, or the product needs §6 *Corresponding Source* / *Installation Information* exemptions, a commercial license should be obtained. When in doubt, treat as "needed".

---

## 2. What a Commercial License Typically Grants (Per Written Agreement)

Typical terms may include (**none granted by default**; only effective when written into signed agreement):

- Use, modify, redistribute in proprietary / closed-source products, **with exemption from GPLv3 source disclosure and copyleft obligations**;
- **Sublicense** or deliver private builds to your customers / affiliates / OEM partners;
- Explicit **patent grant**, third-party IP **indemnification**, liability cap, and **warranties**;
- **SLA / technical support / custom development / security advisories / compliance materials** (e.g., FIM-class compliance evidence);
- Specific terms for `NOTICE` attribution handling.

Rights not explicitly written in the agreement are **not granted**.

---

## 3. How to Apply

1. Initiate inquiry via **GitHub repository owner's private contact channel**;  
   or leave `Commercial license inquiry — please contact me privately` in Issues / Discussions — **do not disclose commercial details in public posts**.
2. Specify: entity name, use case (internal / distribution / SaaS / embedded), distribution mode & scale, required terms (closed-source, OEM, indemnity, SLA, etc.), desired term.
3. Negotiate and **sign written agreement**; upon effectiveness, you use the software under that agreement instead of GPLv3.

**This document commits to no price, discount, terms, or response SLA.** Any public discussion does not constitute an offer.

---

## 4. Why Dual Licensing Is Possible Here

- Project has **zero third-party source code**, runtime depends only on Python stdlib — single copyright chain;
- All external contributions via `CLA.md` grant copyright holder **sublicensable** rights, see `CONTRIBUTING.md`;
- Therefore copyright holder may simultaneously license under GPLv3+ (community) and proprietary terms (commercial), and adding new license options later does not require re-authorization from historical contributors.

---

## 5. Relationship with Community Edition

- Choosing GPLv3+ requires no contact, no fee — just use per `LICENSE-GPL-3.0.txt`;
- Derivative works already released under GPLv3+ retain their GPLv3+ grant **regardless of later commercial license sales**;
- Commercial license only solves "licensee doesn't want to bear GPLv3 obligations" — it does not retract any existing community rights.
