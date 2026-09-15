# Codex native subagent vs Codex CLI executor bridge

This note defines the first concrete Harr executor experiment: a strong Codex
planner (GPT-5.6 Sol or Terra) delegates deterministic implementation to
GPT-5.6 Luna while keeping planner and executor contexts separate.

## Two paths to compare

### A. Native Codex subagent

The planner calls the native collaboration tool with **no parent turn history**:

```text
spawn_agent(
  task_name="harr_builder",
  fork_turns="none",
  model="gpt-5.6-luna",
  reasoning_effort="low",
  message=<same Harr Execution Contract used by the CLI bridge>
)
```

Subsequent blocker resolutions go to the same child agent with the native
follow-up mechanism. The child keeps its own context; the planner receives only
the bounded Harr terminal packet.

Do not use a full-history fork for this experiment. Current Multi-Agent V2
semantics make full-history forks inherit the parent model/effort and disallow a
model override. The experiment exists specifically to avoid copying the Sol/Terra
planner history into Luna.

### B. Separate Codex CLI session

Harr starts:

```text
codex exec \
  --json \
  --model gpt-5.6-luna \
  --sandbox workspace-write \
  --cd <repo> \
  --output-schema <harr-terminal-schema.json> \
  --output-last-message <file> \
  --config 'model_reasoning_effort="low"' \
  --config 'features.multi_agent=false' \
  -
```

The adapter records the `thread.started.thread_id` event. A planner resolution
continues exactly that executor context with:

```text
codex exec ... resume <thread_id> -
```

The model is explicitly supplied again on every resume. This is intentional: the
bridge must not depend on implicit model restoration.

## Expected token/usage trade-off

The native path has the theoretical minimum handoff overhead when
`fork_turns="none"`: only the explicit execution contract is copied from the
planner. It still has its own model/system/tool context, but avoids starting an
independent CLI process and may reuse more Codex runtime machinery.

The CLI bridge sends the same contract, but a fresh Codex thread also builds its
own normal CLI/session baseline. Therefore it may consume more input/context per
new executor session. The gap should shrink on later `resume` turns because the
executor session is persistent and receives only Planner Resolution Delta
messages.

The CLI bridge nevertheless has stronger orchestration properties:

- a concrete durable thread id owned by Harr;
- explicit model selection on every turn;
- an output JSON Schema enforced by Codex itself;
- process-level cancellation and failure detection;
- easy backend substitution later;
- executor lifecycle independent from native multi-agent implementation details.

Native subagents are simpler and may be cheaper. The bridge is more portable and
observable. Harr should measure rather than assume which is the default.

## Benchmark contract

Run the same repository fixture and the same Execution Contract through both
paths. At minimum record:

1. planner turns/tool calls before delegation;
2. bytes/tokens in the execution contract;
3. executor input/output/reasoning telemetry when available;
4. number and size of BLOCKED packets;
5. number and size of Planner Resolution Delta messages;
6. task success and validation completeness;
7. changed-path violations;
8. wall time;
9. Codex subscription-usage delta when the product exposes a measurable value.

Do **not** infer subscription usage from provider token counts alone; they are a
separate metric.

Recommended fixture classes:

- trivial mechanical edit with no blocker;
- multi-file signature/config propagation;
- one intentional false planner precondition causing exactly one BLOCKED turn;
- one compile/test failure that the contract fully specifies how to repair;
- one case requiring an architectural decision, where the executor must stop
  instead of improvising.

## Initial policy

For the first Harr version:

- planner: user-selected Sol/Terra, normal persistent parent context;
- executor: Luna low by default, overridable by explicit profile;
- native subagent: `fork_turns="none"` only for the benchmark/fast path;
- CLI bridge: separate persistent Codex session, explicit Luna model on start and
  resume;
- both receive the same strict executor rules and terminal packet contract;
- neither executor may replan architecture or spawn further agents;
- Harr remains responsible for mechanical workspace/validation checks above the
  model report.
