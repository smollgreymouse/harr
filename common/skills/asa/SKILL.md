---
name: asa
description: Use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, or mechanical.
---
<!-- harr-managed-skill-v1 -->

# Asa

When an unresolved material architecture decision arises, do not choose it in the root.

1. Spawn `asa-architect` with `fork_turns: "all"`.
2. Ask the exact question to resolve, including competing alternatives or constraints that make the decision necessary.
3. Asa must return the chosen solution and rationale; rejected alternatives and why; invariants and risks the implementation owner must preserve; and explicit unresolved questions, if any.
4. Return the decision to the existing implementation owner. The SAME owner continues the work.

If essential evidence is missing, gather the specific missing facts and continue the SAME architect. Do not substitute generic advice for a decision.
