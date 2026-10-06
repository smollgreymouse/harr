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
  "prompt": "Implement the already-decided change ...",
  "timeout_sec": 900
}
```

`start` returns a persistent `session_id`. A confirmed `RUNNING` includes `startup_confirmed=true` plus the first real GigaCode model/tool activity; a merely alive process reports `STARTING`.

## Status without polling

Do not poll in the same parent turn. On a later continuation, check once:

```text
arguments = {
  "action": "status",
  "session_id": "<session-id>"
}
```

A final handoff is `DONE`, `FAILED` or `ESCALATE`. `ESCALATE` is designed to contain enough exact code evidence for the planner to decide without rereading files merely to rediscover the mismatch.

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

The bridge launches GigaCode detached, performs a short startup handshake, preserves the same GigaCode session for resume, uses a 5-minute no-progress watchdog, and defaults each start/resume turn to a 900-second wall-clock limit (configurable up to 1500 seconds).

Normal planner work must use only the MCP handoff. GigaCode chat/debug/runtime files under `~/.gigacode` and `~/.cache/gigacode-mcp` are bridge diagnostics and should be read only when explicitly debugging a bridge/runtime failure.
