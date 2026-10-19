# Einherjar generic external worker MCP

Einherjar is Harr's backend-neutral planner→worker bridge. It exposes one downstream tool:

```text
einherjar::worker
```

Actions are `start|resume|status|messages|wait|cancel|backends`.

## Backends

Built-in adapters:

- `gigacode`
- `opencode`
- `codex`

Additional simple CLIs can be declared in `~/.config/harr/einherjar.json` with the `command-template` adapter. Authentication remains owned by each CLI; Harr stores no provider tokens.

Use `action=backends` to see the safe capability view and current default backend.

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

Optional `backend=gigacode|opencode|codex|<configured-name>` overrides the configured default for that new Harr session. The backend is then frozen for resume.

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
