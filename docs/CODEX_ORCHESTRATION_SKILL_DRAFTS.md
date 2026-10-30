# Harr / Asa / Ein skill audit

Status: design-only PR, rebased on Harr 0.3.1. No runtime/installer changes.

## Result

Public surface stays **Harr / Asa / Ein**:

- `$harr` — existing harness operations and safety policy.
- `$asa` — explicit coordinator mode.
- `$ein` — explicit external Ein delegation.
- Native workers remain internal; no public `$worker` / `$exec` skill.

Rule ownership is strict:

| Owner | Rules |
| --- | --- |
| Stock Codex | native spawn/follow-up/wait, worker ownership and parallelism |
| Internal `asa-worker` | Asa-specific child behavior; model/effort come from Harr-managed user configuration |
| `$asa` | delegated-scope ownership, root non-duplication, escalation boundary and context reuse |
| Ein MCP schema | actions, arguments, wait/status/messages and no-polling semantics |
| `$ein` | parent/Ein scope ownership, escalation and terminal handoff review |
| `$harr` | doctor/repair authorization and Harr operational safety |

Asa coordinates only; it never weakens Harr or Ein rules.

## Workflow matrix

| Invocation | Flow | Extra rule |
| --- | --- | --- |
| none | Current chat works directly | none |
| `$asa`, mechanical/local task | one Asa worker owns read -> understand -> local design -> implement -> validate | worker is Asa's eyes and hands; root does not duplicate the implementation read |
| `$asa`, material decision appears | worker returns compact evidence -> root decides -> same worker continues | escalation is exceptional; preserve worker code context |
| `$asa`, independent scopes | stock native parallel workers | rely on stock ownership/disjoint-write rules |
| `$ein <instance>` | parent delegates scope and continues | active delegated scope belongs to Ein until terminal handoff |
| `$asa + $ein <instance>` | Asa coordinates native and/or explicit Ein scopes | never duplicate one active scope across executors; Asa handles material `ESCALATE` |
| `$harr + $asa/$ein` | coordination/execution around Harr operations | fresh Asa workers do not inherit invoked `$harr` skill policy; keep Harr repair/mutations in root and delegate investigation/evidence only |

Independent review is allowed but is not a core Asa rule.

### Live propagation check

Verified with `codex-free` on Codex CLI 0.162.1: an explicitly invoked root test skill was present in the parent rollout but absent from a fresh custom child created with `fork_turns: "none"`. Putting the skill name into the child task text also did not load its body. Therefore Asa must not assume domain-skill policy propagation to fresh workers.

## Duplication audit

Remove these from skill text because another layer already owns them:

- native agent tool mechanics, waits, ownership, disjoint writes and integration guidance -> stock Codex;
- per-spawn model/effort arguments -> Harr-managed Asa configuration rendered into the internal role;
- generic build/test/commit/push permissions -> global/project policy;
- Ein action/session/wait/status/messages/polling details -> Ein MCP schema;
- current `$harr`/generated routing copies of Ein authorization/action rules -> reduce to discoverability only (`$ein` + available instance names).

Do not invent a parallel message protocol or semantic labels. Stock Codex already carries bounded assignment, incremental follow-up, and the child's final answer without transcript replay. Extra ASSIGN/FOLLOWUP/RESULT/DECISION labels would only add payload text.

## Draft `$asa`

```md
---
name: asa
description: Coordinate decision-heavy coding work while preserving implementation context in Harr's internal native worker.
---

For each implementation-bound scope, spawn `asa-worker` with
`fork_turns: "none"`. Do not insert an Explorer pre-pass.

Once a scope is delegated, treat that worker as Asa's eyes and hands for the
scope. The worker normally owns read -> understand -> local design -> implement
-> validate. Do not independently search/read the same implementation surface.

Escalation to Asa is exceptional. If the worker reaches a material architecture,
contract, ownership/lifetime/concurrency, persistence/recovery/security, or
scope decision, it returns compact evidence. Decide in the root, then continue
the SAME worker with native follow-up.

If no material decision appears, let the worker finish end-to-end. A clean,
mechanical task should require almost no root implementation work.

Inspect the delegated implementation surface in the root only when worker
evidence is insufficient for a material decision or final integration check.
Do not assign an active Ein scope to a native worker.
```

`$asa` is explicit-only via `policy.allow_implicit_invocation: false`.

## Internal `asa-worker`

Do not override stock `worker`; use a separate internal role so non-Asa workers
keep native behavior.

Model and reasoning effort are **user configuration**, not skill policy. Harr is
the source of truth and renders them into the role. Proposed CLI surface:

```text
harr agents asa status
harr agents asa configure
harr agents asa configure --model gpt-6-luna --effort high
```

`configure` follows the existing Harr pattern: persist Harr-owned configuration
and apply the rendered Codex role. `$harr` may invoke these commands when the
user asks conversationally to configure Asa. The skill itself never hardcodes a
model. The configure UI may suggest Luna High, but the persisted user choice is
authoritative.

The rendered role contains only the chosen model/effort plus the small policy
delta:

```toml
developer_instructions = """
Do not spawn subagents.
Own routine local decisions inside the delegated implementation scope.
Escalate only a material architecture/contract/ownership/concurrency/persistence/
security/scope decision; return compact evidence and stop at that boundary.
After parent follow-up, reuse existing context and continue.
Keep handoffs compact.
"""
```

This role is implementation detail, not a public skill.

## Draft rename `$ein`

```md
---
name: ein
description: Coordinate bounded work delegated to a user-selected Harr Ein external executor.
---

The parent owns scope and material decisions. While Ein is active, its delegated
scope belongs to Ein; the parent works only outside that scope.

On terminal handoff, evaluate acceptance evidence. On `ESCALATE`, make the
material decision and resume the same session when continuing the same phase.
Use a fresh session for a genuinely new phase or independent review.
```

`$ein` is explicit-only. Executor selection/authorization remains defined by
the Ein MCP tool, not duplicated in the skill.

## Implementation delta

1. Add explicit-only `$asa` and internal `asa-worker`.
2. Add Harr-managed Asa model/effort configuration plus `status/configure`; `$harr` is the conversational front-end to that CLI state.
3. Rename `$einherjar-worker` to explicit-only `$ein` and update Harr references/tests.
4. Collapse generated Ein routing/`$harr` text to discoverability only; keep authorization/action semantics in `ein_tool_schema.json`.
5. Leave native-agent mechanics in Codex rather than restating them in `$asa`.
6. Keep `$harr` repair/mutations root-owned for fresh Asa workers; current Codex does not propagate invoked domain-skill bodies across `fork_turns: "none"`.
