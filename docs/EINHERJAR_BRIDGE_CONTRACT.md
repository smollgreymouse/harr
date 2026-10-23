# Einherjar Bridge Contract

> Status: reference contract for Harr external CLI-agent adapters
>
> Scope: defines the stable boundary between the Harr Einherjar worker core and
> vendor-specific command-line agent adapters. New CLI agents should be wrapped
> against this contract without changing planner-facing MCP semantics.

## 1. Purpose

Einherjar is Harr's generic worker bridge for delegating an already-decided
implementation or verification task to an external console agent.

The planner-facing protocol is intentionally independent from any particular
agent CLI. GigaCode, OpenCode, Codex CLI, future local agents, and user-defined
command-template agents are all backends behind the same Harr worker contract.

The architecture is:

```text
planner
  |
  | einherjar::worker
  v
Einherjar core
  |
  | BackendAdapter contract
  +--> GigaCode adapter
  +--> OpenCode adapter
  +--> Codex CLI adapter
  +--> command-template adapter
  +--> future adapter
```

The planner must never need to know vendor session ids, vendor event schemas,
CLI flags, transcript locations, or process-management details.

## 2. Responsibility boundary

### Einherjar core owns

- Harr session id and job id generation.
- Persistent Harr session state.
- Detached job lifecycle.
- start/resume/status/messages/wait/cancel semantics.
- timeout and cancellation policy.
- workspace root.
- worker system contract.
- final Harr handoff validation.
- conversion of backend failures into backend-neutral Harr failures.
- selection of a configured backend.
- persistence of the selected backend and vendor session handle.
- public MCP schemas.

### Backend adapter owns

- executable discovery and capability probe.
- start argv/stdin/file construction.
- resume argv/stdin/file construction.
- vendor session-id extraction.
- vendor event/transcript parsing.
- normalization of assistant progress text.
- backend-specific process environment requirements.
- backend-specific diagnostics safe to expose.
- identifying whether resume is supported.

### Backend adapter must NOT own

- planner policy.
- architecture decisions.
- scope expansion.
- Harr session ids.
- public MCP action names.
- Harr terminal handoff semantics.
- automatic commit/push/publish behavior.
- user/provider credentials.

## 3. Identity model

Harr session identity and vendor session identity are separate.

```text
Harr session
  session_id = <Harr UUID>
  backend = "opencode"
  vendor_session_id = <opaque backend value>
```

Rules:

1. Public `resume/status/messages/wait/cancel` use only the Harr session id.
2. The selected backend is frozen when the Harr session starts.
3. The vendor session id is opaque to core and callers.
4. A backend adapter may return no vendor session id only if it declares itself
   stateless/non-resumable.
5. Resume must never silently switch backend.

## 4. Required adapter API

The exact Python shape may evolve, but every adapter must expose equivalent
semantics:

```python
class BackendAdapter(Protocol):
    def name(self) -> str: ...
    def probe(self) -> BackendCapabilities: ...

    # Return argv only; core owns Popen/cwd/process groups/timeouts/cancel.
    def start_command(self, request: BackendStartRequest) -> list[str]: ...
    def resume_command(self, request: BackendResumeRequest) -> list[str]: ...

    # Default preparation prepends the Harr WORKER_CONTRACT. An adapter may
    # override this only when it has a native system-prompt route (GigaCode).
    def prepare_prompt(self, prompt: str) -> str: ...
    def stdin_text(self, prompt: str) -> str | None: ...

    def initial_vendor_session_id(self, request: BackendStartRequest) -> str | None: ...
    def extract_vendor_session_id(self, stdout: str, stderr: str) -> str | None: ...
    def final_output(self, stdout: str, stderr: str) -> str: ...
    def progress_messages(self, stdout: str) -> list[str]: ...
    def cleanup(self) -> None: ...
```

This is the current contract. Additions should remain backend-neutral; vendor
flags, event names, and transcript layouts belong inside the adapter.

## 5. Capability model

Every adapter reports capabilities. Core behavior must branch on capabilities,
not backend names.

Minimum fields:

```json
{
  "resumable": true,
  "structured_events": true,
  "progress_messages": true,
  "prompt_stdin": false,
  "prompt_file": false,
  "cancel": true,
  "working_directory": true
}
```

Recommended future extensions:

- custom_system_prompt
- permission_controls
- project_config_disable
- tool_allowlist
- sandbox_controls
- structured_final_output
- persistent_session
- model_selection

Do not add planner-visible vendor-specific booleans.

## 6. Start contract

Core provides:

- workspace path;
- worker prompt;
- Harr session id;
- timeout;
- worker contract text;
- backend options already validated.

Adapter returns a launch description. Prefer data over side effects.

Conceptually:

```json
{
  "argv": ["agent", "run", "..."],
  "stdin": "optional prompt",
  "env": {},
  "vendor_session_id_hint": null,
  "structured_output": true
}
```

Requirements:

- argv must be an argument vector.
- never use a shell command string.
- never use `shell=True`.
- cwd must be the Harr workspace unless the backend cannot support it.
- auth remains owned by the external CLI.
- secrets must not be copied into Harr config or logs.
- dangerous bypass flags must not be enabled merely for convenience.

## 7. Resume contract

If `resumable=true`, the adapter must be able to continue the same vendor
session given:

- opaque vendor session id;
- planner delta prompt;
- workspace;
- timeout/backend options.

Resume must preserve the existing agent context where the backend supports it.

If `resumable=false`, core must not pretend otherwise. A later stateless
recovery mode may start a new process from a compact recovery bundle, but it is
a separate capability and must be reported explicitly.

## 8. Prompt transport

Allowed mechanisms:

1. argv placeholder;
2. stdin;
3. Harr-created temporary prompt file.

Adapters must not require shell interpolation.

Temporary prompt files:

- must live in Harr-owned runtime/cache state, not arbitrary workspace paths;
- must be removed when no longer required;
- must not contain provider credentials.

## 9. Command-template adapter

The declarative adapter exists for simple CLIs that do not need custom Python
logic.

Example:

```json
{
  "adapter": "command-template",
  "start": ["my-agent", "run", "--prompt-file", "{prompt_file}"],
  "resume": ["my-agent", "resume", "{session_id}", "--prompt-file", "{prompt_file}"],
  "session_id": {
    "source": "stdout-json",
    "keys": ["session_id", "sessionId"]
  },
  "events": {
    "mode": "jsonl"
  }
}
```

Supported placeholders must be explicitly documented and validated. At minimum:

- `{prompt}`
- `{prompt_file}`
- `{session_id}` — on start this may be a Harr-assigned vendor id for CLIs that accept caller-selected session ids; on resume it is the persisted opaque vendor id.
- `{workspace}`

Rules:

- command values are arrays only;
- unknown placeholders are rejected;
- shell metacharacters have no special meaning;
- resume is optional;
- absence of resume means the backend is non-resumable;
- recursive invocation of Einherjar itself must be rejected where detectable.

If a CLI needs complex session discovery, event parsing, auth handshakes, or
non-trivial state management, write a dedicated adapter instead.

## 10. Observation and progress normalization

Core may expose bounded progress via `messages` and app UI.

Adapters normalize vendor output to a small common shape:

```json
{
  "kind": "assistant",
  "text": "bounded assistant progress text",
  "timestamp": "...",
  "sequence": 17
}
```

Rules:

- tool-call payloads are not planner progress text.
- raw debug logs are not planner progress text.
- reasoning/internal chain-of-thought must not be surfaced.
- duplicate messages must be suppressible by sequence/revision.
- malformed vendor events are ignored or converted to diagnostics; they must not
  crash the bridge.
- backends without structured progress may legitimately return no messages.

## 11. Vendor session discovery

Preferred order:

1. explicit CLI-provided session id in structured output;
2. documented session id event;
3. documented backend state file/transcript lookup;
4. no session id -> backend is treated as non-resumable.

Do not scrape unstable human-formatted terminal banners if a structured route
exists.

Vendor session ids are opaque strings. Core should not impose UUID format on
them unless the vendor contract explicitly guarantees UUIDs.

## 12. Final output contract

The backend's final model response must contain the Harr worker handoff.

Current handoff statuses:

- `DONE`
- `ESCALATE`
- `FAILED`

Core validates the packet. Adapter only obtains the backend's final response.

A backend-specific parser may strip transport wrappers, but must not invent
missing semantic fields or reinterpret a failed task as DONE.

## 13. Backend-neutral failure mapping

Generic core error text must not say "GigaCode failed" when another backend is
active.

Examples:

```text
External worker exited with code 2.
Backend executable not found: opencode.
Backend did not return a parseable Harr handoff.
Selected backend does not support resume.
```

Backend-specific diagnostic details may be attached in bounded evidence.

## 14. Process lifecycle

Einherjar core owns process lifecycle unless an adapter explicitly uses a
different documented transport.

Required behavior:

- detached worker survives the individual MCP tool call;
- process tree can be terminated on explicit cancel;
- positive hard timeout can terminate the process;
- timeout=0 means no automatic hard timeout;
- owner-loss behavior follows Harr bridge policy;
- no arbitrary PID supplied by the model/user may be killed.

Adapters must not spawn uncontrolled background grandchildren that bypass core
cancellation.

## 15. Configuration contract

Default config:

```text
~/.config/harr/einherjar.json
```

Respect XDG/Harr config overrides where supported.

Example:

```json
{
  "schema": 1,
  "default_backend": "gigacode",
  "backends": {
    "my-agent": {
      "adapter": "command-template",
      "start": ["my-agent", "run", "{prompt}"]
    }
  }
}
```

Configuration must never contain provider API keys or login tokens.

Backend names should be stable identifiers suitable for persistence in Harr
session state.

## 16. Backend probe contract

`backends`/probe output is informational and secret-free.

Expose only data such as:

```json
{
  "name": "codex",
  "source": "builtin",
  "found": true,
  "resumable": true,
  "structured_events": true,
  "progress_messages": true,
  "diagnostic": "codex executable found"
}
```

Do not expose:

- access tokens;
- config contents;
- environment secrets;
- full home-directory paths unless needed for a safe diagnostic.

Executable discovery alone does not prove full backend compatibility.

## 17. Conformance test suite

Every new backend adapter must pass deterministic tests without consuming real
model tokens.

Required tests:

1. probe reports absent/present executable safely;
2. start command construction;
3. prompt transport;
4. workspace/cwd behavior;
5. vendor session-id extraction;
6. resume command construction when declared resumable;
7. malformed structured output;
8. non-zero process exit;
9. UTF-8 output;
10. bounded large output;
11. cancel semantics;
12. final handoff extraction;
13. secret-free diagnostics.

For a resumable fake backend, integration must prove:

```text
start
 -> Harr session A
 -> vendor session V
resume Harr session A
 -> same vendor session V
```

## 18. Implementation validation baseline

The built-in command shapes in the first Einherjar implementation were checked
against these locally installed CLI versions:

- GigaCode 26.7.33
- OpenCode 1.18.33
- Codex CLI 0.162.1

These are a validation baseline, **not version pins**. Runtime discovery remains
capability-oriented; if a future CLI changes its invocation or event contract,
update and re-run the adapter conformance tests rather than adding version
branches to Einherjar core.

## 18. Adding a new dedicated adapter

Checklist:

1. Read this contract.
2. Record the exact CLI version used during development.
3. Inspect `--help` for noninteractive start/resume behavior.
4. Prefer structured JSON/JSONL output.
5. Identify stable session-id semantics.
6. Implement the current `BackendAdapter` methods: `probe`, `start_command`, `resume_command`, session-id/final-output parsing, progress normalization, and cleanup.
7. Declare capabilities truthfully.
8. Add deterministic adapter tests.
9. Add a fake-fixture integration test when possible.
10. Do not modify public MCP semantics.
11. Do not add provider keys to Harr.
12. Document backend-specific limitations.
13. Run the common adapter conformance suite.
14. Verify an unavailable CLI fails cleanly.
15. Only then advertise the backend as supported.

## 19. When core changes are allowed

A new adapter should normally require no Einherjar core changes.

Core changes are justified only when the new CLI demonstrates a genuinely
backend-independent capability missing from this contract.

Bad reason for a core change:

- "CLI X calls sessions conversations."
- "CLI Y names its flag --thread."
- "CLI Z stores JSON under another key."

Those belong in the adapter.

Potentially valid reason:

- a new generic transport category needed by multiple backends;
- a new capability that changes Harr lifecycle semantics;
- a security invariant that must be enforced centrally.

## 20. Backward compatibility

The legacy Harr `gigacode` MCP may coexist with Einherjar.

During migration:

- existing `gigacode::gigacode` behavior remains valid;
- the Einherjar GigaCode backend should reuse the same semantics;
- no existing install is auto-switched to Einherjar;
- backend abstraction must not weaken GigaCode cancellation, startup
  confirmation, handoff validation, or progress behavior.

## 21. Security invariants

Every adapter must preserve these invariants:

- no shell-string execution;
- no implicit external writes;
- no automatic commit/push/publish;
- no secrets in Harr config/logs;
- no arbitrary PID kill;
- no recursive Einherjar spawning;
- no silent backend switch on resume;
- no claim of resume support without same-session proof;
- no weakening sandbox/approval controls merely to make an adapter easier.

## 22. Definition of a supported backend

A CLI is "supported by Einherjar" only when:

- its invocation semantics are documented;
- adapter capability claims are tested;
- start works deterministically in fixture/conformance tests;
- resume is tested if declared;
- cancellation/failure paths are bounded;
- final Harr handoff extraction is tested;
- its adapter does not leak vendor concepts into the planner-facing protocol.

Finding an executable in PATH is discovery, not support.
