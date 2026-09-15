# План: optional OpenCode Builder Bridge для Harr

> Статус: design / implementation plan
>
> Цель первого релиза: Linux-first, transport через OpenCode CLI/session API,
> без автоматического включения. Компонент должен быть **optional** в Harr и
> включаться пользователем явно.

## 1. Цель

Добавить в Harr опциональный builder bridge, который позволяет использовать
дорогой/сильный Codex-контекст как planner/orchestrator, а отдельную дешёвую и
вплоть до практически неризонящей модели за OpenCode — как строго ограниченный
executor.

Основной сценарий:

```text
user
  |
  | @builder <задача>
  v
Codex planner/orchestrator
  |
  | Harr + LeanCTX: исследование репозитория
  | подробный Execution Contract
  v
LeanCTX ctx_tools
  |
  v
harr-builder MCP bridge
  |
  | OpenCode session #S (persistent)
  v
cheap/non-reasoning builder model
  |
  | isolated builder-side LeanCTX
  v
repo + CodeGraph + bounded shell/edit
```

При blocker обратный путь должен быть автоматическим:

```text
OpenCode session #S
  |
  | compact BLOCKED packet
  v
Codex (тот же planner context)
  |
  | resolution delta / plan revision
  v
OpenCode session #S (та же сессия, тот же накопленный builder context)
```

Главная ценность архитектуры — **два долгоживущих контекста вместо постоянных
полных handoff**:

1. Codex сохраняет исследование, архитектурные решения и историю planner-а.
2. OpenCode сохраняет Execution Contract, уже прочитанный код, сделанные edits,
   diagnostics и test history builder-а.
3. Между ними передаются только специально ограниченные сообщения:
   initial execution contract, blocker/terminal packets и planner resolution
   deltas.
4. Полный OpenCode transcript никогда не вставляется в Codex по умолчанию.
5. Полный Codex transcript никогда не вставляется в OpenCode.

Это дополняет существующую Harr token-economy архитектуру: оба агента получают
репозиторный контекст через LeanCTX, а специализированный bridge сам остаётся за
`ctx_tools`, поэтому его tool schemas не должны становиться новым постоянным
контекстом host-моделей.

## 2. Важное ограничение модели стоимости

Не строить дизайн на предположении «один Codex tool call = фиксированная единица
лимита». Реальный расход Codex зависит от модели, размера/сложности контекста,
reasoning, tool use и длительности работы.

Следовательно, оптимизируем одновременно:

- объём данных, возвращаемых из builder-а planner-у;
- число бессмысленных polling turns;
- повторную передачу уже известного контекста;
- постоянные tool schemas;
- повторное чтение source/log data;
- количество случаев, когда Codex вынужден заново исследовать то, что уже
  достаточно точно локализовал builder.

Не оптимизировать ценой потери recoverability: полные raw events и большие
артефакты сохраняются out-of-band и доступны planner-у по opaque reference.

## 3. Не-цели первого релиза

- Не делать builder bridge обязательной частью Harr baseline.
- Не запускать builder автоматически для каждой implementation-задачи.
- Не позволять builder-у самостоятельно менять архитектуру или replanning.
- Не делать multi-builder swarm.
- Не давать builder-у subagents.
- Не давать builder-у web search/web fetch.
- Не давать builder-у Git commit/push или внешние API writes по умолчанию.
- Не проксировать весь OpenCode transcript в Codex.
- Не проксировать весь Codex conversation в OpenCode.
- Не требовать DeepSeek: модель OpenCode может быть любой, включая дешёвую
  модель без reasoning mode.
- Не требовать от модели надёжного самостоятельного summarization для
  механических фактов, которые bridge может собрать сам.

## 4. Основной принцип: planner решает, builder исполняет

Builder должен считаться **неризонящим executor-ом**. Его нельзя проектировать
как «второго умного агента».

Codex перед делегированием обязан снять всю существенную неопределённость.
Builder не должен выбирать между архитектурными вариантами, угадывать ownership,
менять публичный API «как лучше», расширять scope, выбирать новый алгоритм или
переписывать тестовую семантику.

Разрешённая builder-у свобода должна быть только механической:

- точное позиционирование изменения внутри уже указанного symbol/file;
- локальные имена временных переменных, если они не являются API;
- formatting;
- очевидное исправление syntax/type mismatch, напрямую вызванного текущим
  предписанным edit и не требующего нового design decision;
- повтор predeclared validation command после такого локального исправления.

Во всех остальных случаях builder обязан остановиться и вернуть `BLOCKED`.

## 5. Явный UX запуска

### 5.1. Канонический marker

В Harr policy/skill ввести пользовательскую конвенцию:

```text
@builder <задача>
```

Пример:

```text
@builder добавь поле timeout в WorkerConfig и протяни его до WorkerPool,
не меняя текущую семантику default timeout
```

`@builder` — не нативный parser feature Codex. Это **явный Harr semantic marker**,
который generated Codex policy обязан трактовать как запрос на builder bridge.

Критично: Codex **не передаёт raw текст после `@builder` прямо в OpenCode**.
Сначала он исследует задачу через Harr/LeanCTX, устраняет неопределённости,
формирует Execution Contract и только потом вызывает bridge.

### 5.2. Native skill alias

Дополнительно поставить optional skill `harr-builder`, чтобы там, где Codex
поддерживает явное skill invocation, можно было писать:

```text
$harr-builder <задача>
```

Обе формы должны вести в один workflow.

### 5.3. Natural-language explicit invocation

Также считать явным разрешением фразы вроде:

```text
сделай это через builder
используй Harr builder для реализации
передай реализацию builder-у
```

### 5.4. Запрет implicit delegation в v1

Без одного из явных сигналов Codex не вызывает builder bridge сам.
Это позволяет включить компонент в Harr, не превращая его в default behavior.

## 6. Planner gate перед `builder_start`

Codex не имеет права запускать builder, пока не знает следующее.

### Обязательные gate

1. **Goal** — точный observable result.
2. **Root cause / change reason** — для bugfix; для чисто механической feature
   допустимо `not-applicable`, но это должно быть осознанно.
3. **Affected files** — точный allowlist или осознанно узкие glob masks.
4. **Affected symbols** — существующие symbols и новые symbols, если нужны.
5. **Dependencies / call flow** — где изменение начинается и куда протягивается.
6. **Implementation sequence** — порядок edits, учитывающий зависимости.
7. **Per-step recipe** — что именно builder должен сделать на каждом шаге.
8. **Invariants** — что нельзя менять.
9. **Validation** — точные commands/checks и ожидаемые outcomes.
10. **STOP conditions** — какие наблюдения означают, что план неверен или
    недостаточен.
11. **Scope policy** — что builder вправе менять и что обязан оставить в покое.
12. **Completion definition** — когда можно вернуть DONE.

Если хотя бы один существенный gate неизвестен, Codex продолжает investigation
через существующий Harr routing (`CodeGraph -> targeted LeanCTX`) и не
делегирует задачу.

## 7. Execution Contract v1

Initial message в OpenCode должен быть не свободным prose-планом, а жёстким
контрактом. Bridge хранит canonical structured representation, а модели отдаёт
стабильный Markdown rendering, потому что слабые модели обычно лучше следуют
простому линейному тексту, чем глубоко вложенному JSON.

Предлагаемый формат:

```markdown
# HARR BUILDER EXECUTION CONTRACT v1

Run: <run-id>
Plan revision: 1
Goal: ...
Success definition: ...

## Allowed scope
Files/patterns:
- src/foo.cpp
- include/foo.hpp

New files allowed:
- tests/foo_timeout_test.cpp

## Forbidden changes
- Do not change Worker ownership.
- Do not change public defaults.
- Do not add dependencies.
- Do not commit or push.

## Known facts
- WorkerPool owns ...
- timeout currently comes from ...

## Fixed decisions
- New field type is std::chrono::milliseconds.
- Default is 5s.
- Existing constructor remains source compatible.

## Global invariants
- ...

## Step B001
Objective: ...
Targets:
- file: include/foo.hpp
- symbol: WorkerConfig
Preconditions:
- field X exists
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
Return only the HARR terminal packet requested by the builder protocol.
```

### Требование к granularity

Шаг должен быть достаточно маленьким, чтобы слабая модель могла выполнить его
без выбора architecture. Если в одном step есть формулировка «реши как лучше»,
«при необходимости переработай», «выбери подходящую структуру» или аналогичная
неопределённость, planner gate считается проваленным.

## 8. Builder system contract

OpenCode custom agent `harr-builder` получает жёсткий system prompt примерно с
такими правилами:

1. You are an executor, not a planner.
2. The Execution Contract is authoritative.
3. Never redesign, replan, broaden scope, add architecture, or reinterpret the
   goal.
4. Execute steps in order unless the contract explicitly allows reordering.
5. Use only the tools and filesystem paths permitted by the runtime policy.
6. Do not ask the user questions. If a decision is missing, return BLOCKED.
7. Do not launch subagents.
8. Do not use web tools.
9. Do not commit/push/publish.
10. Do not weaken/remove tests merely to make validation pass unless the plan
    explicitly commands that exact semantic change.
11. Do not silently skip a validation step.
12. When a plan precondition is false, gather the smallest sufficient evidence
    and return BLOCKED immediately.
13. When a failure is an obvious local syntax/type error created by the current
    prescribed edit, it may be repaired inside the same step; otherwise return
    BLOCKED.
14. Never dump large source/log output into the final report; return references
    and bounded excerpts.
15. Final output must be one protocol packet, not free-form narrative.

## 9. Builder-side isolation

Нельзя полагаться только на prompt discipline, особенно если модель очень
слабая. Ограничения должны быть физически выражены в OpenCode permissions и
launch environment.

### 9.1. Project instruction isolation

Builder launch устанавливает:

```text
OPENCODE_DISABLE_PROJECT_CONFIG=1
```

чтобы случайные project-level OpenCode instructions/agents не переопределяли
executor semantics. Нужные project constraints обязан перенести в Execution
Contract Codex planner.

Global Harr policy остаётся допустимым, но builder-specific agent/system rules
имеют более узкое назначение.

### 9.2. Plugins and autonomous extensions

Запускать OpenCode с `--pure` и отключить всё, что builder-у не требуется.
Не давать external plugins возможности расширять tool surface.

### 9.3. Permissions

Dynamic OpenCode config для конкретного run должен:

- `edit`: deny `*`, затем allow только contract `allowed_files` и
  `new_files_allowed`/явные masks;
- native `read`/`grep`/`glob`/`shell`: deny; репозиторное исследование и shell
  идут через builder LeanCTX;
- `subagent`: deny `*`;
- `question`: deny `*`;
- `webfetch`/`websearch`: deny `*`;
- skills: deny, кроме будущих явно разрешённых builder-only skills;
- external directories: deny;
- разрешить только builder-side LeanCTX MCP tools;
- любые write-capable external MCPs отсутствуют из builder catalog.

Конкретные OpenCode permission action names нужно probe/зафиксировать тестом для
поддерживаемой версии, а не угадывать строковые ids.

### 9.4. Workspace guard

Bridge перед start фиксирует baseline:

- canonical repo root;
- current HEAD, если это Git repo;
- pre-existing dirty paths;
- hashes/stat для in-scope files при необходимости;
- allowed path set.

Bridge **никогда не reset/revert пользовательские pre-existing changes**.
После каждого terminal event он механически проверяет, что builder не изменил
path вне allowlist. Scope violation превращается в `FAILED_GUARDRAIL`, даже если
модель сказала DONE.

В v1 разрешать только один active builder run на один canonical workspace root.

## 10. Отдельный builder-side LeanCTX profile

Builder не должен подключаться к полному user-facing Harr gateway, иначе он
может увидеть `harr-builder` и потенциально рекурсивно вызвать самого себя.

На каждый run bridge создаёт/использует отдельный LeanCTX config profile или
config dir:

```text
~/.local/state/harr/builder/runs/<run-id>/leanctx/config.toml
```

Environment:

```text
LEAN_CTX_CONFIG_DIR=<run-specific-or-builder-profile-dir>
LEAN_CTX_PROJECT_ROOT=<repo-root>
```

Builder profile наследует текущие Harr token-economy настройки:

- stable small core surface;
- compression;
- content-defined chunking;
- archive;
- terse output;
- cache behavior where безопасно;

но downstream gateway в v1 содержит только то, что нужно local code builder-у:

```text
builder OpenCode
  -> builder LeanCTX
       -> CodeGraph
       -> core ctx_read/search/glob/shell
```

`harr-builder`, GitLab, Grafana и другие external/write-capable services в этот
catalog не попадают.

Позже можно добавить per-run explicit downstream allowlist, но default должен
быть CodeGraph-only.

## 11. Почему bridge остаётся за основным LeanCTX

С planner side architecture остаётся Harr-native:

```text
Codex
  -> six LeanCTX core tools
      -> ctx_tools
          -> builder::start / wait / continue / inspect / cancel
```

То есть включение optional builder не добавляет его полный MCP schema напрямую
в Codex host config. Это следует текущему Harr принципу: specialized MCPs живут
за gateway.

`common/mcp/registry.json` получает optional server `builder` с
`required=false`. Компонент выключен в fresh selection и появляется только
после явного выбора пользователя.

## 12. Persistent OpenCode session

Каждый `builder_start` создаёт один OpenCode session id и хранит его в run state.
Все продолжения идут в **тот же session** через `opencode run --session ...` или
эквивалентный server API.

Initial launch передаёт:

- builder system contract;
- Execution Contract revision 1;
- только минимальный session bootstrap.

При blocker planner не пересылает initial plan заново. Он передаёт delta:

```text
HARR PLANNER RESOLUTION v1
Run: ...
Resolves blocker sequence: 4
New plan revision: 2
Decision: ...
Changed constraints: ...
Changed steps:
- B004: ...
Unchanged contract sections remain authoritative.
Continue from: B004
```

OpenCode session уже знает предыдущий plan, source reads, edits и failures.

### Context pressure

Не создавать новую OpenCode session автоматически только ради «чистоты».
Сначала полагаться на native OpenCode compaction. Если session действительно
невосстановима/переполнена, это отдельное recovery событие. Новый session тогда
seed-ится не полным transcript, а:

- canonical Execution Contract latest revision;
- completed step ledger;
- current workspace manifest;
- latest blocker/resolution state;
- references на raw artifacts.

Это recovery path, не normal workflow.

## 13. MCP tool surface

Bridge остаётся маленьким. Предлагается пять downstream tools.

### `builder::start`

Input:

- `repo_root`
- `task_label`
- `execution_contract`
- `allowed_paths`
- optional `model_override` only if user explicitly requested it

Behavior:

- validate config/readiness;
- acquire workspace lock;
- capture baseline;
- create run + OpenCode session;
- send initial contract;
- wait up to bounded `interactive_wait_secs` for a meaningful event.

Return:

- terminal packet if DONE/BLOCKED/FAILED arrived quickly;
- otherwise minimal RUNNING heartbeat + `run_id`.

### `builder::wait`

Input:

- `run_id`
- `after_sequence`
- optional bounded timeout

Это long-poll, а не busy polling. Tool возвращается сразу только если появился
новый meaningful event; иначе ждёт до Harr/LeanCTX-safe timeout и возвращает
минимальный heartbeat.

### `builder::continue`

Input:

- `run_id`
- `resolves_sequence`
- `plan_revision`
- `resolution_delta`

Bridge проверяет, что planner отвечает на текущий blocker и revision монотонно
увеличивается, после чего отправляет delta в **тот же OpenCode session**.
Как и `start`, может bounded-wait до следующего meaningful event.

### `builder::inspect`

Input:

- `run_id`
- opaque `artifact_ref`
- optional range/limit

Используется только когда compact packet недостаточен. Возвращает bounded raw
source diagnostic / command log / diff fragment / OpenCode event. Большие
результаты дополнительно проходят через LeanCTX archive/compression.

### `builder::cancel`

Останавливает active OpenCode work, сохраняет journal и workspace facts, но не
делает automatic revert.

`status` как отдельный tool не нужен: `wait(timeout=0)` покрывает query state и
уменьшает surface.

## 14. State machine

```text
CREATED
  -> RUNNING
      -> DONE
      -> BLOCKED
          -> RUNNING        (planner continue)
          -> CANCELLED
      -> FAILED_EXECUTION
      -> FAILED_PROTOCOL
      -> FAILED_GUARDRAIL
      -> CANCELLED
```

Дополнительные правила:

- terminal states immutable;
- каждый meaningful event имеет strictly increasing `sequence`;
- `continue` разрешён только из BLOCKED;
- stale planner response к старому blocker sequence отклоняется;
- одновременно только один writer run на workspace;
- service restart восстанавливает run metadata из journal, а не считает RUNNING
  успешным.

## 15. Terminal packet contract

Codex должен получать достаточно данных для качественного решения, но не весь
builder transcript.

Общая envelope:

```json
{
  "protocol": "harr.builder.v1",
  "run_id": "bld_...",
  "sequence": 7,
  "state": "DONE|BLOCKED|FAILED_EXECUTION|FAILED_PROTOCOL|FAILED_GUARDRAIL|CANCELLED",
  "plan_revision": 2,
  "current_step": "B004",
  "completed_steps": ["B001", "B002", "B003"],
  "session_ref": "oc_...",
  "workspace": {},
  "validation": [],
  "artifacts": []
}
```

### 15.1. Workspace section

Bridge формирует эту часть **механически**, а не верит модели:

```json
{
  "workspace": {
    "baseline_head": "...",
    "changed_files": [
      {"path": "src/foo.cpp", "kind": "modified"}
    ],
    "unexpected_changed_files": [],
    "preexisting_dirty_files_touched": [],
    "diff_stat": "2 files changed, 18 insertions(+), 4 deletions(-)",
    "diff_ref": "artifact:diff:7"
  }
}
```

Не включать полный diff по умолчанию.

### 15.2. Validation section

Bridge должен по возможности собирать command/exit facts из OpenCode JSON tool
events, а не только из финального prose модели:

```json
{
  "validation": [
    {
      "id": "V001",
      "command": "ctest -R worker_timeout",
      "outcome": "PASS",
      "exit_code": 0,
      "summary": "3/3 tests passed",
      "artifact_ref": "artifact:command:31"
    }
  ]
}
```

Log excerpt включается только если outcome != PASS или planner contract требует
конкретного evidence.

### 15.3. DONE-specific section

```json
{
  "completion": {
    "summary": "bounded factual summary",
    "contract_deviations": [],
    "unvalidated_items": []
  }
}
```

DONE запрещён, если:

- есть missing required validation;
- есть unexpected changed file;
- builder признал plan deviation;
- current contract step не завершён.

### 15.4. BLOCKED-specific section

```json
{
  "blocker": {
    "class": "PLAN_PRECONDITION_FALSE|UNSPECIFIED_DESIGN_DECISION|SCOPE_CONFLICT|BUILD_FAILURE_OUTSIDE_PLAN|TOOL_FAILURE|PERMISSION|OTHER",
    "statement": "one precise sentence",
    "expected": "what the contract assumed",
    "observed": "what was actually observed",
    "why_contract_is_insufficient": "short factual explanation",
    "decision_needed": "one exact question for planner",
    "safe_state": {
      "partial_edits": "kept|none|unknown",
      "can_continue_same_session": true,
      "resume_step": "B004"
    },
    "evidence": [
      {
        "kind": "source|diagnostic|test|tool",
        "locator": "src/foo.cpp:Worker::start",
        "excerpt": "bounded excerpt",
        "artifact_ref": "artifact:..."
      }
    ]
  }
}
```

### 15.5. Размер packet

Начальные soft caps:

- `summary`: <= 800 chars;
- blocker `statement`: <= 300 chars;
- `observed`/`expected`: <= 800 chars each;
- каждый excerpt: <= 1200 chars;
- default evidence items: <= 5;
- total terminal packet target: <= 6 KiB до LeanCTX compression.

Это не loss boundary: всё сверх caps сохраняется как artifact и доступно через
`builder::inspect`.

## 16. Не полагаться на final JSON модели как на единственный источник истины

Слабая модель может нарушить schema. Поэтому protocol assembly делится на два
слоя.

### Mechanical facts from bridge

- run/session ids;
- timestamps/sequences;
- changed files/diff stat;
- scope violations;
- OpenCode process exit;
- observed tool calls;
- command exit codes и captured logs;
- raw event refs.

### Semantic fields from builder model

- краткий `summary`;
- blocker classification;
- expected vs observed;
- decision needed;
- plan-step relation.

Model final response заканчивается специальным bounded protocol block. Bridge
валидирует его.

Если block invalid:

1. один раз отправить в **ту же session** protocol-repair message: «не делай
   новую работу; используя уже известные факты, выведи только valid packet»;
2. если повторно invalid — `FAILED_PROTOCOL` с raw final-response artifact ref.

Не зацикливать model на бесконечном self-repair.

## 17. Artifact journal: полнота без загрязнения Codex context

Run state хранится вне repo, например:

```text
~/.local/state/harr/builder/runs/<run-id>/
  run.json
  execution-contract-r1.md
  execution-contract-r2.delta.md
  events.ndjson
  artifacts/
    command-00031.txt
    model-final-00007.txt
    diff-00007.patch
  leanctx/
    config.toml
```

Свойства:

- raw artifacts никогда не помещаются в Git автоматически;
- secret-bearing output проходит существующую Harr/LeanCTX secret policy;
- metadata содержит content hashes;
- terminal packet содержит opaque refs, а не host absolute paths;
- retention configurable; initial default можно согласовать с LeanCTX archive
  horizon, но удаление journal не должно происходить посреди active run.

Таким образом compact return не теряет recoverability.

## 18. Planner response contract

На `BLOCKED` Codex не должен отвечать builder-у свободным разговорным текстом.
Он формирует `Planner Resolution Delta`:

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

Перед continue Codex при необходимости делает **targeted** investigation через
свой уже тёплый Harr/LeanCTX context. Он не обязан повторять discovery, которое
уже присутствует в planner context.

Если packet недостаточен, Codex сначала вызывает `builder::inspect` по одному
конкретному artifact ref, а не запрашивает «весь transcript».

## 19. Completion audit planner-а

DONE от builder — не безусловная гарантия корректности.

Bridge уже механически проверяет scope и validation ledger. После DONE Codex
делает bounded audit, заданный самим Execution Contract.

Минимум:

1. убедиться, что actual changed-file set соответствует plan;
2. убедиться, что все required validations имеют PASS;
3. проверить отсутствие contract deviations/unvalidated items;
4. если задача архитектурно чувствительна — targeted review изменённых symbols
   через уже существующий Harr/CodeGraph/LeanCTX path.

Не выполнять полный повтор всей planner investigation без причины.

Execution Contract может явно задать `planner_final_review: mechanical`,
`targeted` или `deep`. Default для обычной реализации — `targeted`.

## 20. OpenCode transport v1

Первый implementation не обязан зависеть от отдельного `opencode serve` daemon.
Использовать официальный automation path:

```text
opencode run --agent harr-builder --model <provider/model> --format json ...
opencode run --session <session-id> --format json ...
```

OpenCode session является persistent context boundary. Bridge парсит newline
JSON events и сохраняет их в journal.

Transport спрятан за adapter interface:

```text
OpenCodeAdapter.start(...)
OpenCodeAdapter.continue(session_id, ...)
OpenCodeAdapter.cancel(...)
OpenCodeAdapter.health()
```

Позже можно заменить CLI adapter на shared/background server API без изменения
MCP protocol или planner contract.

## 21. Model configuration

Bridge не содержит DeepSeek-specific logic.

Harr config, например:

```text
~/.config/harr/builder.json
```

поля v1:

```json
{
  "backend": "opencode",
  "model": "provider/model",
  "variant": null,
  "interactive_wait_secs": 100,
  "protocol_repair_turns": 1,
  "disable_project_config": true
}
```

API keys и provider auth не копировать в Harr — ими владеет OpenCode.

Commands:

```text
harr builder configure
harr builder status
harr builder set-model <provider/model>
```

`harr status` при включённом optional component показывает кратко:

```text
builder-bridge ready (opencode: ready, model: provider/model)
```

или конкретную причину `not-ready`.

Reasoning не требуется и не является protocol capability. Если provider имеет
reasoning variant, пользователь может настроить его отдельно, но default design
должен работать с model без reasoning.

## 22. Изменения структуры Harr

Предлагаемые common assets:

```text
common/
  builder/
    bridge.py                 # minimal stdio MCP server
    service.py                # run/state orchestration
    opencode_adapter.py       # CLI first, server adapter later
    protocol.py               # schemas + validation + caps
    journal.py                # run metadata/artifact refs
    workspace_guard.py        # baseline + changed-path validation
    config.py                 # builder config
    prompts/
      builder-system.md
      protocol-repair.md
  skills/
    harr-builder/
      SKILL.md
  mcp/
    registry.json             # optional builder entry
  policy/
    tool-routing.template.md  # explicit invocation rules
```

Tests:

```text
tests/
  test_builder_protocol.py
  test_builder_state_machine.py
  test_builder_journal.py
  test_builder_workspace_guard.py
  test_builder_opencode_adapter.py
  test_builder_policy.py
  test_builder_mcp_integration.py
```

Platform glue добавлять только там, где реально требуется. Core protocol,
journal и OpenCode adapter остаются common Python.

## 23. Registry / lifecycle integration

`common/mcp/registry.json`:

- новый `name = "builder"`;
- `required = false`;
- `transport = "stdio"`;
- `lifecycle = "on-demand"`;
- runtime invokes Harr-owned Python bridge;
- no secret entries;
- optional `skill_reference`/metadata для install selector.

Так как текущий manager различает runtime kinds, для Harr-owned Python runtime
либо:

1. расширить registry/manager явным `kind = "harr-python"`, который запускает
   repo-installed/copied Harr module через managed Python;
2. либо использовать `kind = "path"` с installed Harr wrapper.

Предпочтителен отдельный `harr-python`/internal runtime semantic, чтобы registry
не притворялся внешней dependency.

Fresh install: builder unchecked.
Existing installation: migration не должна самопроизвольно включать новый
optional component.

## 24. Long-poll и timeout strategy

Current Harr LeanCTX gateway имеет bounded downstream timeout, поэтому нельзя
делать один бесконечный MCP call на часовую задачу.

`start` и `continue` выполняют bounded wait до чуть меньшего gateway timeout.
Если builder всё ещё работает, packet минимален:

```json
{
  "protocol": "harr.builder.v1",
  "run_id": "bld_...",
  "sequence": 3,
  "state": "RUNNING",
  "current_step": "B006",
  "progress": "no planner action required"
}
```

Затем Codex вызывает `wait`, который снова long-poll-ит.

Не возвращать промежуточный stream логов в Codex. Intermediate OpenCode events
пишутся только в journal, пока не возник meaningful state transition.

## 25. Что считается meaningful event

В Codex возвращаются только:

- `DONE`;
- `BLOCKED`;
- любой `FAILED_*`;
- `CANCELLED`;
- bounded RUNNING heartbeat после timeout;
- редкий guard warning, требующий planner action.

Не возвращаются:

- каждый file read;
- каждый CodeGraph call;
- каждый edit;
- обычный successful compile line;
- reasoning/thinking модели;
- повторные progress messages.

## 26. Token-economy benchmark

Добавить новый reproducible benchmark рядом с существующим
`benchmarks/token-economy`.

Сравнить минимум три режима на одинаковой задаче с искусственным blocker:

### A. Manual fresh handoff

- Codex создаёт plan;
- новый OpenCode session получает plan;
- blocker вручную переносится в Codex;
- новый/перезапущенный builder получает plan + blocker + planner fix.

### B. Persistent builder session without compact protocol

- same OpenCode session;
- planner получает raw builder response/transcript fragments.

### C. Harr builder bridge

- same Codex context;
- same OpenCode context;
- compact blocker packet;
- resolution delta;
- LeanCTX on both sides.

Измерять отдельно:

- initial contract tokens;
- builder input/output provider tokens из OpenCode stats/session data;
- blocker packet size;
- resolution delta size;
- repeated-context bytes/tokens;
- number of planner model turns;
- tool-schema persistent context;
- task success;
- blocker correctness;
- scope violations;
- required-validation completion;
- protocol repair count.

Не утверждать, что разница в provider token count прямо равна ChatGPT/Codex
subscription usage units.

## 27. Тестовая стратегия

### 27.1. Protocol unit tests

- valid DONE;
- valid BLOCKED;
- caps/truncation -> artifact refs;
- stale sequence;
- stale plan revision;
- invalid continue state;
- one protocol repair then FAILED_PROTOCOL.

### 27.2. Workspace guard tests

- clean repo;
- repo with pre-existing dirty files;
- permitted edit;
- forbidden edit;
- touching pre-existing dirty allowed file;
- no auto reset/revert;
- non-Git workspace fallback.

### 27.3. Fake OpenCode adapter

Deterministic scripted adapter должен позволить CI проверять весь orchestrator
без API/model cost:

```text
start -> RUNNING
wait -> BLOCKED
continue -> RUNNING
wait -> DONE
```

Проверить, что planner packets не требуют raw transcript.

### 27.4. Real OpenCode integration test

Opt-in/local test с дешёвой model или deterministic test provider:

- create session;
- execute exact edit;
- hit planned blocker;
- continue same session;
- finish;
- assert same session id;
- assert scope guard;
- assert JSON event parsing.

Не делать paid external model обязательным для CI.

### 27.5. Harr install tests

- builder absent in required-only selection;
- builder selected explicitly;
- effective main gateway contains builder only when selected;
- builder-side LeanCTX gateway excludes builder;
- uninstall removes Harr-owned builder assets/config but preserves OpenCode auth
  and unrelated user config.

## 28. Acceptance scenario v1

Сценарий считается успешным, если можно в одной Codex conversation выполнить:

```text
@builder реализуй <test fixture task>
```

и наблюдается:

1. Codex сам делает investigation через Harr.
2. Codex строит детальный Execution Contract.
3. `builder::start` создаёт OpenCode session S.
4. Builder делает несколько edits/tests.
5. Fixture заставляет его встретить false precondition.
6. Builder возвращает compact BLOCKED packet без полного transcript.
7. Codex по packet + своему старому контексту принимает решение.
8. Codex отправляет resolution delta.
9. Bridge продолжает **session S**, не новую session.
10. Builder заканчивает DONE.
11. Scope guard подтверждает только разрешённые files.
12. Required validations PASS.
13. Codex делает bounded completion audit и сообщает пользователю результат.
14. Ни один manual copy/paste между planner и builder не требуется.

## 29. Этапы реализации

### Phase 0 — protocol spike

- Зафиксировать `harr.builder.v1` dataclasses/schema.
- Сделать fake adapter и state machine.
- Сделать artifact journal.
- Написать unit tests до OpenCode integration.

### Phase 1 — optional MCP integration

- Добавить optional registry entry.
- Реализовать minimal stdio MCP `start/wait/continue/inspect/cancel`.
- Провести его через main LeanCTX `ctx_tools`.
- Проверить, что persistent Codex schema overhead не растёт на полный builder
  tool catalog.

### Phase 2 — OpenCode CLI adapter

- Probe installed OpenCode version/capabilities.
- `run --format json` parsing.
- session id extraction/persistence.
- `--session` continuation.
- cancellation/process failure.
- no dependency on model reasoning.

### Phase 3 — hardened builder runtime

- `harr-builder` agent system prompt.
- `OPENCODE_DISABLE_PROJECT_CONFIG=1`.
- `--pure`.
- dynamic path permissions.
- no subagents/web/questions/native repo reads/shell.
- dedicated builder LeanCTX config with CodeGraph-only gateway.
- workspace lock/baseline/guard.

### Phase 4 — planner UX

- optional Harr skill.
- generated policy handling `@builder` and explicit natural-language calls.
- planner gates.
- Execution Contract rendering.
- Planner Resolution Delta rendering.
- bounded completion audit rules.

### Phase 5 — evidence quality

- parse tool execution facts from OpenCode JSON events.
- command/test ledger.
- diff refs and changed-file manifest.
- protocol repair turn.
- inspect by opaque artifact ref.

### Phase 6 — integration + benchmark

- fake deterministic end-to-end fixture.
- real OpenCode opt-in test.
- token-economy benchmark A/B/C.
- Linux manual acceptance.

### Phase 7 — portability

Только после Linux acceptance:

- macOS paths/process lifecycle;
- Windows OpenCode process/locking/path normalization;
- platform-specific integration tests.

Не заявлять support платформы до passing acceptance.

## 30. Решения, которые считаются зафиксированными этим планом

1. Builder bridge — optional Harr component.
2. Запуск v1 только явный.
3. `@builder` — canonical Harr marker; `$harr-builder` — optional native skill
   alias.
4. Codex всегда planner/orchestrator; OpenCode model — executor.
5. Builder model может не иметь reasoning.
6. Один logical run = один persistent OpenCode session.
7. Blocker возвращается в тот же Codex context компактным typed packet.
8. Continue возвращается в ту же OpenCode session delta-сообщением.
9. Raw transcript out-of-band, доступен только через targeted inspect.
10. Механические facts собирает bridge, а не доверяет prose модели.
11. Builder scope физически ограничивается permissions/workspace guard.
12. Builder использует отдельный LeanCTX profile без builder bridge и внешних
    write-capable MCPs.
13. Main Codex видит bridge только за `ctx_tools`.
14. Никаких automatic commits/pushes.
15. Никакого automatic reset/revert пользовательских изменений.
16. Protocol repair ограничен одной попыткой по умолчанию.
17. Full re-planning делает только Codex.

## 31. Открытые implementation details, которые надо проверить spike-ом

Эти пункты не должны менять архитектуру, но требуют empirical validation перед
кодом production path:

- точные JSON event types текущей установленной версии OpenCode;
- стабильный способ получить session id из `opencode run --format json`;
- точные OpenCode permission ids для Harr LeanCTX MCP tools;
- поведение cancellation для active `opencode run`;
- можно ли безопасно reuse shared OpenCode background service или для bridge
  лучше private/attached mode;
- какой timeout оставить между `interactive_wait_secs` и текущим LeanCTX gateway
  call timeout;
- как current OpenCode compaction отражается в exported/session events;
- минимальный cross-platform file locking primitive для workspace lock.

Если spike показывает, что CLI JSON stream недостаточно стабилен, заменить
только `OpenCodeAdapter` на server API. Planner protocol, MCP contract,
persistent-session model и token-economy architecture остаются без изменений.
