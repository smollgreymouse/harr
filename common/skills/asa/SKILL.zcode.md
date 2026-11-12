---
name: asa
description: Automatically use for an unresolved material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not auto-use when the user or an accepted design already fixed the decision, or merely because work is large, code-heavy, mechanical, or only needs analysis. An explicit user invocation may also address Asa directly or request bounded architect-grade analysis of selected code, an image, or other material; every invocation remains evidence-first, and discovery/selection of that material remains with root or the existing scope owner.
---
<!-- harr-managed-skill-v1 -->

# Asa

Asa is the architectural interlocutor of the whole root conversation, routed through the persistent saved workflow `asa` (installed at `~/.zcode/workflows/asa.dwf.ts`), whose architect runs on the model configured for Asa (`harr agents asa configure --zcode-model`). The main chat must not resolve material architecture decisions itself: it routes them to the dedicated architect run. Root is the only agent router; the user does not directly drive the workflow. ZCode has two entry paths at the same time: automatic material-decision escalation from root, and explicit user dialogue/analysis routed through root.

## Evidence ownership

Every Asa invocation, automatic or explicit, must be evidence-ready first.

1. For a root-owned scope, root gathers any missing repository, runtime, or contract facts under the normal Harr Workspace/tool-routing policy. If a newly created checkout/worktree is involved, it must be registered through the normal Harr Workspace flow before investigation. Root gathers facts, constraints, provenance, and exact material locators only: once a boundary is material, root must not invent, rank, compare, or choose architecture alternatives. If the user explicitly asked Asa herself to perform the deep analysis, root must not perform that deep analysis first.
2. For a delegated scope, use the existing scope owner's compact evidence handoff. For a native subagent, ask the SAME subagent for narrowly missing facts. For a named Ein, use the handoff/evidence produced under the `$ein` contract and resume the SAME Ein after Asa decides. Root must not independently reread or duplicate investigation of delegated code. Asa does not inherit subagent or Ein private history.
3. The workflow architect reads the root session history itself: root passes the session id, the request mode, the exact question, and fixed constraints — never a pre-curated evidence packet. Choosing what in the history matters is the architect's job, not the root's.
4. Root still performs its own evidence preparation under the normal routing policy BEFORE invoking Asa (the history the architect reads must contain it), and the dispatch states the exact question and fixed constraints.

## Persistent Asa lifecycle

Asa is the persistent saved workflow `asa` for the whole root conversation.

This contract requires the ZCode workflow surface. If the CreateWorkflow tool is unavailable or the saved `asa` workflow is missing, report that ZCode Asa orchestration requires it and stop; do not answer the material architecture decision as root, and do not substitute another mechanism.

- Invoke Asa only through the saved workflow: `CreateWorkflow` with `saved: { name: "asa", args: { mode, question, root_session_id } }`. The run executes in the background; its completion notification carries the decision. A request expecting an Asa answer is not complete until that notification arrives — never synthesize an Asa answer yourself.
- `root_session_id` is THIS root chat's session id: the newest `~/.zcode/cli/rollout/model-io-sess_<id>.jsonl`. The workflow's architect reads the root session history itself — the whole chat, including the evidence preparation — so root passes a pointer, not a summary.
- Every automatic decision, follow-up, and explicit user message goes to the SAME saved workflow with the same `root_session_id`; the architect re-reads the root history, which now also carries Asa's earlier answers (root relays them into the chat). Do not substitute other mechanisms per decision.
- If the configured Asa model is unavailable (provider error), report that transport state instead of answering the material decision as root.

## Architect reading and tool discipline

The workflow architect has the standard agent toolset, and the contract fences it deliberately. Root does not need to truncate or summarize the conversation for Asa — the architect reads economically on its own:

- It orients from the session summary, then reads messages from the end backwards, page by page, and stops when the request's context is covered — the tail carries the current task and the evidence preparation.
- It reads exactly one session: this root chat. No repository exploration, no shell, no gateway or MCP calls, no file edits, no spawning, no other sessions.
- Missing essential evidence comes back as explicit open questions for the existing scope owner to gather — root must therefore complete its own evidence preparation under the normal routing policy BEFORE invoking Asa, so the history the architect reads contains it.
- The decision report cites what the architect relied on and marks what it could not verify; anything it could not confirm arrives as `unconfirmed` rather than silently assumed.

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
