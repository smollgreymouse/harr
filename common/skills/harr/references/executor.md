# External executor bridge

The executor bridge is optional and explicit-use only. Its first backend is a
separate persistent Codex CLI session using `gpt-5.6-luna` with low reasoning by
default. The parent Codex conversation remains the planner/orchestrator and may
use Sol or Terra independently.

## Explicit invocation

Treat these as explicit delegation requests:

```text
@builder <task>
$harr-builder <task>
сделай через builder
передай реализацию executor-у
```

Never pass the raw user text directly to the executor. First investigate the
repository using normal Harr routing (CodeGraph first, then targeted LeanCTX
calls) and remove design ambiguity.

## Planner gate

Before `executor::start`, know all of the following:

1. exact observable goal;
2. root cause/change reason, or explicit not-applicable;
3. exact/narrow allowed paths;
4. affected symbols and dependency/call flow;
5. ordered implementation steps with fixed decisions;
6. invariants and forbidden changes;
7. exact validation checks and expected outcomes;
8. STOP/BLOCKED conditions;
9. completion definition.

If the plan still says things like “choose the best API”, “redesign if needed”,
or “decide ownership”, do not delegate yet.

## Execution Contract

Make steps small enough for a non-reasoning executor. Every step should name its
target file/symbol, preconditions, exact actions, expected result, validation,
and conditions that require BLOCKED instead of improvisation.

Call `executor::start` with the Markdown contract plus mechanical fields:

- `allowed_paths`: exact paths / directory prefixes / narrow globs;
- `required_steps`: every step id required for DONE;
- `required_validation`: labels that must be PASS for DONE.

Harr mechanically audits these fields. Luna's own `changed_files` and DONE claim
are not trusted when Harr can verify the workspace or completion packet itself.

## Conversation protocol

`start` returns quickly with `RUNNING` and a sequence number. Use bounded
`executor::wait(run_id, after_sequence=<last sequence>)`; do not stream or poll
builder chatter into the planner context.

On `BLOCKED`, inspect the compact blocker first. If it contains enough evidence,
resolve the decision in the parent planner context and call
`executor::continue` with:

- the same run id;
- the exact BLOCKED `sequence` as `expected_sequence`;
- only a Planner Resolution Delta.

Do not resend the whole Execution Contract. The same Codex CLI thread is
resumed, so the executor keeps its own accumulated context. A stale sequence is
rejected.

Use `executor::inspect` only for a bounded artifact fragment when the blocker
packet is insufficient. Do not pull the full executor transcript by default.

`executor::cancel` terminates a running child process or closes a blocked run.
It does not revert workspace edits.

## Isolation and recursion

The executor child runs with `workspace-write`, multi-agent spawning disabled,
and hard prompt rules forbidding replanning, web, commit/push/publish and
external writes. `HARR_EXECUTOR_CHILD=1` disables the executor MCP inside the
child itself, preventing recursive executor spawning through LeanCTX.

This is still a post-edit workspace guard, not a filesystem sandbox restricted
to `allowed_paths`: if the child changes an out-of-scope path, Harr reports
`FAILED_GUARDRAIL` and does not auto-revert it.

## Native subagent A/B path

A native Codex child with `fork_turns="none"`, Luna and the same Execution
Contract is the comparison fast path. Do not use a full-history fork for the
cost benchmark: that copies planner history and, on current Multi-Agent V2
semantics, prevents model/effort override. See
`docs/codex-native-vs-cli-executor.md` for the benchmark contract.
