# Codex async notification probe

Reference MCP App used to verify asynchronous completion wake-up behavior in Codex Desktop.

This example is not installed by Harr and is not production runtime code. It exists to preserve the tested protocol and UX mechanics for the future Harr Workspace + Ein completion integration.

## Files

- `server.py` — stdio MCP server, simulated async jobs, app-only wait/claim tools.
- `marker.html` — compact inline marker. It waits for one job, changes RUNNING -> DONE, claims the completion, and calls `ui/message`.
- `workspace.html` — fullscreen Workspace-like monitor for long-lived side-panel lifecycle experiments.
- `smoke.py` — protocol smoke test that does not require Codex Desktop.

## Smoke test

```bash
python3 examples/codex-async-notify-probe/smoke.py
```

Expected result:

```text
async notify probe smoke: PASS
```

The smoke test verifies initialization, tool discovery, marker resource metadata, async completion, and atomic claim/release behavior. It cannot verify `ui/message`, because that requires a real MCP Apps host.

## Register in Codex for manual Desktop testing

From the Harr checkout:

```bash
codex mcp add async-notify-probe -- \
  /usr/bin/python3 \
  "$(pwd)/examples/codex-async-notify-probe/server.py"
```

Restart/reload Codex Desktop if the running app-server does not hot-reload MCP configuration.

Then ask the parent thread to call:

```text
async-notify-probe::start_async_marker_probe
```

with a short delay, for example 10-15 seconds.

### Trusted wake test

Before starting the async worker, give the parent thread a trusted instruction such as:

```text
When the async completion wakes this thread, calculate 2 + 2 and explicitly say that the wake was received.
```

Then start the marker with a neutral completion message such as `trusted-wakeup-test`.

Do not put the task itself into the later `ui/message`. That message is intentionally treated as untrusted input by Codex Desktop. The expected result is that the completion wakes the thread and the model executes the earlier trusted instruction.

## Compact height

The marker resource includes these Codex Desktop metadata fields:

```text
openai/widgetHeightHint = 44
openai/widgetMinFrameHeight = 40
openai/widgetShowCodexWidgetInline = true
```

They are required for the tested Desktop build to allocate the small inline frame before iframe creation. Runtime `ui/notifications/size-changed` remains in the HTML as a secondary hint.

## Cleanup

```bash
codex mcp remove async-notify-probe
```

Runtime probe logs are written below:

```text
$XDG_STATE_HOME/harr-async-notify-probe/events.jsonl
```

or, when `XDG_STATE_HOME` is unset:

```text
~/.local/state/harr-async-notify-probe/events.jsonl
```

For the full experiment notes and architectural conclusions, see `docs/ASYNC_EIN_COMPLETION_MCP_APP_PROBE.md`.
