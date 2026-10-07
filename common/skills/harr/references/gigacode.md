# GigaCode executor MCP

GigaCode is an optional Harr-managed executor for planner-to-builder delegation. Harr exposes it behind LeanCTX as the single downstream tool `gigacode::gigacode`; its schema is loaded only when needed.

The external `gigacode` CLI must already be installed, authenticated and available in `PATH`. Harr ships the MCP bridge, not the GigaCode CLI itself. The bridge treats GigaCode as a black box: it does not configure or depend on GigaCode's internal tools, shell implementation, editor, or MCP servers.

## Start

When the parent has already decided architecture, scope, invariants and acceptance criteria, prefer a plan file so the expensive parent does not resend its contents:

```text
ctx_tools
  action = "call"
  tool = "gigacode::gigacode"
  arguments = {
    "action": "start",
    "plan_path": "EXECUTION_PLAN.md"
  }
```

For a small bounded task without a plan file:

```text
arguments = {
  "action": "start",
  "prompt": "Implement the already-decided change ..."
}
```

`start` returns a persistent `session_id`. A confirmed `RUNNING` includes `startup_confirmed=true` plus the first real GigaCode model/tool activity; a merely alive process reports `STARTING`.

Optional `timeout_sec` (default 0 = unlimited) sets a positive hard wall-clock limit. Use it only for bounded tasks where automatic termination on deadline is safer than indefinite execution.

## Status without polling

Do not poll in the same parent turn. On a later continuation, check once:

```text
arguments = {
  "action": "status",
  "session_id": "<session-id>"
}
```

Status exposes `hard_timeout_sec` (0 means unlimited), `stall_elapsed_sec` (informational only; no auto-kill), `cancel_requested`, and `process_running`.

A final handoff is `DONE`, `FAILED` or `ESCALATE`. `ESCALATE` is designed to contain enough exact code evidence for the planner to decide without rereading files merely to rediscover the mismatch.

## Cancel

Explicitly cancel a running detached job:

```text
arguments = {
  "action": "cancel",
  "session_id": "<session-id>"
}
```

Returns `CANCEL_REQUESTED` on success. The worker terminates the GigaCode process tree on its next loop iteration and records a terminal handoff identifying manual cancellation. The session remains resumable. Repeated cancel on a finished or unknown session produces a clear safe response. Cancel never targets arbitrary PIDs — only the session's active job.

## Review and resume

After `DONE`, review independently. Send substantive defects back into the same executor context:

```text
arguments = {
  "action": "resume",
  "session_id": "<session-id>",
  "prompt": "Review found: <specific defect/evidence>. Required invariant: <...>. Rerun: <checks>."
}
```

Keep one session per logical implementation task. While a session is `RUNNING`, do not edit its scope in the parent or build a competing implementation. The parent may make only a tiny obvious local correction directly; iterative debugging and non-trivial empirical probes belong to the executor.

## Runtime safeguards

The bridge launches GigaCode detached, performs a short startup handshake (20s bounded, independent of timeout), and preserves the same GigaCode session for resume. The default hard timeout is 0 (unlimited); callers may set a positive `timeout_sec` to impose an explicit deadline. No-progress inactivity is tracked as informational status only — the bridge never automatically kills for inactivity.

Cancellation is explicit via `action=cancel`; there is no automatic inactivity or total-deadline cancellation unless the caller requested a positive `timeout_sec`.

Normal planner work must use only the MCP handoff. GigaCode chat/debug/runtime files under `~/.gigacode` and `~/.cache/gigacode-mcp` are bridge diagnostics and should be read only when explicitly debugging a bridge/runtime failure.