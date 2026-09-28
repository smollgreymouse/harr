---
name: task-builder
description: Implement an already prepared self-contained plan without repeating repository exploration or redesigning it. Use in the cheap builder session after the planner has produced a builder-ready plan.
---

# Task Builder

The builder executes a ready implementation plan. The plan is the source of truth for design decisions.

## Start from the plan

Read the selected plan completely before editing.

Do not begin with an architecture review, repository inventory, broad CodeGraph exploration, or a search for "all related files". The planner/explorer stage already did that work.

Use the paths, symbols, anchors, diffs, and contracts in the plan as addresses for implementation.

If the plan records a base commit and current `HEAD` differs, do not automatically reread the repository. First try to apply the planned changes using stable anchors. Shifted line numbers are not a conflict.

## Allowed narrow investigation

Read code only for a concrete obstacle:

- a planned anchor no longer matches;
- a patch does not apply mechanically;
- the current code contradicts a stated plan fact;
- a build/test failure points at an immediate dependency;
- the new base changes the affected local contract.

Keep investigation restricted to the affected location and immediate dependency.

Do not redesign the solution or expand scope. If the plan lacks an implementation-significant decision, record the exact blocker instead of inventing architecture. Continue independent unblocked steps when possible.

## Implementation discipline

- preserve the planner's decisions;
- make only in-scope changes;
- adapt mechanical differences without changing semantics;
- update every call site explicitly named by the plan;
- preserve the project's Git/tool/build/test policies;
- inspect the final diff for plan compliance and unrelated changes.

Do not modify the plan unless the user explicitly requests it.

Run builds/tests only when required by the user, the plan, or the project's explicit completion policy. Report what was run and what was not available.

## Completion report

Return:

- implemented plan steps;
- changed files;
- deviations from the plan, if any, with reason;
- validation performed and results;
- unresolved blockers.

Do not claim completion for blocked or unvalidated requirements.
