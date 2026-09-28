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

The explorer is project-scoped at `.codex/agents/explorer.toml`. It pins GPT-6 Luna, medium reasoning, and a read-only sandbox. Planner and builder are workflows expressed as repo-scoped skills rather than additional agent profiles.

## Skills

- `$code-explorer` — factual repository investigation and a compact `EXPLORER REPORT`.
- `$task-planner` — delegates discovery to `explorer`, makes the design decisions, and writes a self-contained local plan.
- `$task-builder` — implements that plan without redoing broad discovery.

Codex discovers repo-scoped skills from `.codex/skills/<skill>/SKILL.md`.

## Planner usage

Run the planner in the expensive model/context (for example GPT-6 Sol) and request the planner skill:

```text
Use $task-planner for this task.
Delegate repository discovery to the explorer agent.
Use its report as the primary code context and do not repeat broad exploration yourself.
Produce a builder-ready plan; do not implement it.
<task>
```

The planner should delegate concrete factual questions. The explorer must not choose the fix.

The planner may directly inspect a narrow source fragment only when the explorer report is ambiguous, contradictory, `UNKNOWN`, or insufficient for a high-impact decision.

## Builder usage

Start a separate cheap builder context/model (for example GPT-6 Luna) and give it the plan:

```text
Use $task-builder.
Implement .plans/<name>_PLAN.md exactly.
Do not repeat repository exploration or redesign the solution.
<validation requirements>
```

Keeping planner and builder in separate contexts prevents the builder's implementation chatter and diffs from inflating the planner context, while the explorer absorbs the read-heavy repository work.

## Why the explorer is separate

Repository discovery is usually input-heavy and evidence-oriented. Architectural decisions are reasoning-heavy. Splitting those responsibilities lets the planner consume a compact map of the code instead of the raw code used to build that map.

The boundary is deliberate:

- Explorer: facts, paths, symbols, flows, tests, invariants, ambiguities.
- Planner: root cause, architecture, contracts, sequence, exact plan.
- Builder: edits, mechanical adaptation, validation.

## Harr integration

The explorer follows Harr's existing tool-routing policy. Cross-file investigation starts with CodeGraph through LeanCTX; it does not duplicate the same investigation through alternate tools. Exact reads/searches are reserved for unresolved evidence.

OpenCode is intentionally out of scope for this workflow.
