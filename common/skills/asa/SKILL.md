---
name: asa
description: Use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, or mechanical.
---
<!-- harr-managed-skill-v1 -->

# Asa

When an unresolved material architecture decision arises, do not choose it in the root.

1. For this unresolved decision, reuse its existing `asa-architect` if one was already spawned; otherwise spawn one with `fork_turns: "all"`. Do not spawn a second Asa for the same decision.
2. Ask the exact question to resolve, including competing alternatives or constraints that make the decision necessary. Do not copy or summarize the inherited conversation as a substitute for the question.
3. Asa must return the chosen solution and rationale; rejected alternatives and why; invariants and risks the implementation owner must preserve; and explicit unresolved questions, if any.
4. Return the decision to the existing implementation owner. The SAME owner continues the work.

If essential evidence is missing, gather only the requested facts and use `followup_task` to continue the SAME architect; do not re-fork the parent history. Do not substitute generic advice for a decision.

Do not compact the parent conversation, restrict the forked history, or spawn speculative Asa agents just to reduce tokens. Prompt-cache reuse is opportunistic, not guaranteed. After the decision is returned, do not keep asking Asa to review unrelated implementation details; a genuinely independent new architecture question may warrant a new Asa.
