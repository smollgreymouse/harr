# GigaCode executor MCP

GigaCode is an optional Harr-managed executor for planner-to-builder delegation. Harr exposes it behind LeanCTX as the single downstream tool `gigacode::gigacode`; its schema is loaded only when needed.

The external `gigacode` CLI must already be installed, authenticated and available in `PATH`. Harr ships the MCP bridge, not the GigaCode CLI itself. The bridge treats GigaCode as a black box: it does not configure or depend on GigaCode's internal tools, shell implementation, editor, or MCP servers.

## Start

For normal delegation, load and follow the installed `$gigacode-executor` skill. This reference is primarily for bridge setup and diagnostics.

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

`start` returns a persistent `session_id`. A confirmed `RUNNING` includes `startup_confirmed=true` only after the bridge has observed real GigaCode model/tool activity internally; the activity itself is not exposed to the parent. A merely alive process reports `STARTING`.

Optional `timeout_sec` (default 0 = unlimited) sets a positive hard wall-clock limit. Use it only for bounded tasks where automatic termination on deadline is safer than indefinite execution.

## Nonblocking status and blocking wait

After confirmed `RUNNING`, normal parent work on the delegated scope stops, but the parent may still do genuinely independent planner/product work.

Use `status` for an immediate nonblocking snapshot:

```text
arguments = {
  "action": "status",
  "session_id": "<session-id>"
}
```

When there is no useful independent work and the current interaction needs the result, prefer one bridge-local wait:

```text
arguments = {
  "action": "wait",
  "session_id": "<session-id>",
  "wait_timeout_sec": 1500
}
```

`wait` polls only inside the MCP bridge, so the parent model is not re-entered for every RUNNING check. A bounded wait timeout returns compact `RUNNING`; it never cancels the detached GigaCode job.

RUNNING responses intentionally expose only compact public runtime state; they do not return GigaCode event history, internal logs, model text, or tool traces.

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

## Acceptance and resume

`DONE` is accepted from the structured handoff by default; it is not a signal for a second full parent code review. The bridge requires GigaCode to report criterion-by-criterion PASS evidence plus final diff/scope self-review before DONE is considered valid.

If the handoff lacks evidence or contradicts the fixed contract, send only the missing proof/decision back into the same executor context:

```text
arguments = {
  "action": "resume",
  "session_id": "<session-id>",
  "prompt": "Handoff lacks evidence for criterion C3. Verify C3, perform final scope review, and return a complete handoff. Do not redesign."
}
```

Keep one session per logical implementation task. While a session is `RUNNING`, do not read/edit/revalidate its scope in the parent. Parent source/artifact inspection after DONE requires a concrete exception from `$gigacode-executor`.

## Runtime safeguards

The bridge launches GigaCode detached, performs a short startup handshake (20s bounded, independent of timeout), and preserves the same GigaCode session for resume. The default hard timeout is 0 (unlimited); callers may set a positive `timeout_sec` to impose an explicit deadline. `wait` is independently bounded to at most 1500 seconds per MCP call; Harr configures LeanCTX downstream calls for 1800 seconds and host-side LeanCTX tool calls for 1900 seconds, leaving transport margin around the wait. No-progress inactivity is tracked as informational status only — the bridge never automatically kills for inactivity.

Cancellation is explicit via `action=cancel`; there is no automatic inactivity or total-deadline cancellation unless the caller requested a positive `timeout_sec`.

Normal planner work must use only the MCP handoff. GigaCode chat/debug/runtime files under `~/.gigacode` and `~/.cache/gigacode-mcp` are bridge diagnostics and should be read only when explicitly debugging a bridge/runtime failure; normal public status does not expose their event contents.