# Einherjar generic external worker MCP

Einherjar is Harr's backend-neutral planner→worker bridge. Each named MCP instance exposes one common tool:

```text
<user-chosen-mcp-name>::ein
```

Actions are `start|resume|status|messages|wait|cancel` for every named instance. Configure them using `harr ein add` and `harr ein list`.

The deprecated PR #39 singleton API `einherjar::worker` was a transitional endpoint; the named API is `<mcp-name>::ein`.

## Backends

Built-in adapters:

- `gigacode`
- `opencode`
- `codex`

Additional simple CLIs can be declared per instance using `harr ein add --adapter custom --definition-file PATH`, stored under `~/.config/harr/einherjar/instances.json`. Authentication remains owned by each CLI; Harr stores no provider tokens.

The adapter is bound to the MCP instance in Harr setup, not selected by a model invocation.

## Start

Prefer a plan file:

```text
arguments = {
  "action": "start",
  "plan_path": "IMPLEMENTATION_PLAN.md"
}
```

Or a small direct task:

```text
arguments = {
  "action": "start",
  "prompt": "Implement the already-decided change ..."
}
```

No `backend` parameter is accepted. Each named MCP instance always uses its configured adapter.

## Resume

```text
arguments = {
  "action": "resume",
  "session_id": "<Harr Einherjar UUID>",
  "prompt": "Planner delta / missing evidence request ..."
}
```

The planner never handles vendor session ids.

## Supervision

`status` is nonblocking. `wait` is bounded and polls only inside the bridge. `messages` exposes only normalized assistant progress where the backend supports structured events. Raw CLI transcripts remain outside planner context.

## Adding another CLI

Follow `docs/EINHERJAR_BRIDGE_CONTRACT.md`. A new dedicated adapter should normally require no change to the public MCP protocol.
