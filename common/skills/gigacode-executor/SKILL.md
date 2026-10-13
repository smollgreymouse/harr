---
name: gigacode-executor
description: Delegate bounded code implementation, debugging, and test loops to Harr GigaCode while the parent stays planner and decision-maker.
---
<!-- harr-managed-skill-v1 -->

# GigaCode executor

1. **Contract.** Parent fixes architecture, scope, forbidden changes, invariants and acceptance criteria. Delegate the entire implementation + verification loop using a plan path or concise self-contained prompt. GigaCode handles code investigation, edits, tests and ordinary fixes; the parent does not duplicate them.
2. **Handoff.** Trust the compact terminal `DONE` report when it maps each criterion to actual check results and covers scope. For missing proof, ask the worker for that specific evidence. On `ESCALATE`, decide the minimal architectural question and send the decision back. Independently investigate only a concrete contradiction.
3. **Session boundaries.** Keep `resume` for small corrections within a healthy phase. Between substantial phases (e.g. implementation → independent verification), start fresh *after* the prior job finishes; transfer only the remaining task, decisions, repository/commit, allowed scope, verified results/log paths, existing build directory and resource limits. Never duplicate an active job or discard build caches. Rotate early if the session repeatedly confuses stale state.

**Use the MCP tool's own description for actions, timeouts and waiting.** Never run parent-side polling or fetch the worker transcript during ordinary supervision. Live progress belongs in the app-only panel, not Sol's context.
