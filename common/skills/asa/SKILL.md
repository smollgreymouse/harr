---
name: asa
description: Use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, or mechanical.
---
<!-- harr-managed-skill-v1 -->

# Asa

When an unresolved material architecture decision arises, do not choose it in the root.

1. Before invoking Asa, prepare a verified evidence packet for the exact decision. If root owns the scope, root must first investigate the relevant code and contracts itself, using the correct checkout/worktree and explicit project path for code-navigation tools. Include relevant entry points, call/lifetime paths, existing behavior, constraints, alternatives, and any gaps; distinguish observed facts from assumptions. Keep investigation targeted, not an exhaustive repository audit.
2. If a Worker owns the scope, use that Worker's compact evidence packet instead. Root must not independently reread or duplicate investigation of delegated code; ask the SAME Worker for narrowly missing facts if needed.
3. For this unresolved decision, reuse its existing `asa-architect` if one was already spawned; otherwise spawn one with `fork_turns: "all"`. Do not spawn a second Asa for the same decision.
4. Ask the exact question to resolve, supply the verified evidence packet and competing alternatives or constraints that make the decision necessary. Do not copy or summarize the inherited conversation as a substitute for the question or packet. Full forked history is contextual, not a replacement for evidence. By default, Asa reasons over the supplied evidence instead of doing source investigation. An explicit user request may ask Asa to independently analyze a selected code excerpt, image, or other material; root (or the existing Worker for its owned scope) must first locate and supply the correct material. This exception allows Asa to analyze it, not to independently search the repository.
5. Asa must return the chosen solution and rationale; rejected alternatives and why; invariants and risks the implementation owner must preserve; and explicit unresolved questions, if any.
6. Return the decision to the existing implementation owner. The SAME owner continues the work.

If essential evidence is missing, the existing scope owner gathers only the exact missing facts (root for root-owned scope; SAME Worker for delegated scope), then root uses `followup_task` to continue the SAME architect; do not re-fork the parent history. Do not substitute generic advice for a decision.

Do not compact the parent conversation, restrict the forked history, or spawn speculative Asa agents just to reduce tokens. Prompt-cache reuse is opportunistic, not guaranteed. After the decision is returned, do not keep asking Asa to review unrelated implementation details; a genuinely independent new architecture question may warrant a new Asa.
