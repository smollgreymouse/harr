---
name: einherjar-worker
description: Delegate bounded code implementation, debugging, and validation to any named Harr Ein external CLI worker while the parent remains the planner.
---
<!-- harr-managed-skill-v1 -->

# Ein worker — shared execution contract

Use `<instance-name>::ein` only when the user directly instructs executor delegation. Merely having one or more instances configured is not authorization. Never choose an executor or backend automatically; keep each named instance bound to its configured backend.

This is **the single skill for every configured Ein instance**, including GigaCode. All instances have the same `start`, `resume`, `status`, `messages`, `wait`, `cancel` API via `<mcp-name>::ein`.

1. **Planner owns architecture.** Fix scope, invariants, forbidden changes, decisions and acceptance criteria first. The worker executes the bounded implementation and verification loop. Do not ask a worker to invent architecture or broaden scope.
2. **Use the user's named instance.** Do not choose an instance or backend yourself. No `backend` argument is allowed: Harr setup permanently binds each MCP name to its CLI adapter. The chosen instance cannot change on resume.
3. **Delegate complete execution.** Prefer `plan_path` for substantial implementation, or `prompt` for a small self-contained task. The worker investigates only needed code, edits, builds, tests and fixes ordinary implementation mistakes. No unsolicited commits, pushes or external changes.
4. **Startup confirmation.** `STARTING` means a process exists but genuine agent work is not yet verified. A confirmed `RUNNING` freezes the delegated scope in the parent: do not edit/read/inspect it, re-run its checks or watch intermediate diffs. Do independent planning elsewhere if useful.
5. **Supervision consumes minimal model context.** Do not automatically wait, repeatedly call `status` or fetch a transcript. `status` is a one-off snapshot for explicit user request or real dependency; `wait` is one bounded bridge-local wait when blocking is genuinely necessary; `messages` is opt-in for explicit progress requests. Never create short model-side polling loops. An expired wait does not cancel the job. Desktop live progress is display-only, not planner input.
6. **Review the handoff.** A `DONE` label is not independent proof. Use the complete structured handoff, including changed files, verification, blockers, and evidence, to assess the acceptance criteria. Inspect reported changes and verification evidence as needed; ask for specific missing proof.
7. **Escalate decisions, not trivial errors.** On `ESCALATE`, the planner resolves the exact unexpected plan/code mismatch or ambiguous decision from the worker's code evidence. Send only the decision and new evidence via `resume`. `FAILED` covers tools, timeouts, permissions and execution problems, not speculative design changes.
8. **Preserve healthy session boundaries.** Use `resume` for small corrections within the same implementation phase. For a major new phase or an independent verification, start a fresh session **after** the old one is terminal; transfer only validated facts, allowed scope, check results, logs/build-directory locations and resource limits. Do not launch overlapping workers on the same editing scope.
9. **Session identity belongs to Harr.** Pass only the returned Harr `session_id`, never vendor session IDs. Explicit `cancel` stops that session; it does not mean the execution history is erased.

The adapter-implementation interface is documented in `docs/EINHERJAR_BRIDGE_CONTRACT.md`. Named-instance setup and migration are documented in `docs/EINHERJAR_NAMED_INSTANCES_DESIGN.md`.
