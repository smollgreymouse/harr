# Harr Workspace Service (LeanCTX fork): multi-root для Codex CLI и Desktop

> Статус: **план, реализация не начата**. Дата: 2026-10-14.
> Область: Harr + поставляемая интеграция LeanCTX; без патчей Codex.
> Решение: ручное управление проектными корнями в CLI и через HTML MCP App в Desktop при единой серверной модели.

## 1. Цель и принятые решения

Codex Desktop позволяет открыть проект с несколькими независимыми каталогами/репозиториями. LeanCTX должен искать, индексировать и читать файлы всех **явно включённых пользователем** каталогов в контексте выбранного Harr workspace, а не только текущего CWD. Для Codex CLI нужен ручной конфигуратор, для Desktop — HTML MCP App. Они должны обращаться к **одному Workspace Service в форке LeanCTX** и давать идентичный результат.

Зафиксированные решения:

1. **Не** читать внутреннюю БД/файлы сессий Codex, не опираться на приватные форматы.
2. **Не** пытаться выводить project roots из `permissionProfile`, `codex/sandbox-state` или `threadId`, не обновлять Codex ради этого.
3. **Не** патчить Codex и не требовать MCP `roots/list` (при этом не ломать уже существующую поддержку `roots/list` в LeanCTX).
4. Не хранить единственный глобальный список roots на все чаты: рабочие области изолированы.
5. `cwd` допустим лишь как кандидат на автоматический выбор проекта; при неоднозначности требуется явный выбор. `threadId` — ключ привязки сессии, **не** источник путей.
6. Добавление корня разрешает операции только внутри фактически доступного ОС/MCP sandbox; Registry **не выдаёт** прав Codex на запись или обход sandbox.
7. Изменения применяются к следующим вызовам без рестарта LeanCTX; индексы меняют scope согласованно.

## 1.1. Уточнение принятой архитектуры: live session + `.harr/`

**Решение:** единственный источник истины для **текущих effective roots** — состояние живой сессии LeanCTX (а не отдельный реестр Harr). Устойчивое локальное пользовательское дополнение хранится в **`<primary_root>/.harr/workspace.json`**, а не в `.lean-ctx.json` и не в `~/.lean-ctx` по умолчанию. В нашем **форке LeanCTX** требуется добавить API чтения/модификации этого состояния; CLI Harr и Desktop MCP App — тонкие клиенты одного API. Legacy project config `.lean-ctx.json` и `linkedProjects` продолжают учитываться как read-compatible источник, но новый Harr UI туда не пишет.

**Жёсткое runtime требование:** пользователь уже открыл чат в Codex, LeanCTX MCP уже запущен, сессия и индексы прогреты; открытие панели, `show`, `add`, `remove` должны **без переоткрытия чата, рестарта MCP/LeanCTX или обновления конфигурации Codex** показать текущие roots этой сессии и применить изменения для её следующего вызова. Запись JSON на диск сама по себе недостаточна. UI всегда запрашивает фактический snapshot у работающего LeanCTX, а не рисует сохранённый JSON в качестве текущего состояния.

Пример файла (примерные поля):

```json
{
  "schemaVersion": 1,
  "name": "game",
  "additionalRoots": ["../sprite-processing", "../shared"]
}
```

`primary_root` = директория-родитель `.harr`. Пути интерпретируются относительно неё, канонизируются и валидируются. Запись атомарная с revision/CAS, без потери других полей существующего файла; сохранять ли папку `.harr/` в Git решает пользователь. Создать файл при первом явном изменении, не при простом `show`.

**Разделить источники и состояние:**

- Live `SessionState.project_root` и `SessionState.extra_roots`: текущее рабочее состояние; также помнить источник каждого root (`session`, `mcp`, `ide`, `global`, `legacy-project`, `harr-project`) для UX и корректной мутации.
- `<root>/.harr/workspace.json`: постоянные пользовательские additions/removals. `remove` для корня, полученного из чужого источника, нельзя обещать постоянным без определения override/tombstone semantics; отображать конфликт и предложить явную операцию override, не удалять silently legacy/global настройки.
- LeanCTX global `extra_roots`, `allow_paths`, `read_only_roots`, `.lean-ctx.json` `linkedProjects` и client roots: совместимые источники входных данных, **не** отдельные источники истины для UI. Workspace Service возвращает один computed effective snapshot с provenance.
- Индекс: производное/кешированное состояние; не использовать index manifest как каталог проектов.

**Live API нашего форка LeanCTX (проект контракта):**

```text
workspace.current(session_context) -> {primary, roots:[{path,source,status,access}], revision}
workspace.discover_live(session_context) -> snapshot | selection_required
workspace.add(session_context, path, expected_revision) -> applied snapshot
workspace.remove(session_context, path, expected_revision) -> applied snapshot
workspace.select(session_context, workspace_id|primary_path) -> applied snapshot
workspace.list_known() -> [{primary,name,live?,sources}]  # best-effort persisted+live discovery
workspace.subscribe(session_context, since_revision) -> revision/events  # optional polling fallback
```

**Самое важное — связь с уже открытой сессией:** не путать MCP transport/session identity с глобальным процессом LeanCTX. Надо доказать в Phase 0, что каждый вызов от действующего Codex thread можно привязать к правильному `SessionState`, и что панель обращается к **той же** runtime session. `threadId`/`windowId`, реально присутствующие в `_meta`, могут служить идентификаторами маршрутизации только после проверки границы доверия и фактической реализации; они **не** служат источником каталогов. Если серверу неизвестно, к какой live-сессии относится вызов, запрещён silent fallback к случайной сессии: explicit select / явная привязка.

Обновление выполняется **в запущенном LeanCTX**: validate -> CAS revision -> atomic persistent config -> replace session effective roots (или transactional rollback при ошибке) -> invalidate scope/search caches -> enqueue index warm for added root -> вернуть applied snapshot. Все ветки чтения, поиска и PathJail должны использовать новый snapshot со следующего tool call. При частичном сбое возвращать честный статус и обеспечить recovery/reconcile на следующем запросе. Несколько параллельных сессий, подписанных на один `.harr/workspace.json`, должны увидеть новую revision без перезапуска; сессии других проектов сохраняют свою политику. Для уже запущенных вызовов отдельно описать семантику отзыва права.

**Phase 0 blocking gate:** real Codex Desktop -> live MCP App -> actual LeanCTX session snapshot -> change root -> real ctx_search within same open Codex thread -> concurrent unrelated thread unchanged. Без успешной проверки этого цикла нельзя называть функцию seamless. Если приложение использует другой MCP процесс или session state, предусмотреть RPC внутри LeanCTX (bounded local IPC) и идентификатор active session; не заводить зеркальную базу в Harr.

## 2. Проверенная отправная точка

- LeanCTX поддерживает `--root`, `extra_roots`, MCP `roots/list`, переменные `WORKSPACE_FOLDER_PATHS` / `VSCODE_WORKSPACE_FOLDER`, PathJail и multi-root resolution.
- `_leanctx_fix/rust/src/server/roots.rs`: нормализация/отбор корней; `server_handler.rs`: начальные roots; `call_tool/policy.rs`: отложенный `roots/list`; `multi_path.rs`: мультикорневая область; `dispatch/mod.rs`: фоновый прогрев дополнительных индексов.
- `allow_paths` — только разрешение доступа; `extra_roots` — дополнительно участие в multi-root поиске. Нельзя считать их взаимозаменяемыми.
- Для HTML MCP App в Harr уже существует прототип `common/mcp/gigacode_app/server.py`, в нём используются `ui/resourceUri`, `resources/read`, `visibility:["app"]`; обязательно переиспользовать подход после проверки совместимости с текущим Desktop.
- Фактический CLI эксперимент (Codex 0.162.1, 3 папки) лежит **локально** в `/tmp/harr-codex-multiroot-probe`: MCP-вызов прошёл, пришли `threadId/sessionId/windowId`, но не пришли `roots/list` и `codex/sandbox-state`. Не делать этот временный путь проектной зависимостью.

Важно: `_leanctx_fix/` в текущем локальном дереве Harr является untracked копией; **это не путевой контракт для production-пакета**. Реализацию LeanCTX вести в его настоящем upstream/fork с отдельным PR/версией, а Harr подключать через штатный путь зависимости.

## 3. Термины, сущности, модель данных

- **Workspace** — именованная, сохраняемая пользователем конфигурация, а не непременно один Git-репозиторий.
- **Primary root** — основная директория для относительных путей и fallback выбора.
- **Additional roots** — упорядоченный набор дополнительных каталогов, включая независимые Git-репозитории.
- **Binding** — выбор workspace для одной MCP-сессии / Codex thread, не замена состава workspace.
- **Effective roots** — разрешённая конфигурация на момент исполнения: зарегистрированные roots, прошедшие локальную проверку и проверки доступа.

Пример логической структуры (не окончательный сериализованный формат):

```yaml
schema_version: 1
workspaces:
  - id: ws_8f42  # стабильный непрозрачный идентификатор
    name: game-development
    primary_root: /home/user/Projects/game
    additional_roots:
      - /home/user/Projects/sprite-processing
      - /home/user/Projects/shared
    revision: 12
bindings:
  # session/thread-specific; persisted отдельно от основного списка
  session_or_thread_key: ws_8f42
```

Требования: атомарная запись, версионирование схемы, явная миграция, canonical/realpath где возможно, проверка существования, детерминированный порядок, удаление дубликатов (в том числе через symlink), запрет `/`, HOME и заведомо слишком широких roots по аналогии с LeanCTX. Запретить вложенные корни или дедуплицировать их без повторной индексации; правило определить и зафиксировать тестами. Каталог может стать недоступен: показывать диагностический статус и исключать из effective roots, не стирать пользовательские настройки молча. Файлу реестра — права только для владельца; разрешения каталогов не изменять.

Данные Binding отделить от Registry. Не сохранять в реестре bearer tokens, cookies, transcripts. Для ключа `threadId` предусмотреть scope по экземпляру сервера/соединению, если нельзя гарантировать глобальную уникальность; исключить утечку доступа через подменённые метаданные. Тщательно различать серверную MCP session identity и произвольные аргументы tool-call: пользовательская строка `threadId` не должна автоматически считаться доверенной.

## 4. Выбор текущего workspace

Алгоритм (предварительный):

1. Проверить существующий **валидный binding** для текущей MCP-сессии / надёжно идентифицированного Codex thread.
2. Если binding нет, проверить канонический `cwd`/контекст, который **реально** доступен серверу, и сопоставить его с зарегистрированными primary roots. Выбирать только однозначное совпадение; ближайший предок — отдельное правило при вложенных репозиториях.
3. Если нет совпадений или найдено несколько — вернуть `WORKSPACE_SELECTION_REQUIRED` и предложить список; **не** открывать первый попавшийся или чужой workspace.
4. При явном выборе записать binding для этой сессии. На следующем вызове применять актуальную конфигурацию и revision workspace.
5. Если невозможно надёжно определить session identity или проект из MCP-транспорта, разрешить явный workspace selector в аргументах инструментов, а для непомеченных вызовов fail closed. Не гадать по `sessionId` из недоверенного пользовательского ввода.

**Обязательный spike:** доказать, доступен ли реальный CWD нужного Codex thread в LeanCTX, а не CWD процесса MCP, который может быть общий. При невозможности: CLI явный `harr workspace use --workspace <id>` с привязкой к передаваемому вызову/обёртке, Desktop UI явный выбор workspace; не обещать автоматического определения, которого протокол не даёт.

Параллельные сессии A и B (разные workspaces) на одном long-lived MCP сервере обязаны сохранять собственный набор effective roots. Нельзя мутировать глобальный `session.extra_roots` при переключении чатов и тем самым расширить область поиска другому thread.

## 5. Сервисный контракт Registry

Предлагаемый WorkspaceService (один источник истины для CLI, MCP tools и App UI):

```text
list_workspaces() -> [{id, name, primary_root, count, revision}]
get_workspace(id) -> full configuration + validation diagnostics
create_workspace(name?, primary_root?, expected_context?) -> workspace
rename_workspace(id, name, expected_revision)
add_root(id, path, expected_revision) -> revised workspace
remove_root(id, path, expected_revision) -> revised workspace
set_primary_root(id, path, expected_revision)
delete_workspace(id, expected_revision, explicit confirmation)
bind_workspace(session_identity, id) -> binding
get_active_workspace(session_identity) -> workspace | selection_required
resolve_effective_roots(session_identity, operation) -> immutable snapshot
```

Мутации сериализуются и проверяют `expected_revision` (оптимистический контроль конфликтов), чтобы два открытых HTML окна не затёрли друг друга. В ответах возвращать ошибки вида `NOT_FOUND`, `INVALID_ROOT`, `ROOT_DUPLICATE`, `ROOT_UNAVAILABLE`, `REVISION_CONFLICT`, `WORKSPACE_SELECTION_REQUIRED`, `ACCESS_DENIED` с человекочитаемым пояснением. Audit log изменения конфигурации — без содержимого файлов.

**Безопасность доверия:** регистрация абсолютного пути сама по себе не делает его допустимым для текущей операции. PathJail принимает roots из доверенного registry snapshot, но процесс должен также пройти фактические ОС/sandbox проверки; приложения не должны объявлять право доступа на основании UI-конфигурации. Если статический PathJail глобален для процесса, разделить per-request policy или отказаться от общего сервера до устранения изоляции.

## 6. Codex CLI: ручной конфигуратор

Два фасада над WorkspaceService:

**Нативная консоль:**

```bash
cd /home/user/Projects/game
harr workspace create                                # name=game; primary=$PWD
harr workspace create --name game-dev                # explicit name; primary=$PWD
harr workspace create --root /home/user/Projects/game --name game-dev
harr workspace list                                  # all workspaces
harr workspace show                                  # workspace from cwd
harr workspace show --workspace game-dev             # explicit selection
harr workspace add ../sprite-processing              # workspace from cwd
harr workspace add ../shared --workspace game-dev     # explicit selection
harr workspace remove ../sprite-processing           # workspace from cwd
harr workspace remove ../shared --workspace game-dev  # explicit selection
harr workspace diagnose                              # workspace from cwd
harr workspace diagnose --workspace game-dev
harr workspace use --workspace game-dev               # explicit session binding; see caveat below
```


**Семантика `create`:** без аргументов `primary_root` берётся из текущего рабочего каталога (`cwd`) процесса `harr`, а `name` — из имени последнего компонента канонического пути. При явном `--root` без имени имя выводится из этой папки, а при явном `--name` без `--root` корнем остаётся `cwd`. Путь должен существовать и пройти общую валидацию. Не создавать второй workspace молча при конфликте имени: возвращать понятную ошибку и требовать другое имя либо выбор существующего workspace. Не создавать workspace автоматически при запуске Codex или Harr — только после команды `create`.

**Семантика `add` / `remove`:** если имя workspace опущено, определить его по **каноническому текущему каталогу (`cwd`)**: сначала точное совпадение с `primary_root`, затем однозначное нахождение внутри primary root (например, команда вызвана в `game/src`). Не выбирать workspace только потому, что `cwd` совпал с *additional root* другого workspace: каталог может совместно использоваться несколькими проектами. Если каталог принадлежит нескольким primary roots или определение неоднозначно — отказ с сообщением и подсказкой явного имени. Если workspace не найден — отказ с подсказкой `harr workspace create`. Не создавать workspace автоматически. Обе команды работают одинаково, отличие только в добавлении или удалении указанного root. Позиционный аргумент этих команд — исключительно путь; имя workspace передаётся только через `--workspace` (допустим короткий `-w`). `remove-root` не должен молча удалять primary root; для него отдельная операция смены primary root или удаления workspace. Сохраняется возможность явного синтаксиса `add PATH --workspace NAME` и `remove PATH --workspace NAME`; изменения подтверждаются и проверяются общим сервисом.

Разобрать действительный режим `use`: глобальный default опасен при параллельных сессиях. В MVP предпочтительнее явно передавать workspace id в MCP операции либо запускать Codex через тонкий wrapper с session-scoped переменной/контекстом, если его жизненный цикл надёжен. `use` без корректного адресата сессии должен объяснять ограничение, а не тихо устанавливать глобальный default.

**MCP tools:** `harr_workspace_list`, `harr_workspace_show`, `harr_workspace_select`, `harr_workspace_add_root`, `harr_workspace_remove_root` (и создание по необходимости). Явно типизированные аргументы, минимальные ответы без full directory trees. Read-only annotations для list/show; мутации требуют намеренного действия пользователя, запретить бесконтрольную правку списка roots агентом в ответ на текст из репозитория. При наличии механизма approvals в Codex использовать его; при отсутствии — подтверждение в собственном UI либо привилегированный конфигуратор с локальным контролем.

## 7. Codex Desktop: HTML MCP App

Одна открываемая по запросу панель **Harr Workspace** (не перманентная плавающая панель):

- Заголовок: активный workspace, проект, revision; переключение workspace через список.
- Primary root (отображение; изменение отдельным явным действием).
- Additional roots: список путей, статус `OK / missing / denied`, кнопка удаления.
- Добавление папки: путь вручную; системный file picker только если реально поддержан хостом; **не** имитировать доступ к filesystem из sandboxed HTML.
- Создание / переименование workspace, сохранение, inline ошибки валидации, индикатор несохранённых изменений и конфликтов ревизии.
- Диагностика effective roots и индексирования, без контента исходников в UI; индексация может идти асинхронно без блокировки окна.
- Чётко показать отличие «папка включена в LeanCTX» от «Codex имеет права чтения/записи».

Реализация как MCP App resource + app-only tools (проверить поддержку в текущем Codex Desktop), по образцу `common/mcp/gigacode_app/server.py`. Интерактивные вызовы `window.openai.callTool` / MCP Apps SDK — сверить с **фактически поддерживаемым** механизмом в этой сборке, не копировать частные хаки. UI не должен требовать чтения transcript агентом и не должен передавать полный список файлов в model-visible response.

Права: App UI без доступа к произвольным MCP инструментам; минимальные методы `workspace_ui_list/get/create/update/select`; серверная валидация всех параметров, никакого доверия к JavaScript/hidden fields. Ограничить HTML CSP, избегать inline injection из названий папок, экранировать данные, обеспечить адекватную обработку ошибок и повторного подключения.

## 8. Интеграция с LeanCTX

1. Определить реальный формат integration contract: встроенный Registry в LeanCTX vs Harr workspace adapter на стороне MCP gateway. **Не вводить два расходящихся списка roots**. Предпочтение: один сервис, LeanCTX получает immutable `WorkspaceSnapshot` per tool call.
2. Внедрить resolver перед PathJail и индексным dispatch, а не после проверки путей.
3. `primary_root` и `extra_roots` из snapshot работают с `multi_path.rs`; не подменять их `allow_paths`.
4. Пересмотреть кеши: индексирование по canonical root, scope набора roots + workspace revision; отсутствие результатов из других workspace; удалённые roots перестают участвовать в поиске **сразу**, даже если индекс ещё остался на диске.
5. Изменение набора roots не должно приводить к пересканированию всех прежних корней, если не изменилось их содержимое. Индексация нового root — demand-driven с видимым статусом.
6. Параллельные call-tools должны получить консистентный snapshot; мутации не меняют права уже начатого вызова внутри операции без явной стратегии cancellation/revocation. Для удаления доступа выбрать и задокументировать гарантию (на новом запросе немедленно; для in-flight лучше cancellation или fail-closed при следующем read).
7. Не ломать standalone LeanCTX: старые `--root`, `extra_roots`, `roots/list`, IDE env работают как раньше для тех, кто не использует Harr Registry.
8. Обратить внимание на index/path ownership между проектами с одинаковыми именами: ключи — canonical paths/ids, не basename.

## 9. Безопасность и границы доступа

- Реестр — trusted **локальная пользовательская конфигурация**, а не данные, извлечённые из недоверенного prompt/tool arguments без верификации.
- Отдельные папки одного workspace могут находиться вне текущего Codex sandbox. В этом случае возвращать явный `DENIED_BY_SANDBOX`, не подменять пустой результат успехом.
- Запрещать path traversal, symlink escape, URI decoding tricks, roots на HOME и `/`, широкие системные каталоги, дубли и недопустимые сетевые пути по политике платформы.
- Изолировать настройки между профилями пользователей и разными MCP соединениями; не распространять privileges через один long-lived LeanCTX session.
- Не давать произвольным текстам из репозитория/agent response автоматически добавлять roots. Подтверждение мутаций обязательно.
- Раздельно учитывать permissions «index/read» для LeanCTX и «write» для Codex. Не представлять Registry как механизм выдачи ОС прав.
- Сравнивать canonical paths корректно на Linux, macOS, Windows (включая case-insensitive volumes, UNC и junction/symlink).

## 10. Этапы реализации и gates

### Phase 0 — протокольный spike и архитектурный gate

- Исследовать процессную модель MCP в CLI и Desktop: сколько сессий на один сервер, CWD MCP vs CWD проекта, доверенность `threadId`, срок жизни binding.
- Изолированный тест с двумя одновременными чатами и тремя корнями, без чтения внутренней базы Codex.
- Проверить работающий двусторонний app-only MCP UI из Desktop на уже имеющемся GigaCode-примере.
- Принять документированное решение по хранению Registry (Harr vs LeanCTX) и транспортировке per-call snapshot.
- **Gate:** доказана идентификация workspace или выбран обязательный explicit selector; исключён cross-session leak; GUI поддерживает операции.

### Phase 1 — данные и сервис

- Versioned Registry, миграции, атомарная запись, блокировки, canonicalization, validation и ревизии.
- WorkspaceService unit tests; explicit session binding, fail-closed selection.
- **Gate:** два параллельных клиента не перезаписывают изменения; invalid paths отвергаются; нет глобальной утечки.

### Phase 2 — LeanCTX multi-root integration

- Per-call immutable snapshot, динамический PathJail и multi-root search; индексирование и отзыв корня.
- Сохранить legacy standalone paths без изменения семантики.
- **Gate:** искать по A+B+C можно после настройки; удаление B исключает результаты и доступ B; одновременный workspace D не видит A/B/C.

### Phase 3 — CLI конфигуратор и MCP инструменты

- Команды `harr workspace create/list/show/add/remove/diagnose/use`, диагностические ответы, выбор активного workspace; MCP read/mutation tools.
- **Gate:** CLI и MCP видят одинаковое состояние; без подтверждения мутации не выполняются.

### Phase 4 — Desktop HTML MCP App

- Реальная interactive UI, list/add/remove/select, ошибки, loading/indexing status, revision conflict.
- Проверка открытия по запросу и отсутствия модельного transcript.
- **Gate:** UI и CLI отражают одни и те же roots сразу; после закрытия/открытия панели выбор сохраняется в надлежащем scope.

### Phase 5 — packaging, docs, regression

- Подключить версионированный fork LeanCTX / adapter в Harr packaging; Linux приоритет, затем macOS/Windows.
- End-to-end tests для CLI, Desktop UI, single/multi-root и upgrade.
- README + troubleshooting + migration guide, без обязательных изменений рабочей конфигурации пользователей.
- **Gate:** старые single-root проекты работают без миграции, новые могут работать одновременно; откат на предыдущую версию не портит пользовательский реестр.

## 11. Матрица тестов (минимум)

| Сценарий | Критерий |
| --- | --- |
| 3 независимых Git repo | Поиск в каждом, точные абсолютные пути |
| Workspace A/B в параллельных чатах | Нет смешения результатов, permissions, индексов |
| Несколько окон одной Desktop App | Привязки не перетирают друг друга |
| Add root без перезапуска | Следующий запрос включает новый root |
| Remove root без перезапуска | Следующий запрос исключает root, в т.ч. из ранее прогретого индекса |
| Symlink/`..`/HOME/`/` | Защита PathJail и отказ в небезопасных roots |
| Root пропал/перемещён | Диагностика, fail-closed без удаления настройки |
| Конкурентные изменения из UI+CLI | revision conflict, сохранность данных |
| MCP tool call без достоверной сессии | Explicit selection вместо угадывания |
| Codex sandbox уже, чем Registry | Явное denial; никакого обхода sandbox |
| Standalone LeanCTX legacy | `--root`, config roots, IDE/MCP roots работают как раньше |
| Linux/macOS/Windows paths | Canonicalization и регрессия разделителей/case |
| UI отключен/не поддерживается | CLI и модельные MCP инструменты остаются доступны |

## 12. Разделение PR и зона ответственности

1. **LeanCTX fork: Live Workspace Service + `.harr/workspace.json` persistence + tests** (наследование legacy roots и сессионной информации).
2. **LeanCTX fork: session-scoped dynamic roots / index integration + security tests** (отдельный PR в форке с публичным контрактом адаптера).
3. **Harr: CLI facade + Desktop MCP App + tests** (повторное использование существующей инфраструктуры MCP Apps).
4. **Harr: packaging + docs + E2E** (версия LeanCTX зафиксирована, rollback инструкция).

До начала каждого PR проверить актуальное состояние рабочих веток и не включать случайные локальные untracked файлы/временные тесты. В текущей ветке Harr `feature/gigacode-worker-mcp` имеются многочисленные неотслеживаемые артефакты; новый код вести в отдельной ветке/PR, не менять несвязанные компоненты.

## 13. Definition of Done

Пользователь открывает Harr Workspace UI в Codex Desktop, явно выбирает один workspace и добавляет три корневые папки. LeanCTX при последующем чтении и поиске видит **ровно** его разрешённые корни. В другом чате с другим workspace видны **только его** корни. Те же операции доступны из CLI без Desktop. Никаких патчей Codex, чтения его БД, глобальных утечек PathJail, ручного рестарта LeanCTX и скрытого расширения прав.
