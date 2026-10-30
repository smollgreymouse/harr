# Harr orchestration skill economy audit

Status: design audit stacked on the Luna-root topology PR. No runtime/installer changes.

## What we keep from earlier orchestrator research

The useful parts of the earlier da34 / omid511 comparison survive in a smaller form:

- **delegate only when it buys something** — isolation of a large implementation context, real parallelism, or a material decision;
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
conversation / routing / integration
        |
        | local + cheap
        +----------------------------> do directly
        |
        | implementation context worth isolating
        +----------------------------> one stock Luna worker
        |                               owns that scope/phase
        |
        | material architecture decision
        +----------------------------> $asa
        |                               fresh Sol architect
        |
        | explicit external delegation
        +----------------------------> $ein <instance>
                                        Ein owns that scope/phase
```

The root is the **control plane**. Worker/Ein sessions are **execution contexts**. Asa is a **decision context**. The economical profile keeps the root on Luna High; stock native workers inherit that model unless the user configures otherwise.

Do not add a Harr-specific implementation-worker role. Do not move the same implementation context through all three layers.

## Economy invariants

1. **No agent by default.** A small/local task stays in Luna root.
2. **One owner per scope.** Root, worker, or Ein owns active implementation work; never two at once.
3. **One context per phase.** Continue the same worker/Ein session while its code context is useful.
4. **Asa is an interrupt, not a planner loop.** Call it only for a material decision.
5. **No duplicate investigation.** Root does not reread a delegated scope; Asa does not inspect the repository broadly.
6. **No Explorer pre-pass.** The implementation owner investigates its own scope.
7. **Compact handoffs only.** Transfer evidence and decisions, not transcripts or broad file dumps.
8. **Rotate on a boundary, not by habit.** New phase / independent review / unusably broad context -> fresh executor with compact handoff.
9. **Review is risk-based.** Fresh reviewer only when independent context is worth another read.
10. **Parallelism stays narrow.** One writing worker per repository by default; 2–3 workers maximum for genuinely independent scopes. Parallel writes in one repository require explicit user intent plus isolated worktrees/copies.

No mandatory plan file is part of the protocol. A plan file may be used when one already exists or is useful as a durable artifact; it is not required for delegation.

## Routing matrix

| Situation | Owner / flow |
| --- | --- |
| small/local task | Luna root |
| large but mechanical task with modest context | Luna root |
| substantial implementation whose code/tool trace should stay out of the long-lived chat | one stock Luna worker; root does not duplicate the read |
| worker needs ordinary local design choice | worker decides |
| material decision appears | compact evidence -> `$asa` -> same implementation owner continues |
| user explicitly invokes `$asa` | fresh architect immediately |
| user explicitly delegates to Ein | selected Ein session owns the delegated scope |
| Ein reports material escalation | compact evidence -> `$asa` -> resume same Ein session |
| same implementation phase needs correction | follow up same worker/Ein |
| genuinely new phase | fresh worker/Ein with validated-facts handoff |
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

The current `einherjar-worker` skill is about 500 words and repeats action semantics already present in the MCP schema.

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

- use a worker when isolating substantial code/tool context is worth the cold-start cost;
- once delegated, root treats that worker as its eyes/hands for the scope;
- follow up the same worker inside the phase;
- if it hits a material decision, preserve it while Asa decides, then continue it;
- do not create a replacement worker just because the parent spoke to Asa.

For small/local blocking work, Luna root can simply do it. This preserves da34's "delegate only when useful" behavior instead of turning every task into an agent ceremony.

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

Reuse beats restart until reuse becomes expensive.

Rotate a worker/Ein/architect when:

- the work enters a genuinely new phase with a different scope;
- independent review is desired;
- compaction/context growth has made the existing context less useful than a compact validated handoff.

The handoff contains only:

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

## Implementation order

1. Implement the compact auto-discoverable `$asa` + configurable `asa-architect`.
2. Rename/shrink `$einherjar-worker` to `$ein`; leave action semantics in MCP schema.
3. Shrink top-level `$harr` and lazy-load its existing references.
4. Remove duplicated Ein policy from generated Harr routing/skill text, leaving discoverability only.
5. Add tests for Asa implicit-selection metadata, role rendering/configuration, and skill installation/migration.
6. Measure real sessions before adding any further orchestration layer.
