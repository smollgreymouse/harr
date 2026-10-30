# Codex Desktop async completion MCP App probe

This standalone example captures the verified async-completion pattern used to wake a parent Codex Desktop thread without polling from the model.

It is intentionally kept outside Harr runtime code. The probe exists as a reference implementation for the eventual Harr Workspace + async notification integration.

## What the experiment proved

On 2026-10-30, the probe was exercised in Codex Desktop with this sequence:

1. A parent turn started a simulated async worker.
2. The tool returned immediately.
3. The inline MCP App marker remained in the transcript.
4. The server-side timer completed later, independently of the model.
5. The marker long-polled the app-only MCP tool, atomically claimed the completion, and called `ui/message`.
6. Codex Desktop woke the parent thread without model-side polling.
7. The model continued an instruction that had been given earlier in trusted parent context.

The decisive wake test used a pre-existing trusted instruction equivalent to:

> When the async completion arrives, calculate 2 + 2 and explicitly say that the wake was received.

The later `ui/message` carried only completion status. The model then produced the expected answer, proving that the notification woke the thread and that continuation could consume the already trusted parent task.

This distinction matters: MCP App `ui/message` content is surfaced as untrusted input. It is suitable for a completion/wake signal and status payload, but it must not be used as a trusted instruction channel.

## Experiments that failed before the final shape

The successful shape was selected after several negative tests:

- A fullscreen/side-panel MCP App could observe the server-side completion, claim it and call `ui/message`, and the rollout contained the completion payload, but that path did not reliably produce the visible automatic parent continuation we wanted.
- Putting a new task such as “calculate 2 + 2” inside the completion `ui/message` did wake the model, but Codex correctly treated that embedded request as untrusted and refused to execute it as an instruction.
- Moving the wake surface to a transcript-attached inline MCP App made the wake visible and reliable in the tested Desktop build.
- Keeping the task in trusted parent context and using the later `ui/message` only as a neutral completion signal produced the desired automatic continuation.

Therefore the side panel is useful as a persistent Workspace/job monitor, but it must not be the only completion-delivery mechanism. If Desktop suspends or hides that panel, the worker still belongs to Harr and the transcript marker remains the wake surface for the run.

## Architecture demonstrated

```text
parent Codex thread
    |
    +-- trusted task/instructions already present
    |
    +-- MCP tool starts async work and returns
            |
            +-- server-side job / real Ein adapter
                    |
                    +-- completion event
                            |
                            +-- compact inline MCP App marker
                                    |
                                    +-- app-only wait
                                    +-- atomic claim
                                    +-- ui/message wake
                                            |
                                            +-- parent thread resumes trusted task
```

A separate Workspace-like fullscreen MCP App is included to exercise the future long-lived side-panel surface. It monitors jobs but does not own the wake. The compact inline marker owns the final wake because the transcript-attached surface was empirically reliable for `ui/message` delivery.

The intended Harr architecture is therefore:

```text
Harr Workspace side panel
    +-- workspace/multiroot UI
    +-- async job monitor

per async run
    +-- compact transcript marker
            +-- RUNNING -> DONE
            +-- completion claim
            +-- ui/message wake
```

The worker engine and UI are deliberately separated. A real Ein adapter should publish a generic completion event; the UI should not be the process supervisor.

## Side-panel opening policy

The Workspace side panel is strictly opt-in UI:

- starting an async worker must not open, focus or expand the side panel;
- worker completion must not open, focus or expand the side panel;
- if the side panel is already open, it may update silently in place;
- the side panel opens only after an explicit user/model request to show the Workspace panel;
- the async wake path must continue to work with the side panel never opened at all.

The verified reference implementation follows this rule: `start_async_marker_probe` exposes only the inline marker resource, and neither its start path nor its completion path invokes `show_async_workspace_probe`, fullscreen mode or `ui/request-display-mode`.

## Compact marker sizing

Codex Desktop supports runtime `ui/notifications/size-changed`, but on the tested build that notification did not shrink the already-large inline host allocation reliably.

The working fix was to provide Codex-specific resource metadata in `resources/read`:

```json
{
  "openai/widgetHeightHint": 44,
  "openai/widgetMinFrameHeight": 40,
  "openai/widgetPrefersBorder": false,
  "openai/widgetShowCodexWidgetInline": true
}
```

These values are read before the iframe is created, so the host allocates a compact frame from the start. The marker still emits `ui/notifications/size-changed` as a secondary hint.

## Reliability boundary

What is verified:

- server-side completion can occur after the launching tool returned;
- the inline marker can observe completion through app-only MCP tools;
- a completion can be claimed once to avoid duplicate delivery from multiple UI instances;
- `ui/message` wakes the parent Codex Desktop thread;
- the resumed model can continue a trusted task that predates the notification;
- a fixed resource height hint keeps the inline marker compact.

What is not yet a production guarantee:

- durability across Desktop restart;
- durable event persistence;
- delivery after the transcript marker is explicitly destroyed;
- exact behavior across future Codex Desktop MCP Apps changes;
- replacement of the timer with the real Ein engine lifecycle.

For production Harr integration, persist or reconstruct pending completions independently of the iframe and treat UI lifetime as a delivery surface, not as ownership of the worker.

## Example

See `examples/codex-async-notify-probe/`.

The example contains:

- `server.py` — stdio MCP server with simulated async jobs;
- `marker.html` — compact transcript marker and wake path;
- `workspace.html` — Workspace-like side-panel monitor;
- `smoke.py` — host-independent protocol smoke test.

The example is intentionally dependency-free and uses only the Python standard library.
