---
name: asa
description: Automatically use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not auto-use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, mechanical, or only needs analysis. An explicit user invocation may also request bounded architect-grade analysis of selected code, an image, or other material; discovery/selection of that material remains with root or the existing scope owner.
---
<!-- harr-managed-skill-v1 -->

# Asa

## Default architecture route

When an unresolved material architecture decision arises, do not choose it in the root.

1. Make the decision evidence-ready before invoking Asa. For a root-owned scope, root gathers any missing repository, runtime, or contract facts under the normal Harr Workspace/tool-routing policy. If a newly created checkout/worktree is involved, it must be registered through the normal Harr Workspace flow before investigation. Root gathers facts, constraints, and provenance only: once the boundary is material, root must not invent, rank, compare, or choose architecture alternatives. Because Asa is a full-history fork, do not retransmit a second full evidence packet. Do provide concise verified fact anchors for decisive facts that exist only in tool output or may no longer be durable after compaction.
2. If a Worker owns the scope, use that Worker's compact evidence handoff instead. Root must not independently reread or duplicate investigation of delegated code; ask the SAME Worker for narrowly missing facts if needed.
3. For this unresolved decision, reuse its existing `asa-architect` if one was already spawned; otherwise spawn one with `fork_turns: "all"`. Do not spawn a second Asa for the same decision.
4. Ask the exact question to resolve and state the fixed constraints. Include alternatives only when they were already supplied by the user, an accepted contract/design, or the gathered evidence; root must not manufacture or evaluate alternatives before Asa. For root-owned scope, add only concise verified fact anchors needed to make the question unambiguous, especially decisive facts originating in tool output or surviving only through compaction; do not summarize or resend the inherited conversation. For Worker-owned scope, include the Worker's evidence handoff because Asa does not inherit the Worker's private history.
5. Asa returns the chosen solution and rationale; rejected alternatives and why; invariants and risks the implementation owner must preserve; and explicit unresolved questions, if any.
6. Return the decision to the existing implementation owner. The SAME owner continues the work.

## Explicit user-directed analysis

If the user explicitly asks Asa herself to analyze selected code, an image, or other material, that is a manual override and does not require the analysis step itself to be an architecture decision.

Explicit invocation does not waive evidence preparation. Root, or the existing Worker for its owned scope, must first make the request evidence-ready: gather the relevant surrounding facts/constraints, identify and locate the correct material, and distinguish known facts from open questions. When the user explicitly asked Asa to perform the deep analysis, root must not perform that deep analysis first; root may inspect only enough to locate the target and prepare its surrounding factual context. If the material is already present in inherited parent history (for example a user-provided image), point Asa at it and include concise verified anchors for the prepared evidence. Otherwise provide the material itself or an exact locator such as a file/path/range or artifact reference. Asa may independently inspect and analyze that supplied material, including using an exact read/view operation on a caller-supplied locator, but must not broaden the task into repository discovery or gather missing surrounding evidence herself. Discovery and evidence acquisition remain with the scope owner.

For explicit analysis, Asa returns the analysis the user requested. If the user also asked Asa to resolve an architecture question, it returns the normal decision/rationale/invariants output above. If the analysis instead discovers a new material architecture decision that the user did not ask Asa to resolve, Asa must not choose it: return the analysis plus the exact escalation question for the user. Root surfaces that question to the user; if the user asks to continue, use `followup_task` on the SAME Asa.

## Missing evidence and lifecycle

For a default architecture decision, if essential evidence is missing, the existing scope owner gathers only the exact missing facts (root for root-owned scope; SAME Worker for delegated scope), then root uses `followup_task` to continue the SAME architect. For explicit user-directed analysis, Asa may derive facts from material already supplied; if another source is required, request that exact missing material and let the scope owner locate it before the same `followup_task`. Do not re-fork the parent history.

Do not compact the parent conversation, restrict the forked history, or spawn speculative Asa agents just to reduce tokens. Prompt-cache reuse is opportunistic, not guaranteed. After the decision or requested analysis is returned, do not keep asking Asa to review unrelated implementation details; a genuinely independent new architecture question or a new explicit user request may warrant a new Asa.
