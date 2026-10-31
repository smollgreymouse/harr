# Harr orchestration skill economy audit

Status: audit implemented in the follow-on orchestration skills branch. The Codex orchestration layer is opt-in and disabled by default; runtime skill/installer changes match this design. Live-system installation remains separate.

## What we keep from earlier orchestrator research

The useful parts of the earlier da34 / omid511 comparison survive in a smaller form:

- **delegate only for real parallelism** — sequential implementation stays in the Luna root; native workers exist for genuinely independent parallel scopes;
- **reuse the same executor inside one phase** — follow up the worker/architect/Ein session instead of making another agent reread the same surface;
- **rotate context deliberately** — start fresh only for a genuinely new phase, independent review, or a context that has become too broad/compacted to be useful;
- **handoff facts, not history** — invariants, exact evidence, accepted decisions, checks/results, paths/symbols; never transcript replay;
- **lazy-load instructions** — keep top-level skills short and move domain detail into references/tool schemas;
- **fresh review is optional** — pay the duplicate-read cost only when risk justifies independent context.

Two rejected patterns remain rejected:

- Explorer -> Worker for implementation-bound work: the Worker rereads the same code;
- planner/root rereading a delegated implementation scope: duplicated context with no new owner.

## Context topology

```text
Luna root (long-lived)
sequential implementation / routing / integration
        |
        | independent parallel scopes only
        +----------------------------> stock worker A / B / ...
        |                               each owns one bounded scope
        |
        | unresolved material architecture decision
        +----------------------------> $asa
        |                               fresh Sol architect
        |
        | explicit external delegation
        +----------------------------> $ein <instance>
                                        Ein owns that scope/phase
```

The root is the **sequential implementation owner and control plane**. Native workers are parallel execution contexts, not context-storage helpers. Asa is a **decision context**. The economical profile keeps the root on Luna High; stock native workers inherit that model unless the user configures otherwise.

Do not add a Harr-specific implementation-worker role. Do not hand sequential implementation from worker to worker just to shed context.

## Economy invariants

1. **Sequential work stays in root.** Task size or code volume alone never justifies a native worker.
2. **Workers buy parallelism only.** Spawn them for genuinely independent scopes that can make progress concurrently.
3. **Root owns decomposition and integration.** Every worker receives a bounded, self-sufficient scope with no dependency on another active worker.
4. **Root is the sole agent router.** Native workers never spawn/fork agents or invoke Asa themselves; they escalate to root.
5. **One owner per scope.** Root, worker, or Ein owns active implementation work; never two at once.
6. **Asa is an interrupt, not a planner loop.** Call it only for an unresolved material decision.
7. **No duplicate investigation.** Root and sibling workers do not reread an active delegated scope; Asa does not inspect the repository broadly.
8. **Router-only worker escalation.** On worker -> Asa escalation, root only adds already-known global/user constraints, forwards compact evidence to Asa, then forwards the decision/invariants back. It does not re-analyze the worker scope.
9. **Pause at material boundaries.** A worker returns compact evidence instead of choosing unresolved material architecture itself.
10. **Resume the same parallel owner.** After Asa decides, follow up the paused worker rather than creating a replacement.
11. **No Explorer pre-pass.** The implementation owner investigates its own scope.
12. **Compact handoffs only.** Transfer evidence and decisions, not transcripts or broad file dumps.
13. **Review is risk-based.** Fresh reviewer only when independent context is worth another read.
14. **Parallelism stays narrow.** 2–3 workers maximum for genuinely independent scopes; parallel writes in one repository require explicit user intent plus isolated worktrees/copies.

No mandatory plan file is part of the protocol. A plan file may be used when one already exists or is useful as a durable artifact; it is not required for delegation.

## Routing matrix

| Situation | Owner / flow |
| --- | --- |
| small/local task | Luna root |
| large or code-heavy sequential task | Luna root |
| two or more genuinely independent scopes | root decomposes -> parallel stock workers -> root integrates |
| worker needs ordinary local design choice | worker decides inside its bounded scope |
| root reaches unresolved material decision | compact evidence -> `$asa` -> Luna root continues |
| worker reaches unresolved material decision | worker pauses -> compact evidence -> root routes only -> `$asa` -> root forwards decision -> SAME worker continues |
| user explicitly invokes `$asa` | fresh architect immediately |
| user explicitly delegates to Ein | selected Ein session owns the delegated scope |
| Ein reports material escalation | compact evidence -> `$asa` -> resume same Ein session |
| independent review is warranted | fresh reviewer after implementation is stable |

Task **size** is deliberately not an Asa trigger.

## `$asa` audit

The Luna-root PR has the right core idea. Keep `$asa` small and auto-discoverable.

The description is the routing classifier, so it must distinguish **materiality** from mere task size. The body should only enforce the behavior that stock Codex does not already provide.

Proposed skill:

```md
---
name: asa
description: Use for a material architecture decision involving public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local trade-offs. Do not use merely because work is large, code-heavy, or mechanical.
---

When this skill applies, do not choose the material architecture in the root.

Send `asa-architect` a compact packet: goal, exact decision required, fixed
constraints/invariants, and concrete evidence. Use fresh context; do not send
the root transcript or broad code dumps.

If the architect needs evidence, gather only the requested facts and follow up
the SAME architect.

Return the decision to the implementation owner that already has the code
context.
```

### Asa architect

Recommended default remains Sol 6.1 XHigh, configurable through Harr.

The role should be even narrower than the previous draft:

```toml
developer_instructions = """
You are Harr's material-decision specialist.
Do not implement, edit, spawn agents, or broadly inspect the repository.
Answer only the decision requested from the supplied evidence.
Prefer existing contracts and the smallest coherent change.
If evidence is insufficient, request the exact missing facts.
Return the decision plus the invariants/risks the implementation owner must keep.
"""
```

Reuse the same architect only while resolving the **same decision episode**. A later independent architecture question gets a fresh architect so expensive Sol context does not accumulate.

## `$ein` audit

The pre-migration `einherjar-worker` skill was about 500 words and repeated action semantics already present in the MCP schema.

The future `$ein` skill should keep only what changes parent behavior:

```md
---
name: ein
description: Coordinate a bounded scope already delegated to a user-selected Harr Ein executor.
---

While an Ein session is active, that session owns its delegated scope. Do not
inspect, edit, re-run checks, or independently solve the same scope in the
parent.

Judge terminal handoff evidence against the requested outcome. Ask only for
specific missing proof.

For a material design escalation, obtain the decision through Asa and resume the
SAME Ein session with only that decision/new evidence.

Use the same session for corrections in the same phase. Start fresh for a
genuinely new phase or independent review, transferring only validated facts
and constraints.
```

Everything else belongs to the named Ein MCP tool schema:

- explicit executor authorization/selection;
- start/resume/status/messages/wait/cancel arguments;
- blocking wait semantics;
- no-polling behavior;
- session identifiers and backend binding.

Remove the current preference for `plan_path` on substantial work. Durable plan files are optional artifacts, not part of the orchestration protocol.

## `$harr` audit

The current top-level `$harr` skill is about 830 words. It is correctly explicit/specialized, but once loaded it still carries unrelated Git/MR/Kubernetes detail.

Apply the omid511 lazy-load lesson more aggressively:

Top-level `$harr` should contain only:

- purpose/ownership boundary;
- cheap `status` / `doctor` entry points;
- repair authorization and fail-closed rules;
- short command index;
- instruction to load exactly one relevant reference.

Move/keep detailed flows in existing references:

- host Git / MR -> `references/git.md`;
- Kubernetes -> `references/kubernetes.md`;
- LeanCTX -> `references/leanctx.md`;
- optional MCP-specific diagnostics -> their existing reference files;
- general install/configure command catalog -> `references/operations.md`.

Do not repeat Ein authorization/action semantics in `$harr`; expose only discoverability of the shared Ein workflow and available named instances.

This makes doctor/repair turns pay for doctor policy, not for an unrelated GitLab MR procedure.

## Root/worker interaction

No new public Worker skill or Harr-specific Worker role is needed.

Stock worker behavior already supplies implementation ownership, model inheritance and native follow-up. Harr only needs the economy convention:

- keep all sequential implementation in Luna root regardless of size;
- spawn workers only for genuinely independent scopes that benefit from concurrent progress;
- root owns decomposition/integration and gives every worker a bounded, self-sufficient scope;
- once delegated, root and sibling workers do not duplicate that scope;
- if a worker hits an unresolved material decision, pause it, let Asa decide from compact evidence, then follow up the SAME worker;
- never replace a worker merely to continue the same sequential phase.

This preserves the useful part of the earlier orchestrator research without creating context islands: workers buy wall-clock parallelism, not context storage.

## Review policy

Independent review is not a mandatory final stage.

Use fresh review when one of these is true:

- user explicitly asks for independent review;
- change crosses a material contract or security/recovery boundary;
- implementation evidence is weak or contradictory;
- the cost of a missed defect clearly exceeds another read.

Otherwise the implementation owner's validation plus root integration is enough.

A reviewer receives requirements + accepted decisions + stable diff/evidence, not the implementation transcript.

## Context rotation policy

A native worker exists only for its bounded parallel scope. Reuse that same worker for follow-up inside the scope; do not chain fresh workers to advance sequential phases that belong in root.

For Ein/architect contexts, reuse beats restart until the decision/session is complete. Start fresh for a genuinely new phase or independent review, or when context growth has made a compact validated handoff cheaper.

Any handoff contains only:

- current goal/scope;
- accepted material decisions/invariants;
- files/symbols actually touched;
- completed verification and remaining failures;
- exact blockers/resources needed next.

Never copy conversation history as a handoff.

## Current-client validation retained

Live `codex-free` / Codex CLI 0.162.1 probes already established:

- material protocol + ownership/lifetime prompt can auto-select an implicit Asa-like skill;
- a large explicitly mechanical migration does not select it;
- an implicitly selected skill can spawn a fresh custom architect;
- root-invoked skill bodies do not propagate automatically to a `fork_turns:"none"` child.

Therefore:

- Asa routing can stay in the skill description/body without duplicating triggers in global `AGENTS.md`;
- architect packets must explicitly carry the relevant domain constraints;
- domain authorization/safety remains with the root.

## Implemented delta

- compact auto-discoverable `$asa` plus Harr-managed configurable `asa-architect`;
- managed `$einherjar-worker` migration to compact `$ein`, with action semantics left in the MCP schema;
- compact top-level `$harr` with existing references lazy-loaded by topic;
- generated Ein routing reduced to discoverability only;
- Codex-only orchestration guard: sequential work stays in root, native workers are parallel-only, unresolved material decisions route to `$asa`, and paused workers resume in place;
- regression coverage for Asa metadata/config rendering, host-specific orchestration routing, Ein ownership/schema split, installer migration and rollback.

Real-session token/quality measurement remains the next step before adding any further orchestration layer.
