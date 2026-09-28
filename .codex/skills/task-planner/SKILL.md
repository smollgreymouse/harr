---
name: task-planner
description: Produce a self-contained implementation plan while minimizing expensive planner input. Use for non-trivial coding tasks that require repository investigation; delegate code discovery to the Codex explorer agent first, then reason from its evidence.
---

# Task Planner

The planner owns reasoning and implementation decisions. It should not spend expensive context on broad repository exploration.

## Delegate exploration first

For every non-trivial task whose implementation location, flow, dependencies, or tests are not already known from the current context, delegate repository exploration to the custom `explorer` agent before reading implementation code yourself.

Give the explorer narrow factual questions, not a vague request to "analyze the task".

Good delegation:

```text
Investigate this task and answer only:
1. Where is ownership of X decided?
2. Which code paths can change it?
3. Which callers depend on that decision?
4. Which tests cover restart/recovery?
5. Which exact symbols form the likely change surface?

Do not design a fix. Return the standard EXPLORER REPORT.
```

Bad delegation:

```text
Analyze X and tell me what we should change.
```

The explorer finds facts. The planner decides what they mean.

## Use the explorer report as primary repository context

Do not independently repeat exploration already completed by the explorer.

Read source yourself only when at least one of these is true:

1. the explorer reports ambiguity or conflicting evidence;
2. an architectural decision depends on exact implementation details not present in the report;
3. a high-risk claim needs direct verification;
4. the explorer marks the item `UNKNOWN`;
5. a small exact excerpt is required to write an unambiguous patch specification.

Keep any planner-side reads narrow and targeted.

If the first explorer report leaves a factual gap, send a follow-up question to the same role before doing broad investigation yourself.

## Planner responsibilities

Using the user request plus explorer evidence:

- determine root cause where applicable;
- make architectural and behavioral decisions;
- resolve ownership, lifetime, ordering, locking, error classification, cleanup, and API/data contracts;
- identify every affected caller and dependency;
- define implementation order;
- define validation appropriate to the task.

Do not implement code while using this skill.

## Plan artifact

Write a self-contained local plan under `.plans/` using a concise descriptive filename ending in `_PLAN.md`.

The plan is for a builder that has no access to the planner's reasoning history or explorer session. It must allow implementation without repeating repository discovery.

Record the base commit on which the explorer/planner evidence was collected.

For each implementation step include:

- exact file paths and target symbols;
- stable source anchors already established by exploration;
- current behavior;
- the exact behavioral/API/data change;
- why the change is needed;
- significant dependencies and required ordering;
- affected call sites;
- error/cleanup/lifetime semantics where relevant;
- for non-trivial edits, a unified diff or exact before/after blocks with stable anchors when practical.

Do not leave implementation-significant alternatives such as "either", "if needed", or "one approach is". Resolve them during planning.

If a decision cannot be resolved from available evidence, mark the plan as requiring further investigation and state the exact missing fact. Do not present it as builder-ready.

Separate code changes from environment- or infrastructure-dependent validation. Tests belong in the plan when the user requested them or they are needed to verify changed behavior.

The plan is a local working artifact unless the user explicitly asks to commit it.
