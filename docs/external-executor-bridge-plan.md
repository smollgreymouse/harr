# План: optional External Executor Bridge для Harr

> Статус: design / implementation plan
>
> Цель: дать Codex/Harr единый planner→executor протокол, где executor может
> быть **любой CLI agent/runtime**, умеющий выполнить задачу и желательно
> продолжить ту же сессию. OpenCode — только первый adapter, не архитектурная
> зависимость.

## 1. Идея

Harr разделяет два долгоживущих контекста:

```text
user
  |
  | @builder <задача>
  v
Codex planner/orchestrator                 expensive / reasoning
  |
  | Harr + LeanCTX investigation
  | Detailed Execution Contract
  v
LeanCTX ctx_tools
  |
  v
harr-executor MCP bridge
  |
  +--> Adapter: opencode CLI
  +--> Adapter: gigachat CLI
  +--> Adapter: <other agent CLI>
  +--> Adapter: generic command-template CLI
             |
             v
       persistent executor session          cheap / little or no reasoning
             |
             v
       isolated builder tool environment
             |
             v
            repo
```

При проблеме:

```text
executor session S
   |
   | compact BLOCKED packet
   v
Codex, тот же planner context
   |
   | targeted investigation if needed
   | Planner Resolution Delta
   v
adapter.resume(session S, delta)
   |
   v
тот же executor context
```

Ключевой принцип: **planner/executor protocol не знает, какая модель или CLI
находится с другой стороны adapter-а**.

## 2. Зачем абстрагировать CLI

Executor может быть тупым, но исполнительным. От него не требуется reasoning.
Требуется только:

- принять детальный contract;
- иметь доступ к нужным file/edit/test tools;
- выполнить инструкции последовательно;
- уметь вернуть terminal response;
- желательно уметь resume существующей session.

Поэтому Harr не должен быть привязан к OpenCode, DeepSeek, GigaChat или любому
конкретному provider/model.

Меняться должен только adapter:

```text
                  Harr protocol
                       |
              ExecutorAdapter API
              /        |         \
             /         |          \
      OpenCode     GigaChat     Future CLI
       adapter      adapter       adapter
```

Все следующие части общие для всех backend-ов:

- planner gate;
- Execution Contract;
- builder system contract;
- BLOCKED/DONE protocol;
- workspace guard;
- artifact journal;
- long-poll semantics;
- completion audit;
- token-economy benchmark.

## 3. Не-цели

- Не делать внешний executor обязательным baseline Harr.
- Не выбирать автоматически модель/provider по «умности».
- Не требовать reasoning mode.
- Не позволять executor-у архитектурное replanning.
- Не переносить полный transcript между planner и executor.
- Не строить transport вокруг vendor-specific session format.
- Не требовать session resume от каждого backend: stateless fallback допустим,
  но должен явно показываться как более дорогой capability level.
- Не давать executor-у git push/commit/external writes по умолчанию.

## 4. UX запуска

Канонический semantic marker Harr:

```text
@builder <задача>
```

Дополнительно:

```text
$harr-builder <задача>
```

если host поддерживает skill invocation, и natural-language формы:

```text
сделай через builder
передай реализацию executor-у
используй внешний builder
```

В v1 delegation только explicit.

`@builder` не означает «передать raw user prompt в executor». Codex сначала
выполняет investigation и строит детальный Execution Contract.

## 5. Planner gate

До `executor::start` Codex обязан знать:

1. Goal / observable result.
2. Root cause или осознанное `not-applicable`.
3. Exact affected files / narrow allowed masks.
4. Affected symbols.
5. Call/dependency flow.
6. Implementation order.
7. Per-step exact actions.
8. Invariants / forbidden changes.
9. Exact validation commands/checks.
10. Expected validation results.
11. STOP/BLOCKED conditions.
12. Completion definition.

Если задача всё ещё содержит выбор вроде «реши как лучше», «при необходимости
перестрой архитектуру», «выбери API», planner gate не пройден.

Investigation идёт текущим Harr routing: CodeGraph first, затем targeted
LeanCTX reads/search/shell. Existing Harr token-economy policy сохраняется.

## 6. Executor model: deterministic implementer

Executor system contract:

1. You are an executor, not a planner.
2. Execution Contract is authoritative.
3. Never redesign or replan.
4. Never broaden scope.
5. Execute steps in order unless explicitly allowed otherwise.
6. Do not ask the user questions; return BLOCKED when a decision is missing.
7. Do not launch subagents unless contract explicitly enables them (default: no).
8. Do not use web access (default: no).
9. Do not commit/push/publish.
10. Do not weaken tests to get green output unless exact semantic change is in
    the contract.
11. Never silently skip required validation.
12. If a contract precondition is false, gather minimum evidence and BLOCK.
13. Repair only obvious local syntax/type errors directly caused by the current
    prescribed edit; anything requiring design judgment => BLOCKED.
14. Do not dump full logs/source into terminal response.
15. Final response must satisfy Harr terminal packet protocol.

Prompt discipline is not considered sufficient. Runtime/tool permissions and
workspace guard enforce scope mechanically where the backend supports them.

## 7. Execution Contract v1

Canonical representation stored by Harr, rendered to stable Markdown for the
executor:

```markdown
# HARR EXECUTOR CONTRACT v1

Run: <run-id>
Plan revision: 1
Goal: ...
Success definition: ...

## Allowed scope
- src/foo.cpp
- include/foo.hpp

## New files allowed
- tests/foo_test.cpp

## Forbidden changes
- Do not change ownership model.
- Do not change public defaults.
- Do not add dependencies.
- Do not commit or push.

## Known facts
- ...

## Fixed decisions
- ...

## Global invariants
- ...

## Step B001
Objective: ...
Targets:
- file: ...
- symbol: ...
Preconditions:
- ...
Exact actions:
1. ...
2. ...
Expected result:
- ...
Validation:
- command/check: ...
- expected: ...
STOP if:
- ...

## Step B002
...

## Final validation
1. ...
2. ...

## Reporting
Return only the Harr terminal packet.
```

Шаги намеренно мелкие. Executor не должен делать архитектурный выбор между
шагами.

## 8. Adapter abstraction

Core interface не должен упоминать OpenCode/GigaChat/vendor concepts:

```python
class ExecutorAdapter(Protocol):
    def probe(self) -> ExecutorCapabilities: ...
    def start(self, request: StartRequest) -> StartedSession: ...
    def resume(self, session: SessionHandle, message: str) -> ResumeResult: ...
    def wait(self, session: SessionHandle, after_sequence: int, timeout_s: int) -> AdapterEvent: ...
    def cancel(self, session: SessionHandle) -> None: ...
    def close(self, session: SessionHandle) -> None: ...
```

Adapter отвечает только за:

- CLI invocation / process management;
- создание session;
- resume той же session;
- parsing stdout/stderr/event stream;
- нормализацию vendor events в Harr adapter events;
- cancellation;
- capability probing.

Adapter **не** решает:

- когда задача считается BLOCKED;
- можно ли менять архитектуру;
- какие файлы разрешены;
- что передавать planner-у;
- как устроен Harr terminal packet;
- как planner реагирует на blocker.

Это responsibility core bridge.

## 9. Capability model

Каждый adapter при `probe()` возвращает capabilities:

```json
{
  "persistent_session": true,
  "resume_session": true,
  "structured_events": true,
  "structured_final_output": false,
  "tool_event_visibility": true,
  "cancel": true,
  "custom_system_prompt": true,
  "custom_agent": true,
  "permission_controls": true,
  "project_config_disable": true,
  "working_directory": true
}
```

Core выбирает поведение по capability, а не по имени backend-а.

### Capability tiers

**Tier A — resumable structured executor**

- persistent session;
- resume;
- structured events;
- cancellation;
- custom instructions.

Это preferred target.

**Tier B — resumable text executor**

- persistent session + resume;
- stdout mostly text;
- bridge extracts terminal block and mechanically gathers workspace facts.

Это всё ещё хороший backend.

**Tier C — stateless executor**

- нет resume session.

Допустим как fallback, но при `continue` bridge должен seed новый process/session
из compact recovery bundle. Harr status и run metadata обязаны показать, что
persistent-context saving unavailable.

## 10. Backend registry

Отдельный registry, не смешанный с MCP registry:

```text
common/executor/backends.json
```

Пример semantic model:

```json
{
  "schema": 1,
  "backends": [
    {
      "name": "opencode",
      "adapter": "opencode",
      "command": "opencode",
      "optional": true
    },
    {
      "name": "gigachat",
      "adapter": "gigachat",
      "command": "<configured executable>",
      "optional": true
    }
  ]
}
```

Не хранить provider tokens/API keys в Harr. Auth остаётся собственностью CLI.

User config:

```text
~/.config/harr/executor.json
```

```json
{
  "backend": "opencode",
  "model": "provider/model",
  "adapter_options": {},
  "interactive_wait_secs": 90,
  "protocol_repair_turns": 1
}
```

Commands:

```text
harr executor list
harr executor probe <backend>
harr executor configure
harr executor use <backend>
harr executor status
```

Позже можно поддержать named profiles:

```text
harr executor use fast-cheap
harr executor use local
harr executor use gigachat
```

## 11. Built-in adapters

### 11.1. OpenCode adapter

Первый reference implementation. Он использует CLI/session resume и event
stream, но никакая OpenCode-specific деталь не выходит за adapter package.

```text
common/executor/adapters/opencode.py
```

### 11.2. GigaChat CLI adapter

Отдельный adapter:

```text
common/executor/adapters/gigachat.py
```

Его задача — отобразить фактические команды start/resume и output/event format
конкретной CLI в `ExecutorAdapter` API. Core Harr не должен знать эти детали.

Точные CLI flags/session semantics фиксируются empirical probe/tests перед
реализацией adapter-а.

### 11.3. Generic command-template adapter

Чтобы не писать Python adapter для каждой CLI, добавить declarative adapter:

```text
common/executor/adapters/command_template.py
```

Пример user backend config:

```json
{
  "name": "my-agent",
  "adapter": "command-template",
  "start": ["my-agent", "run", "--json", "{prompt_file}"],
  "resume": ["my-agent", "resume", "{session_id}", "--json", "{prompt_file}"],
  "session_id": {
    "source": "stdout-json",
    "json_path": "$.session_id"
  },
  "events": {
    "mode": "ndjson"
  }
}
```

Command templates всегда argv arrays, никогда shell strings.

Generic adapter покрывает CLI, где нужны только:

- start command;
- optional resume command;
- session-id extraction;
- output mode;
- cancellation через process lifecycle.

Если CLI имеет сложную API semantics, пишется dedicated adapter.

## 12. Adapter conformance tests

Любой adapter должен пройти единый suite:

```text
probe
start
obtain session handle
emit RUNNING/event
resume same session (если capability declared)
cancel
non-zero exit handling
malformed output handling
UTF-8/large-output handling
working-directory behavior
```

Backend не считается supported только потому, что executable найден.

Command-template backend может иметь `verified=false`; Harr показывает это в
status. Built-in adapters после conformance tests — `verified=true` для
конкретного диапазона CLI versions.

## 13. Main MCP surface

Planner видит bridge за LeanCTX `ctx_tools`.

Минимальный tool surface:

```text
executor::start
executor::wait
executor::continue
executor::inspect
executor::cancel
```

### start

Принимает:

- repo_root;
- task_label;
- execution_contract;
- allowed_paths;
- optional executor profile override, только если пользователь явно попросил.

Создаёт Harr run id и adapter session handle.

### wait

Long-poll meaningful state, без streaming builder chatter в Codex.

### continue

Принимает Planner Resolution Delta и вызывает adapter.resume() той же session,
если backend это умеет.

### inspect

Возвращает bounded artifact fragment по opaque reference.

### cancel

Останавливает execution, сохраняет journal, не делает auto-revert.

## 14. Persistent context semantics

Harr run id и vendor session id — разные сущности:

```text
Harr run: bld_123
   |
   +-- backend=opencode
   +-- adapter_session=ses_abc
```

или:

```text
Harr run: bld_456
   |
   +-- backend=gigachat
   +-- adapter_session=<vendor session handle>
```

Codex никогда не оперирует vendor session id напрямую.

Normal path:

```text
start contract revision 1
  -> session S
BLOCKED
planner delta revision 2
  -> resume S
BLOCKED
planner delta revision 3
  -> resume S
DONE
```

При Tier C backend новый process получает recovery bundle, но Harr terminal
protocol остаётся тем же.

## 15. Runtime isolation profiles

Нельзя предполагать, что все CLI имеют одинаковую permission model.
Поэтому ограничения делятся на generic hard guard и optional backend controls.

### Generic hard guard — всегда

- canonical workspace root;
- workspace writer lock;
- baseline HEAD/dirty set;
- allowed-path manifest;
- post-event changed-path validation;
- no automatic reset/revert;
- bounded artifact capture;
- no external-write commands в contract.

### Backend-native controls — если capability есть

- disable project config;
- pure/no-plugins mode;
- deny web;
- deny subagents;
- deny questions;
- edit path allowlist;
- custom system prompt;
- custom tool allowlist.

Если backend не умеет runtime permissions, Harr status показывает degraded
isolation, а workspace guard остаётся последней линией защиты.

## 16. LeanCTX topology

Planner side:

```text
Codex
  -> LeanCTX
       -> CodeGraph
       -> optional executor MCP
       -> other selected Harr MCPs
```

Executor side по возможности:

```text
external CLI agent
  -> dedicated executor LeanCTX profile
       -> CodeGraph
       -> ctx_read/search/glob/shell
```

Executor-side profile **никогда не содержит executor MCP**, чтобы не было
рекурсивного spawning.

Default executor profile также исключает external/write-capable GitLab/Grafana
и другие ненужные services.

Если конкретный CLI не умеет MCP, adapter может использовать другой его native
local-tool route; это backend concern. Core protocol не должен зависеть от MCP.

## 17. Terminal packet

Codex получает typed bounded packet, а не transcript.

Envelope:

```json
{
  "protocol": "harr.executor.v1",
  "run_id": "bld_...",
  "sequence": 7,
  "state": "DONE|BLOCKED|FAILED_EXECUTION|FAILED_PROTOCOL|FAILED_GUARDRAIL|CANCELLED",
  "plan_revision": 2,
  "current_step": "B004",
  "completed_steps": ["B001", "B002", "B003"],
  "backend": "opencode",
  "workspace": {},
  "validation": [],
  "artifacts": []
}
```

### BLOCKED

```json
{
  "blocker": {
    "class": "PLAN_PRECONDITION_FALSE|UNSPECIFIED_DESIGN_DECISION|SCOPE_CONFLICT|BUILD_FAILURE_OUTSIDE_PLAN|TOOL_FAILURE|PERMISSION|OTHER",
    "statement": "one precise sentence",
    "expected": "contract assumption",
    "observed": "actual fact",
    "why_contract_is_insufficient": "short explanation",
    "decision_needed": "one exact planner question",
    "safe_state": {
      "partial_edits": "kept|none|unknown",
      "can_continue_same_session": true,
      "resume_step": "B004"
    },
    "evidence": [
      {
        "kind": "source|diagnostic|test|tool",
        "locator": "...",
        "excerpt": "bounded excerpt",
        "artifact_ref": "artifact:..."
      }
    ]
  }
}
```

### DONE

```json
{
  "completion": {
    "summary": "bounded factual summary",
    "contract_deviations": [],
    "unvalidated_items": []
  }
}
```

DONE запрещён bridge-ом, если required validation missing, changed paths outside
scope, contract deviation exists или steps incomplete.

## 18. Mechanical facts vs model claims

Core bridge не доверяет слабой модели там, где факт можно установить самому.

Mechanical facts:

- changed paths;
- diff stat/ref;
- process exit codes;
- command/test exit codes, если adapter видит tool events;
- scope violations;
- session/process status;
- timestamps/sequences.

Semantic fields от executor:

- concise summary;
- blocker statement;
- expected vs observed;
- decision needed;
- relation to plan step.

При invalid terminal block — один protocol-repair turn в той же session, без
новой работы. Потом FAILED_PROTOCOL.

## 19. Artifact journal

```text
~/.local/state/harr/executor/runs/<run-id>/
  run.json
  execution-contract-r1.md
  resolution-r2.md
  events.ndjson
  artifacts/
    command-...
    model-final-...
    diff-...
```

Terminal packet содержит opaque refs. Полный transcript/log/diff не идёт в
Codex, пока planner явно не вызовет `inspect`.

Это даёт полноту данных без загрязнения дорогого planner context.

## 20. Planner Resolution Delta

Codex отвечает на blocker только typed delta:

```markdown
# HARR PLANNER RESOLUTION v1
Run: bld_...
Resolves sequence: 7
Previous plan revision: 1
New plan revision: 2

## Decision
...

## Contract changes
### Step B004 replacement
...

## New/changed invariants
- ...

## Validation changes
- ...

## Resume
Continue at B004.
All sections not explicitly replaced remain authoritative.
```

Если blocker packet недостаточен, сначала один targeted `executor::inspect`, а
не request полного transcript.

## 21. State machine

```text
CREATED
  -> RUNNING
      -> DONE
      -> BLOCKED
          -> RUNNING
          -> CANCELLED
      -> FAILED_EXECUTION
      -> FAILED_PROTOCOL
      -> FAILED_GUARDRAIL
      -> CANCELLED
```

Rules:

- terminal states immutable;
- sequence strictly increasing;
- continue только из BLOCKED;
- stale blocker resolution rejected;
- one writer run per canonical workspace;
- service/process crash не превращается в DONE;
- adapter capability/state persisted in run journal.

## 22. Timeout / long-poll

Не держать бесконечный MCP request.

`start`, `continue`, `wait` используют bounded long-poll меньше текущего
LeanCTX downstream timeout. При отсутствии meaningful event:

```json
{
  "protocol": "harr.executor.v1",
  "run_id": "bld_...",
  "sequence": 3,
  "state": "RUNNING",
  "current_step": "B006",
  "progress": "no planner action required"
}
```

Не возвращать обычный stream executor logs в Codex.

## 23. Harr structure

```text
common/
  executor/
    bridge.py
    service.py
    protocol.py
    journal.py
    workspace_guard.py
    config.py
    capabilities.py
    backends.json
    adapters/
      base.py
      opencode.py
      gigachat.py
      command_template.py
    prompts/
      executor-system.md
      protocol-repair.md
  skills/
    harr-builder/
      SKILL.md
  mcp/
    registry.json
  policy/
    tool-routing.template.md
```

Tests:

```text
tests/
  test_executor_protocol.py
  test_executor_state_machine.py
  test_executor_journal.py
  test_executor_workspace_guard.py
  test_executor_adapter_contract.py
  test_executor_command_template.py
  test_executor_opencode_adapter.py
  test_executor_gigachat_adapter.py
  test_executor_policy.py
  test_executor_mcp_integration.py
```

## 24. Harr MCP registry

Main `common/mcp/registry.json` получает optional MCP `executor`:

- required=false;
- transport=stdio;
- lifecycle=on-demand;
- Harr-owned runtime;
- no secrets;
- fresh install unchecked.

Это bridge MCP, не список CLI backends. Backends живут в отдельном executor
registry/config.

Codex видит `executor` только через LeanCTX gateway.

## 25. CLI discovery

`harr executor list` показывает:

```text
NAME          FOUND  VERIFIED  SESSION  RESUME  STRUCTURED  ISOLATION
opencode      yes    yes       yes      yes     yes         strong
gigachat      yes    yes/no    yes      yes     ...         ...
my-agent      yes    no        ?        ?       ...         ...
```

Discovery не означает support. После discovery можно выполнить probe и adapter
conformance test.

Никогда не угадывать CLI flags по executable name.

## 26. Token economy

Экономия строится не на магическом «числе tool calls», а на архитектуре:

- persistent Codex context;
- persistent executor context, где backend это умеет;
- LeanCTX compression/routing на обеих сторонах;
- bridge schemas за LeanCTX;
- compact typed terminal packets;
- delta вместо повторной передачи plan;
- raw artifacts out-of-band;
- targeted inspect;
- отсутствие полного transcript handoff.

Добавить benchmark режимы:

A. fresh/manual handoff;
B. persistent executor + raw return;
C. Harr compact persistent protocol;
D. stateless Tier C adapter fallback.

Измерять provider tokens, payload sizes, repeated context, planner turns,
success/blocker quality, scope violations, validation completeness.

Не приравнивать provider token telemetry к subscription usage units Codex.

## 27. Этапы реализации

### Phase 0 — generic protocol first

- `harr.executor.v1` schema/state machine.
- fake adapter.
- journal/workspace guard.
- no real CLI dependency.

### Phase 1 — optional MCP integration

- optional executor registry entry.
- `start/wait/continue/inspect/cancel`.
- routing via LeanCTX.

### Phase 2 — adapter framework

- `ExecutorAdapter` protocol.
- capability probing.
- conformance suite.
- command-template adapter.

### Phase 3 — first real adapter

- OpenCode adapter as reference, если он доступен на dev machine.
- prove start/resume/session/event parsing.
- no OpenCode concepts in core tests.

### Phase 4 — second heterogeneous adapter

- GigaChat CLI adapter (или другой реально доступный CLI).
- специально подтвердить, что core protocol не зависит от OpenCode assumptions.

### Phase 5 — hardened executor runtime

- explicit UX marker/skill.
- execution contract generator rules.
- backend-native permission hardening where supported.
- dedicated executor LeanCTX where supported.
- workspace guard everywhere.

### Phase 6 — evidence/quality

- mechanical command/test ledger.
- artifact refs.
- protocol repair.
- completion audit.

### Phase 7 — benchmark + portability

- A/B/C/D token benchmark.
- Linux acceptance first.
- macOS/Windows only after adapter/process/path acceptance.

## 28. Acceptance

В одной Codex conversation:

```text
@builder реализуй <fixture task>
```

должно происходить:

1. Codex investigates through Harr.
2. Builds detailed contract.
3. Starts configured executor backend.
4. Adapter creates session S if supported.
5. Executor edits/tests.
6. Fixture triggers false precondition.
7. Harr returns compact BLOCKED packet.
8. Codex resolves using its existing context, optionally one targeted inspect.
9. Harr resumes same session S when capability exists.
10. Executor finishes.
11. Workspace guard validates scope.
12. Validation ledger is complete.
13. Codex performs bounded audit.
14. No manual copy/paste.
15. Switching backend config from OpenCode to another resumable CLI requires no
    planner/protocol changes.

## 29. Зафиксированные решения

1. Component optional and explicit-use only in v1.
2. Architecture is **External Executor Bridge**, not OpenCode bridge.
3. Any CLI/model may be backend.
4. Model may have zero reasoning capability.
5. Planner is Codex; executor never replans architecture.
6. Backend differences hidden behind `ExecutorAdapter`.
7. Persistent session preferred but not required.
8. Harr run id independent from vendor session id.
9. Compact typed packets only; raw artifacts out-of-band.
10. Planner sends resolution deltas, not full repeated plans.
11. Mechanical facts gathered by Harr where possible.
12. Workspace guard independent of backend-native permission quality.
13. Main bridge lives behind planner LeanCTX.
14. Executor-side tool route must not expose executor bridge recursively.
15. No automatic commits/pushes/resets.
16. Generic command-template adapter lowers cost of adding simple CLIs.
17. Dedicated adapters are used when session/event semantics are too complex for
    templates.

## 30. Spike questions

До production implementation для каждого candidate CLI проверить:

- exact version discovery;
- noninteractive invocation;
- stdin/file prompt transport;
- session creation and session-id extraction;
- resume semantics;
- structured/NDJSON events or only text output;
- cancellation behavior;
- working-directory control;
- project/global config loading and how to disable it;
- tool/permission controls;
- MCP support, если нужен executor-side LeanCTX;
- compaction/context behavior;
- exit/error conventions.

Ни один из этих пунктов не должен менять Harr core protocol. Если конкретный CLI
не поддерживает функцию, меняется его capability set и adapter behavior.
