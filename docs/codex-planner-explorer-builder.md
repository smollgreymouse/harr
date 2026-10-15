# Codex planner / explorer / builder workflow

This repository contains a Codex-native split intended to keep expensive planner context small:

```text
           expensive reasoning
        +----------------------+
        | Planner / GPT-6 Sol  |
        +----------+-----------+
                   |
          factual questions
                   v
        +----------------------+
        | Explorer / GPT-6 Luna|
        | read-only            |
        +----------+-----------+
                   |
          compact evidence
                   v
        +----------------------+
        | Planner / GPT-6 Sol  |
        | decisions + plan     |
        +----------+-----------+
                   |
            builder-ready plan
                   v
        +----------------------+
        | Builder / GPT-6 Luna |
        | implementation       |
        +----------------------+
```

All three roles are available as project-scoped Codex subagents:

- `.codex/agents/planner.toml` — GPT-6 Sol, high reasoning, read-only;
- `.codex/agents/explorer.toml` — GPT-6 Luna, medium reasoning, read-only;
- `.codex/agents/builder.toml` — GPT-6 Luna, medium reasoning, workspace-write.

Their reusable behavioral contracts live in repo-scoped skills.

## Skills

- `$code-explorer` — factual repository investigation and a compact `EXPLORER REPORT`.
- `$task-planner` — delegates discovery to `explorer`, makes the design decisions, and writes a self-contained local plan.
- `$task-builder` — implements that plan without redoing broad discovery.

Codex discovers repo-scoped skills from `.codex/skills/<skill>/SKILL.md`.

## Planner usage

Invoke the project planner subagent for planning work. Its profile is already pinned to GPT-6 Sol/high and instructed to delegate broad code discovery to explorer.

Equivalent task contract:

```text
Use $task-planner for this task.
Delegate repository discovery to the explorer agent.
Use its report as the primary code context and do not repeat broad exploration yourself.
Produce a builder-ready plan; do not implement it.
<task>
```

The planner should delegate concrete factual questions. The explorer must not choose the fix.

The planner may directly inspect a narrow source fragment only when the explorer report is ambiguous, contradictory, `UNKNOWN`, or insufficient for a high-impact decision.

## Explorer usage

The planner should invoke the `explorer` subagent with narrow questions. Explorer is pinned to GPT-6 Luna and read-only.

Typical request:

```text
Investigate only these questions:
1. Where is X decided?
2. Which code paths can change it?
3. Which callers and tests depend on it?
4. Which exact symbols form the likely change surface?

Do not design a fix.
Return the standard EXPLORER REPORT.
```

The report is the compression boundary between repository reading and expensive planner reasoning.

## Builder usage

Invoke the project `builder` subagent with the finished plan. Its profile is already pinned to GPT-6 Luna with workspace-write access.

Equivalent task contract:

```text
Use $task-builder.
Implement .plans/<name>_PLAN.md exactly.
Do not repeat repository exploration or redesign the solution.
<validation requirements>
```

Keeping planner, explorer, and builder in separate contexts prevents read-heavy exploration and implementation chatter from inflating the expensive planner context.

## Why the explorer is separate

Repository discovery is usually input-heavy and evidence-oriented. Architectural decisions are reasoning-heavy. Splitting those responsibilities lets the planner consume a compact map of the code instead of the raw code used to build that map.

The boundary is deliberate:

- Explorer: facts, paths, symbols, flows, tests, invariants, ambiguities.
- Planner: root cause, architecture, contracts, sequence, exact plan.
- Builder: edits, mechanical adaptation, validation.

## Harr integration

The explorer follows Harr's existing tool-routing policy. Cross-file investigation starts with CodeGraph through LeanCTX; it does not duplicate the same investigation through alternate tools. Exact reads/searches are reserved for unresolved evidence.

OpenCode is intentionally out of scope for this workflow.
