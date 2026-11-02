---
name: asa
description: Use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, or mechanical.
---
<!-- harr-managed-skill-v1 -->

# Asa

When this skill applies, do not choose the material architecture in the root.

Spawn `asa-architect` with `fork_turns: "none"`. Send only a compact decision packet: goal, exact decision required, fixed constraints/invariants, and concrete evidence. Do not send the root transcript or broad code dumps.

If the architect asks for evidence, gather only the requested facts and continue the SAME architect.

Return the decision to the implementation owner that already has the code context.
