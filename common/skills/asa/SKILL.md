---
name: asa
description: Automatically use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not auto-use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, mechanical, or only needs analysis. An explicit user invocation may also address Asa directly or request bounded architect-grade analysis of selected code, an image, or other material; every invocation remains evidence-first, and discovery/selection of that material remains with root or the existing scope owner.
---
<!-- harr-managed-skill-v1 -->

# Asa

Asa is one persistent architectural interlocutor for the whole root conversation. It has two entry paths at the same time: automatic material-decision escalation from root, and explicit user dialogue/analysis routed through root. Root is the only agent router; the user does not directly drive the Codex sub-agent.

## Evidence ownership

Every Asa invocation, automatic or explicit, must be evidence-ready first.

1. For a root-owned scope, root gathers any missing repository, runtime, or contract facts under the normal Harr Workspace/tool-routing policy. If a newly created checkout/worktree is involved, it must be registered through the normal Harr Workspace flow before investigation. Root gathers facts, constraints, provenance, and exact material locators only: once a boundary is material, root must not invent, rank, compare, or choose architecture alternatives. If the user explicitly asked Asa herself to perform the deep analysis, root must not perform that deep analysis first.
2. For a Worker-owned scope, use that Worker's compact evidence handoff. Root must not independently reread or duplicate investigation of delegated code; ask the SAME Worker for narrowly missing facts if needed. Asa does not inherit the Worker's private history.
3. On the first Asa spawn, `fork_turns: "all"` gives Asa the inherited root history, so do not retransmit a second full root evidence packet. Provide only the exact question, fixed constraints, and concise verified fact anchors for decisive facts that exist only in tool output or may no longer be durable after compaction.
4. On later calls to the persistent Asa, do not assume she sees root turns that happened after the initial fork. Send only the verified delta she has not already received: new root-owned facts/material/constraints since Asa's last relevant view, plus the exact question. Do not resend old inherited history. Worker-owned facts still cross the ownership boundary as a compact handoff.

## Persistent Asa lifecycle

Use one canonical Multi-Agent V2 child for the root conversation.

- First creation must use `spawn_agent` with `task_name="asa"`, `agent_type="asa-architect"`, and `fork_turns: "all"`.
- After that, route every automatic decision call and every explicit user message to the SAME canonical target with `followup_task(target="asa", ...)`. `followup_task` is also the normal cold-resume path for a persisted V2 child.
- Do not infer that Asa does not exist merely because `list_agents` does not show a cold child after root resume. If prior history indicates Asa existed, or existence is uncertain after compaction/resume, try `followup_task(target="asa", ...)` before spawning anything.
- Spawn `task_name="asa"` only when no Asa has ever been created for this root conversation or Codex explicitly reports that the canonical target does not exist. If the canonical target exists but cannot be resumed, report the lifecycle blocker; do not silently create a second Asa under another task name.
- A request expecting an Asa answer is not complete when `spawn_agent` or `followup_task` returns. Wait for Asa's completion notification before proceeding or answering for her. If completion has not arrived and V2 `wait_agent` is available, use it to wait for the mailbox/status update; never synthesize Asa's answer yourself.

## Automatic material-decision route

When an unresolved material architecture decision arises, root must not choose it.

1. Make the decision evidence-ready under the ownership rules above.
2. Ask the exact question to resolve and state the fixed constraints. Include alternatives only when they were already supplied by the user, an accepted contract/design, or verified evidence; root must not manufacture or evaluate alternatives before Asa.
3. Send the request to the SAME persistent Asa using the lifecycle rules above. For root-owned scope, include only the necessary verified delta/anchors. For Worker-owned scope, include the Worker's compact evidence handoff.
4. Asa returns the chosen solution and rationale; rejected alternatives and why; invariants and risks the implementation owner must preserve; and explicit unresolved questions, if any.
5. Return the decision to the existing implementation owner. The SAME owner continues the work.

## Explicit user dialogue and analysis

If the user addresses Asa directly, asks to ask/continue with Asa, or explicitly asks Asa herself to analyze selected code, an image, or other material, root is a transparent router after evidence preparation.

Explicit invocation does not waive evidence preparation. Root, or the existing Worker for its owned scope, first gathers the relevant surrounding facts/constraints, identifies and locates the correct material, and distinguishes known facts from open questions. Evidence preparation may be a no-op when the needed facts are already durable in Asa's own persistent context and no newer root/Worker facts are relevant.

Preserve the user's intent and relevant wording. Send the user's question to the SAME Asa with any required verified delta; root must not answer for Asa or perform the requested deep analysis first. Relay Asa's answer faithfully to the user, adding root commentary only when needed to distinguish transport/status or implementation consequences from Asa's own answer.

For caller-supplied material not already present in Asa's context, provide the material itself or an exact locator such as file/path/range or artifact reference. Asa may independently inspect and analyze that supplied material, including using an exact read/view operation on a caller-supplied locator, but must not broaden the task into repository discovery or gather missing surrounding evidence herself. Discovery and evidence acquisition remain with the scope owner.

For explicit analysis, Asa returns the analysis the user requested. If the user also asked Asa to resolve an architecture question, it returns the normal decision/rationale/invariants output above. If the analysis instead discovers a new material architecture decision that the user did not ask Asa to resolve, Asa must not choose it: return the analysis plus the exact escalation question for the user. Root surfaces that question to the user; if the user asks to continue, use `followup_task(target="asa", ...)` on the SAME Asa.

## Missing evidence

For a default architecture decision, if essential evidence is missing, the existing scope owner gathers only the exact missing facts (root for root-owned scope; SAME Worker for delegated scope), then root continues the SAME Asa with `followup_task(target="asa", ...)`. For explicit user-directed analysis/dialogue, Asa may derive facts from material already supplied; if another source is required, request that exact missing fact/material and let the scope owner locate it before the same follow-up. Do not re-fork the parent history.

Do not compact the parent conversation merely to reduce tokens, restrict the initial forked history, or spawn speculative/replacement Asa agents. Prompt-cache reuse is opportunistic, not guaranteed. Persistence means reuse Asa whenever she is the intended architectural interlocutor; it does not mean routing unrelated implementation review through her.
