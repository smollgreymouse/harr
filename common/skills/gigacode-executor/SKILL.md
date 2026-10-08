---
name: gigacode-executor
description: Delegate substantial implementation, debugging, build/test loops, and mechanical repository work to the optional Harr GigaCode executor after architecture, scope, invariants, and acceptance criteria are fixed. Use to minimize expensive parent-model work. Do not use GigaCode to choose architecture or resolve ambiguous product/design decisions.
---
<!-- harr-managed-skill-v1 -->

# GigaCode executor

Use this skill to keep the parent model in the **planner/decision-maker** role and GigaCode in the **implementation/verification** role.

The optimization target is not merely "GigaCode writes code". It is:

> one parent decision/contract → one GigaCode implementation + self-verification loop → one compact terminal handoff.

The parent must not reproduce the executor's investigation, implementation, debugging, or verification work.

## Responsibility boundary

### Parent owns

- root cause and architectural decisions;
- task scope and forbidden changes;
- invariants and compatibility constraints;
- acceptance criteria and the required validation matrix;
- decisions requested by an `ESCALATE`;
- final user-facing interpretation of an accepted handoff;
- visual/product/artistic judgment when that judgment itself is the task.

### GigaCode owns

Once the contract is fixed, GigaCode owns the entire execution loop:

- implementation-oriented repository reading;
- editing all delegated files;
- local implementation choices that do not change architecture;
- fixtures and test details inside the accepted test matrix;
- build/test/lint/diagnostic commands authorized by the contract;
- ordinary compile/test/debug/fix iterations;
- non-trivial empirical probes needed to validate implementation;
- final diff/scope review;
- mapping every acceptance criterion to evidence;
- correction of ordinary implementation defects before reporting `DONE`.

A compiler error, failing fixture, assertion mistake, formatting problem, or local implementation bug is **not** an architectural escalation. GigaCode fixes it itself.

## Before start

Do enough parent investigation to make the execution contract self-contained, then stop investigating implementation details.

Prefer a plan file when the task is substantial. The contract must contain:

1. Goal and before/after behavior.
2. Chosen architecture and change points.
3. Allowed scope/files and forbidden changes.
4. Invariants and compatibility requirements.
5. Acceptance matrix: criterion → expected result → validation.
6. Build/test command rules, including known build directory/resource limits when relevant.
7. `DONE`: implementation, requested validation, criterion coverage, and final diff/scope self-review are complete.
8. `ESCALATE`: a material assumption is wrong or an architectural/product decision outside the contract is required.
9. Any Git/external-write restrictions.

Do not ask GigaCode to "investigate and decide the best architecture". If architecture is not fixed, the parent is not ready to delegate.

## Start

GigaCode is behind Harr/LeanCTX as exactly one downstream tool: `gigacode::gigacode`.

Use `ctx_tools` with an exact call:

```text
action = "call"
tool = "gigacode::gigacode"
arguments = {
  "action": "start",
  "plan_path": "<workspace-relative-or-absolute-plan>"
}
```

Use a direct `prompt` only for a bounded task that is already as precise as a plan.

Keep the returned `session_id`. Reuse that same session for ordinary corrections and architectural decisions; do not start a fresh executor context for every iteration.

## WAIT ONLY phase

After `start` or `resume` reports confirmed `RUNNING`, the delegated scope belongs to GigaCode.

Until a terminal handoff:

- do **not** read/search/glob delegated source files;
- do **not** inspect intermediate diffs;
- do **not** open generated artifacts merely to supervise progress;
- do **not** run builds/tests/probes for the delegated task;
- do **not** edit the delegated scope or build a parallel implementation;
- do **not** create review/check scripts;
- do **not** inspect GigaCode chat/debug/runtime files or process internals.

If completion is needed in the current interaction, the only normal operation is another compact `status` call. Repeated `RUNNING` states are transport/waiting events, not invitations to reason about implementation.

If the user asks for progress while the worker is running, report only the public state (for example, `RUNNING` and elapsed time). Do not summarize internal executor activity.

## Terminal handoff

### DONE — contract acceptance, not code review

By default, **accept the result from the structured handoff**. Do not independently reread all changed functions, rerun the same tests, or build a second validation harness.

Check only the handoff contract:

- every acceptance criterion is represented by explicit verification evidence;
- every claimed validation has a result/exit outcome;
- GigaCode reports final diff/scope self-review;
- no unresolved blocker or unverified criterion remains;
- the summary does not contradict the contract.

If this is complete, accept `DONE` and continue.

If evidence is missing or vague, **do not collect it yourself first**. Resume the same GigaCode session and request exactly the missing proof:

```text
{
  "action": "resume",
  "session_id": "...",
  "prompt": "Handoff is missing evidence for criterion C3. Verify C3, include the exact check/result, perform final scope review, and return a complete handoff. Do not redesign."
}
```

### When the parent may inspect code/artifacts after DONE

Only with a concrete reason:

- the handoff contradicts itself or the fixed architecture;
- GigaCode explicitly reports an unresolved fact needed for a planner decision;
- the change crosses a security/irreversible/external boundary that requires independent confirmation;
- visual/artistic/product acceptance is explicitly owned by the parent/user;
- the user explicitly asks for an independent code review.

Even then, answer **one specific question with minimum evidence**. Do not fall back to full-diff rereading or duplicate test execution.

If a defect is found, send the evidence and invariant to the **same** GigaCode session via `resume`. GigaCode owns the fix and revalidation.

### ESCALATE

Use the supplied expected/observed/evidence/decision-needed packet first. The executor should provide enough decisive evidence that the parent normally does not need to rediscover the mismatch from source.

Make the architectural/product decision, then `resume` the same session with only the decision/delta. Do not resend the whole plan.

If the escalation packet itself lacks decisive evidence, resume and request that evidence instead of performing broad repository investigation.

### FAILED

Execution, network, tool, or environment failures are not code-review triggers.

- If retryable and the session exists, resume the same session.
- If the process never established a reusable session, start again from the same contract.
- Do not inspect implementation files merely because the executor transport failed.
- Debug GigaCode bridge internals only when the task is explicitly bridge/runtime diagnosis.

## Parent direct edits

After delegation, parent direct edits are exceptional. They are acceptable only for a truly trivial correction that:

- is a few obvious lines in one location;
- requires no design choice;
- requires no debug/test loop;
- is cheaper than a resume without weakening ownership.

Anything spanning multiple functions/files or requiring validation belongs back to GigaCode.

## Acceptance rule

The parent is responsible for the **quality of the contract and decisions**, not for re-performing the executor's work.

A healthy normal task should consume parent effort roughly as:

```text
architecture / contract
        ↓
GigaCode start
        ↓
WAIT ONLY (status)
        ↓
DONE handoff
        ↓
contract acceptance
```

Extra parent source reads, test reruns, or implementation edits after delegation require a named exception from this skill.
