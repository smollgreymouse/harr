# Harr / Asa / Ein — Luna-root topology

Status: design-only stacked PR on top of the Harr / Asa / Ein skill audit. No runtime/installer changes yet.

## Goal

Use the inexpensive model for the long-lived conversation and spend Sol only on decisions that need it.

Recommended operating topology:

```text
long-lived user chat
    Luna High
        |
        +-- ordinary/local work ------------------------------+
        |                                                     |
        +-- stock native worker(s), when useful               |
        |      implementation context / eyes and hands        |
        |                                                     |
        +-- material architecture decision?                   |
               yes                                            |
                |                                             |
                v                                             |
          asa-architect                                       |
          Sol 6.1 XHigh                                       |
          fresh compact context                               |
                |                                             |
          decision/constraints -------------------------------+
```

The root remains Luna. Asa is no longer the root coordinator; it is the expensive architect subagent.

Task size is not the routing criterion. A large mechanical migration with stable contracts stays on Luna. A small change to a protocol, lifetime, concurrency, persistence, security or subsystem boundary may require Asa immediately.

## Public surface

- `$harr` — harness operations and safety policy.
- `$asa` — request/route a material architecture decision to Harr's architect.
- `$ein` — explicit external Ein delegation.
- Stock native workers remain implementation machinery; no public `$worker` skill.

## Rule ownership

| Owner | Rules |
| --- | --- |
| Stock Codex | native worker/spawn/follow-up/wait mechanics and parallel ownership |
| Luna root | user dialogue, routing, integration and ordinary/local decisions |
| `$asa` | material-decision trigger and the hard boundary against Luna self-architecting |
| Internal `asa-architect` | architecture decision from a compact evidence packet |
| Ein MCP / `$ein` | external executor lifecycle and delegated-scope policy |
| `$harr` | Harr operational safety and repair authorization |

Do not duplicate native worker or MCP tool rules in Asa.

## The routing boundary

The difficult part is preventing Luna from solving an architectural decision itself merely because it believes it can.

**Trigger beats confidence.** Once any material trigger applies, Luna must not compare architectures or choose the design locally. It may gather narrowly missing evidence, then routes the decision to Asa.

Material triggers:

- public or cross-module API/contract;
- protocol, schema, wire-format or compatibility decision;
- ownership, lifetime, concurrency, scheduling or cancellation semantics;
- persistence, recovery, migration, durability or data-loss behavior;
- security, permissions, credentials, sandbox or trust boundary;
- subsystem/module boundary or responsibility split;
- multiple plausible non-local designs with meaningful long-term trade-offs;
- an explicit architecture/design/rethink request whose answer is not mechanically determined by existing contracts.

Not triggers by themselves:

- lots of files;
- a long migration;
- code reading/investigation;
- implementation planning when contracts are already fixed;
- local refactor/bug fix/test repair;
- a mechanical replacement that preserves existing behavior and lifecycle.

Tie-breaker: if a wrong choice can force non-local rework or alter a long-lived/external contract, route to Asa. If the choice is local and cheaply reversible, Luna owns it.

## Workflow matrix

| Situation | Flow |
| --- | --- |
| ordinary/local task | Luna works directly or uses stock native workers as Codex normally would |
| large but mechanical task | Luna/worker completes it without Asa |
| user explicitly invokes `$asa` | route the architecture question to `asa-architect` immediately |
| Luna encounters a material trigger | stop local architecture choice -> gather only missing evidence -> invoke `asa-architect` |
| worker reports a material decision | Luna forwards compact evidence to Asa; same worker continues after the decision |
| Ein returns a material `ESCALATE` | Luna invokes Asa for the decision, then resumes Ein if appropriate |
| Asa asks for missing evidence | Luna/worker gathers only that evidence and follows up the SAME architect |
| root is doing Harr repair/mutation | `$harr` safety remains root-owned; Asa may advise architecture but does not inherit/replace Harr authorization |

## Draft `$asa`

`$asa` must support both explicit user invocation and automatic Luna routing. Therefore it should remain discoverable for implicit selection rather than using `allow_implicit_invocation: false`.

Keep the skill deliberately small:

```md
---
name: asa
description: Use for a material architecture decision: public/cross-module contracts, protocol/schema compatibility, ownership/lifetime/concurrency, persistence/recovery, security/trust boundaries, subsystem boundaries, or genuinely non-local design trade-offs. Do not use merely because a task is large or mechanical.
---

When this skill applies, do not choose the material architecture in the root.

Send Harr's internal `asa-architect` a compact decision packet with the goal,
relevant invariants, concrete evidence, and the exact decision required. Use a
fresh context; do not dump the root transcript.

If evidence is missing, gather only what the architect needs. Continue the SAME
architect after supplying that evidence.

After the decision, return implementation to Luna/the existing worker or Ein
session that already owns the scope.
```

The anti-self-architecture rule belongs here because this is the policy Harr adds. Native spawn/follow-up mechanics do not.

## Automatic selection

Automatic Asa relies on normal Codex skill discovery, not a second global routing protocol.

The skill description carries the material-trigger boundary. The full body is read only when selected/invoked; ordinary turns carry only the normal skill-catalog entry.

Explicit `$asa` remains a manual override: the user is saying the decision deserves architect-grade reasoning even if Luna would otherwise classify it as local.

Do not add a second list of the same triggers to global `AGENTS.md`. One source of truth avoids drift.

### Live routing probe

Verified with `codex-free` / Codex CLI 0.162.1 on Luna Low to make the test conservative:

- a material public-protocol + ownership/lifetime prompt automatically selected the test skill and read its body;
- a large explicitly mechanical v2-client migration with fixed API/lifecycle/ownership/protocol semantics did not select the skill;
- when the selected skill instructed a fresh custom architect spawn, Codex created that subagent successfully.

This validates the intended selection path on the current client: description -> implicit skill selection -> skill policy -> architect spawn. It is still model routing behavior, so tests should lock the intended skill metadata and integration behavior as the implementation evolves.

## Internal `asa-architect`

This is a separate native Codex role, not a public skill and not the stock `worker`.

Model/effort are Harr-managed user configuration. Recommended default:

```text
model:  gpt-6.1-sol
effort: xhigh
```

Proposed CLI surface remains:

```text
harr agents asa status
harr agents asa configure
harr agents asa configure --model gpt-6.1-sol --effort xhigh
```

The root chat model is a session/UI choice, not part of the skill contract. The economical profile recommends Luna High for the main chat; Harr should not silently rewrite an already-running chat model.

Rendered architect role delta:

```toml
developer_instructions = """
You are Harr's architecture specialist, not the implementation worker.
Do not edit code and do not spawn subagents.
Work from the compact evidence supplied by the parent.
Decide only the material question asked; do not redesign unrelated areas.
Prefer existing contracts and the smallest coherent change.
If evidence is insufficient, request the exact missing facts instead of broadly
exploring the repository.
Return a concise decision, the constraints/invariants it imposes, and any
specific risk the implementation owner must verify.
"""
```

The role config also carries the Harr-managed model and reasoning effort.

Use `fork_turns: "none"`: the purpose is to keep Sol's context short and expensive reasoning focused on the actual decision rather than the long user conversation.

## Context economy

The long context stays on Luna. Code-heavy context normally stays in Luna/native workers. Sol sees only a decision packet.

A good packet contains:

- goal;
- material decision required;
- relevant existing contract/invariants;
- concrete code/runtime evidence;
- constraints already fixed by the user;
- no transcript, broad file dump or speculative design essay.

Luna must not pre-solve the decision before sending it. Otherwise the expensive architect becomes a reviewer of Luna's answer instead of the decision maker.

## Domain-skill boundary

The previous live `codex-free` probe remains relevant: a skill invoked in the root does not propagate into a fresh custom child with `fork_turns: "none"`, and merely putting the skill name in the child task does not load its body.

That is acceptable for Asa because the architect should not perform domain mutations. The root must include the specific domain constraints relevant to the decision packet and retains the domain skill's authorization/safety responsibilities.

For example, `$harr` repair authorization remains with the root. Asa may decide architecture from supplied constraints but cannot substitute for `$harr` policy.

## Failure modes to guard against

1. **Luna self-architects.** Fix: trigger beats confidence; once material, Luna may gather facts but not choose.
2. **Asa on every large task.** Fix: size/volume are explicitly non-triggers; mechanical work stays Luna.
3. **Sol receives the whole chat/codebase.** Fix: fresh architect + compact packet; ask for exact missing evidence.
4. **Asa becomes another implementation agent.** Fix: role is decision-only; implementation returns to the existing owner.
5. **Repeated fresh Sol calls for one decision.** Fix: follow up the same architect when evidence is missing.
6. **Duplicate routing rules drift.** Fix: material-trigger source of truth lives in the `$asa` skill description/body.

## Implementation delta from the first PR

1. Replace the previous root-Asa / internal `asa-worker` topology with Luna root + internal `asa-architect`.
2. Make `$asa` discoverable for automatic selection as well as explicit `$asa` invocation.
3. Configure the architect model/effort through Harr; suggest Sol 6.1 XHigh by default.
4. Keep the main chat model outside skill policy; recommend Luna High as the economical operating profile.
5. Keep stock native workers stock; no Harr-specific implementation worker role is required.
6. Preserve the existing `$ein` and `$harr` ownership boundaries.
