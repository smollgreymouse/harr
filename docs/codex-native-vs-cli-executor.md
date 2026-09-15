# Codex native subagent vs Codex CLI executor bridge

This note defines the first concrete Harr executor experiment: a strong Codex
planner (GPT-5.6 Sol or Terra) delegates deterministic implementation to
GPT-5.6 Luna while keeping planner and executor contexts separate.

The repository includes an executable A/B runner:

```text
common/executor/ab_benchmark.py
```

It runs both implementations from the **same Git HEAD** in separate detached
worktrees, feeds them the same Harr Execution Contract, and records token usage
without copying the planner transcript into either Luna context.

## Two paths to compare

### A. Native Codex subagent

The planner/native benchmark parent calls the native collaboration tool with no
parent turn history:

```text
spawn_agent(
  task_name="harr_ab_builder",
  fork_turns="none",
  model="gpt-5.6-luna",
  reasoning_effort="low",
  message=<same Harr Execution Contract used by the CLI bridge>
)
```

`fork_turns="none"` is essential for this experiment. Full-history forks copy
planner history and current Multi-Agent V2 semantics also make a full-history
child inherit the parent model/reasoning. With `none`, Luna receives the explicit
executor message and builds its own context.

When the native child returns BLOCKED, the benchmark resumes the same parent
thread and asks it to send only the next Planner Resolution Delta to the
existing `harr_ab_builder` child. Spawning a replacement child on a follow-up is
reported as a benchmark failure.

The runner extracts the native child thread id from Codex JSONL
`collab_tool_call.receiver_thread_ids`. It then reads that child's own local
Codex rollout under `CODEX_HOME/sessions` and obtains:

- the Harr terminal packet;
- `token_count.info.total_token_usage`;
- observed child model/reasoning from `turn_context` when available.

This avoids estimating native Luna usage from parent prompt size.

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
  --config 'agents.enabled=false' \
  --config 'features.multi_agent=false' \
  --config 'features.multi_agent_v2.enabled=false' \
  -
```

The adapter records `thread.started.thread_id`. A planner resolution continues
exactly that executor context with `codex exec ... resume <thread_id> -` and
explicitly supplies Luna/low again on every resume.

## Running the A/B test

First prepare one deterministic Harr Execution Contract. It should already
contain every design decision; the executor is not allowed to replan. Example
shape:

```markdown
# HARR EXECUTOR CONTRACT v1

Goal: ...
Success definition: ...

## Fixed decisions
- ...

## Step B001
Target: src/foo.cpp / Foo::bar
Exact actions:
1. ...
Validation: unit
STOP if: ...

## Final validation
- unit: <exact command and expected result>
```

From a Harr checkout containing this feature:

```bash
python3 common/executor/ab_benchmark.py \
  --repo /absolute/path/to/target/repo \
  --contract /absolute/path/to/execution-contract.md \
  --allowed-path src/foo.cpp \
  --allowed-path include/foo.hpp \
  --required-step B001 \
  --required-validation unit \
  --planner-model gpt-5.6-sol \
  --planner-reasoning high \
  --executor-model gpt-5.6-luna \
  --executor-reasoning low
```

For a Terra planner, replace only:

```text
--planner-model gpt-5.6-terra
```

The source repository itself may have uncommitted changes: the benchmark does
not run against them. Both arms are detached worktrees created from the exact
current `HEAD`, so A and B start with identical committed source and cannot
contaminate each other's workspace.

If the contract intentionally contains a blocker, provide resolution deltas in
order:

```bash
  --resolution /tmp/resolution-r2.md \
  --resolution /tmp/resolution-r3.md
```

Both arms receive the same delta sequence. The CLI arm resumes the same Codex
CLI thread; the native arm sends the delta to the same native child.

By default the JSON report is saved under:

```text
~/.local/state/harr/executor/benchmarks/ab_<id>.json
```

Use `--output FILE` to choose another location. `--keep-worktrees` is available
for debugging only.

## What the report compares

The primary table is **Luna executor vs Luna executor**:

```text
metric                    native Luna    bridge Luna          B-A
input tokens                    ...             ...            ...
cached input                    ...             ...            ...
uncached input*                 ...             ...            ...
cache-write input               ...             ...            ...
output tokens                   ...             ...            ...
reasoning output                ...             ...            ...
```

`uncached input` is a derived diagnostic:

```text
max(input_tokens - cached_input_tokens, 0)
```

The native benchmark needs a small Sol/Terra orchestration turn to perform the
native `spawn_agent`/follow-up calls. That parent usage is recorded separately as
`native.orchestrator_usage` and is **not silently added to Luna usage**. This
keeps two questions distinct:

1. how much context/token work does Luna itself consume in each architecture;
2. how much extra parent orchestration is required by the native transport.

In production the actual planner already exists in a long-lived user context, so
a fresh benchmark-parent baseline is not identical to planner subscription cost.
The separate field makes that limitation explicit.

The report also records:

- exact contract byte count and SHA-256;
- parent and child/session ids;
- observed native child model/reasoning when present in rollout metadata;
- BLOCKED turn count;
- wall time;
- changed paths and scope violations;
- final Harr terminal packets;
- bridge run/session metadata.

Token telemetry is **not** the same as ChatGPT/Codex subscription usage units.
Do not convert these counters into weekly/five-hour quota percentages. If the
product exposes a separately measurable subscription-usage delta, record it as a
separate observation.

## Recommended fixture set

Do not decide from one cherry-picked edit. Run at least these task classes:

1. trivial mechanical edit with no blocker;
2. multi-file signature/config propagation;
3. one false planner precondition causing exactly one BLOCKED turn;
4. one compile/test failure where the contract fully specifies the repair;
5. one architectural ambiguity where Luna must return BLOCKED instead of
   improvising.

For less order bias, run each fixture twice:

```text
--order native-first
--order bridge-first
```

and compare the pair rather than a single run.

## Expected interpretation

Native subagents have lower orchestration/infrastructure overhead and may win on
small one-shot tasks. The CLI bridge has stronger control and observability:

- durable executor thread id owned by Harr;
- explicit model pin on every resume;
- Codex output-schema enforcement;
- process cancellation/failure detection;
- out-of-band artifacts;
- mechanical Harr completion/scope guard;
- backend can later be replaced without changing planner protocol.

The experiment exists specifically so Harr does not assume which path is cheaper.
If native Luna with `fork_turns="none"` consistently wins while preserving
BLOCKED quality and model pinning, it can become a fast path for simple tasks.
If bridge Luna wins on multi-turn tasks or is materially more reliable, the
persistent CLI bridge remains the default executor path.
