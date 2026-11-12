---
name: asa
description: Automatically use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not auto-use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, mechanical, or only needs analysis. An explicit user invocation may also address Asa directly or request bounded architect-grade analysis of selected code, an image, or other material; every invocation remains evidence-first, and discovery/selection of that material remains with root or the existing scope owner.
---
<!-- harr-managed-skill-v1 -->

# Asa

Asa is the architectural interlocutor of the whole root conversation, routed through the `asa-architect` ZCode subagent running on the model configured for Asa (by default the chat plan's GLM Flash with maximum thought level; a larger GLM can be configured through `harr agents asa configure --zcode-model`). The main chat must not resolve material architecture decisions itself: it routes them to the dedicated architect context. Root is the only agent router; the user does not directly drive the subagent. ZCode has two entry paths at the same time: automatic material-decision escalation from root, and explicit user dialogue/analysis routed through root.

## Evidence ownership

Every Asa invocation, automatic or explicit, must be evidence-ready first.

1. For a root-owned scope, root gathers any missing repository, runtime, or contract facts under the normal Harr Workspace/tool-routing policy. If a newly created checkout/worktree is involved, it must be registered through the normal Harr Workspace flow before investigation. Root gathers facts, constraints, provenance, and exact material locators only: once a boundary is material, root must not invent, rank, compare, or choose architecture alternatives. If the user explicitly asked Asa herself to perform the deep analysis, root must not perform that deep analysis first.
2. For a delegated scope, use the existing scope owner's compact evidence handoff. For a native subagent, ask the SAME subagent for narrowly missing facts. For a named Ein, use the handoff/evidence produced under the `$ein` contract and resume the SAME Ein after Asa decides. Root must not independently reread or duplicate investigation of delegated code. Asa does not inherit subagent or Ein private history.
3. A fresh `asa-architect` spawn does NOT inherit the root conversation history. The first dispatch message must carry everything Asa needs: the request mode, the exact question, fixed constraints, and the compact verified evidence packet (including concise anchors for decisive tool-output facts). Do not assume Asa has seen any root turn.
4. On later follow-ups, send only the verified delta Asa has not already received: new root-owned facts/material/constraints since Asa's last relevant view, plus the exact question. Do not resend the whole packet. Subagent-owned facts still cross the ownership boundary as a compact handoff.

## Persistent Asa lifecycle

Use one canonical `asa-architect` subagent for the root conversation.

This contract requires the ZCode Agent tool surface. If the Agent tool is unavailable or the `asa-architect` subagent type is not offered, report that ZCode Asa orchestration requires it and stop; do not answer the material architecture decision as root, and do not substitute another subagent type.

- If this root conversation already has an `asa-architect` agent spawned under an older contract, continue that exact agent for the rest of the conversation; do not create a second Asa beside it.
- Otherwise, first contact spawns the subagent with the Agent tool (`subagent_type: "asa-architect"`). The Agent call is synchronous: its final report is Asa's answer; never synthesize an Asa answer yourself.
- After that, route every automatic decision call and every explicit user message to the SAME agent by continuing it with its agent id (SendMessage to the agent returned by the first spawn) so the persistent context is preserved. Do not spawn a fresh `asa-architect` for each decision when the previous agent id is still continuable.
- If the agent id was lost (session restart or the continuation is rejected), a fresh spawn is the recovery path; include the decisive prior conclusions as verified delta in the dispatch packet and continue from the new agent.
- Root must not continue implementation while an Asa answer is still pending: the foreground Agent call returns the answer directly, and a background continuation must wait for its completion notification before proceeding.

## Request mode

Every message sent to Asa must state the mode explicitly so the persistent role applies the correct output contract:

- `mode=architecture-decision` for automatic material decisions;
- `mode=user-dialogue` when the user is directly addressing/continuing with Asa;
- `mode=explicit-analysis` when the user asked Asa herself to deeply analyze selected material.

The mode label is routing metadata, not a substitute for the exact user question, evidence delta, fixed constraints, or delegated-scope handoff.

## Automatic material-decision route

When an unresolved material architecture decision arises, root must not choose it.

1. Make the decision evidence-ready under the ownership rules above.
2. Ask the exact question to resolve and state the fixed constraints. Include alternatives only when they were already supplied by the user, an accepted contract/design, or verified evidence; root must not manufacture or evaluate alternatives before Asa.
3. Dispatch the request to the SAME persistent Asa using the lifecycle rules above with `mode=architecture-decision`. For root-owned scope, include only the necessary verified delta/anchors. For delegated scope, include the existing subagent/Ein compact evidence handoff.
4. Asa returns the chosen solution and rationale; rejected alternatives and why; invariants and risks the implementation owner must preserve; and explicit unresolved questions, if any.
5. Return the decision to the existing implementation owner. The SAME owner continues the work.

## Explicit user dialogue and analysis

If the user addresses Asa directly, asks to ask/continue with Asa, or explicitly asks Asa herself to analyze selected code, an image, or other material, root is a transparent router after evidence preparation.

Explicit invocation does not waive evidence preparation. Root, or the existing subagent for its owned scope, first gathers the relevant surrounding facts/constraints, identifies and locates the correct material, and distinguishes known facts from open questions. Evidence preparation may be a no-op when the needed facts are already durable in Asa's own persistent context and no newer root/subagent facts are relevant.

Preserve the user's intent and relevant wording. Send the user's question to the SAME Asa with `mode=user-dialogue` or `mode=explicit-analysis` as appropriate and any required verified delta; root must not answer for Asa or perform the requested deep analysis first. Relay Asa's answer faithfully to the user, adding root commentary only when needed to distinguish transport/status or implementation consequences from Asa's own answer.

For caller-supplied material not already present in Asa's context, provide the material itself or an exact locator such as file/path/range or artifact reference. Asa may independently inspect and analyze that supplied material, including using an exact native read/view operation on a caller-supplied locator, but must not broaden the task into repository discovery or gather missing surrounding evidence herself. Discovery and evidence acquisition remain with the scope owner.

For explicit analysis, Asa returns the analysis the user requested. If the user also asked Asa to resolve an architecture question, it returns the normal decision/rationale/invariants output above. If the analysis instead discovers a new material architecture decision that the user did not ask Asa to resolve, Asa must not choose it: return the analysis plus the exact escalation question for the user. Root surfaces that question to the user; if the user asks to continue, continue the SAME Asa with the answered escalation.

## Missing evidence

For a default architecture decision, if essential evidence is missing, the existing scope owner gathers only the exact missing facts (root for root-owned scope; SAME subagent or SAME Ein for delegated scope), then root continues the SAME Asa with the same request mode. For explicit user-directed analysis/dialogue, Asa may derive facts from material already supplied; if another source is required, request that exact missing fact/material and let the scope owner locate it before the same follow-up. Do not spawn a speculative replacement Asa.

Persistence means reuse Asa whenever she is the intended architectural interlocutor; it does not mean routing unrelated implementation review through her.
