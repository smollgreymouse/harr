---
name: ein
description: Coordinate a bounded scope explicitly delegated by the user through a named Harr Ein external executor. Ein is an MCP executor transport, not a Codex agent, and only the root may invoke it.
---
<!-- harr-managed-skill-v1 -->

# Ein

Ein is a root-owned MCP transport to an external executor. Only the root may call `start`, `resume`, `status`, `messages`, `wait`, or `cancel`. Never treat Ein as a Codex subagent and never let another agent invoke it.

The user's explicit delegation authorizes `start` for that bounded scope. A later `resume` of the SAME Ein session within that same delegated scope is transport continuation, not a new delegation: do not ask for a second authorization merely to return a root decision, correction, or requested missing evidence to the same executor. A new scope or genuinely new phase requires a new explicit delegation.

## Scope ownership state machine

- `STARTING` / `RUNNING`: the Ein session owns the delegated scope. Root must not inspect, edit, rerun checks, or independently solve it.
- `ESCALATE`: execution is paused. The SAME Ein session remains the evidence owner and retains the delegated scope. The escalation returns only to root. Root must not reread or re-analyze the delegated scope; use Ein's compact handoff/evidence. If the escalation is a material architecture decision, root routes that handoff through the SAME persistent Asa, then sends only Asa's decision/invariants or specifically requested new evidence back with `resume` to the SAME Ein session. For other escalations, root decides what to do next under its normal routing policy, including asking the user when required. Ein never routes the escalation itself and root must not implement inside the paused scope.
- `FAILED`: the current executor turn ended unsuccessfully. Treat the workspace as potentially partially modified. Root either resumes the SAME session with a bounded correction/missing-proof request when the session is resumable, or explicitly abandons the delegation before taking the scope back. Never infer a clean workspace from an empty `changed` array on failure.
- `DONE`: the delegation releases the scope back to root. Judge the terminal handoff and trusted runtime provenance against the requested outcome. Do not duplicate Ein's implementation or rerun its checks merely for reassurance. If proof is missing or inconsistent, request the exact missing proof through `resume` on the SAME session instead.
- `cancel`: cancellation is explicit abandonment of active execution. Ownership returns to root only after cancellation is terminal. The workspace may contain partial edits; inspect trusted runtime provenance/dirty state before reusing the scope.
- A bounded `wait` timeout does not change ownership or cancel execution.

## Start contract

Prefer `plan_path` when a durable implementation plan already exists. A direct `prompt` must still be a self-contained execution contract: goal, bounded scope, fixed design decisions/constraints, non-goals when relevant, acceptance criteria, and required validation. Do not send an underspecified request and ask the executor to design the solution.

## Escalation and resume

Every `ESCALATE` returns to root; Ein never routes an escalation anywhere itself. Root owns the next decision. When root resumes after an escalation, correction, or missing-proof request, send only the delta needed by the existing session, but make that delta complete:

- the decision/correction;
- invariants and constraints to preserve;
- disposition of any already-made edits when relevant;
- changed acceptance criteria, if any;
- exact validation/proof now required.

Use the SAME session for corrections and escalation continuation in the same delegated scope.

## Supervision

Do not poll normal execution. `status`, `messages`, and bounded `wait` are used only when the user explicitly asks for status/progress/waiting, or when recovery requires checking persisted state because normal async completion was unavailable. Async UI notification is best-effort; persisted Ein session state is authoritative.

Action arguments, backend binding, session identifiers, and transport-specific details are defined by the named Ein MCP tool.
