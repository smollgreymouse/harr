# Этап 1 — проверка контракта LeanCTX gateway (результаты gate)

**Дата:** 2026-11-17. **Деплой:** LeanCTX `3.11.0-harr-unified.7` (`/usr/lib/harr/linux/vendor/lean-ctx/lean-ctx`),
исходники — тег `harr-v3.11.0-unified.7` (= HEAD `_leanctx_fix`). Модуль gateway: `rust/src/core/mcp_catalog/`
(federated tool catalog #210, пул сессий #1078, postprocess #1095, OAuth #1391).

**Метод:** чтение исходников + изолированный рантайм-эксперимент (`LEAN_CTX_CONFIG_DIR=/tmp/harr-mcp-adapter-gate/config`):
3 тестовых stdio-upstream (alpha — секрет привязан, beta — без секретов, gamma — id секрета с отсутствующим memento).
Спавны детей фиксировались самими upstream (pid/timestamp/имена env-переменных, без значений).
Секреты в отчёт не выводились; тестовые значения — фиктивные.

## Верифицированное поведение (подтверждено рантаймом)

| Требование плана | Результат | Доказательство |
|---|---|---|
| Холодный старт сессии не запускает upstream | ✅ 0 спавнов | MCP-сессия lean-ctx + `tools/list` клиента: `logs/spawns.log` пуст; plain `tools/list` = 12 статических `ctx_*`-инструментов, квалифицированных имён нет |
| Ленивый запуск выбранного экземпляра | ✅ по прямому вызову | свежий процесс `ctx_tools call alpha::echo` → ровно 1 спавн (alpha); `proxy()` не читает каталог |
| Квалифицированные имена `<instance>::<tool>` | ✅ | `alpha::echo`, `beta::echo`; dedup по handle без коллизий (`catalog.rs`) |
| Вызов идёт к владельцу handle, без fallback | ✅ | `nosuch::echo` → `unknown or disabled gateway server`, 0 спавнов; вызов не ретраится (не-идемпотентность) |
| Ошибка одного провайдера не переключает на другой credential | ✅ | downstream `isError` всплывает verbatim (`downstream `alpha::fail` reported an error`); resolve-ошибка gamma не влияет на alpha/beta |
| Fail-closed при отсутствии секрета | ✅ | gamma: `missing secret memento 'mcp/test/missing' for 'GAMMA_TOKEN'`, ни одного спавна gamma за все прогоны; в каталоге попадает в `unavailable:` |
| Секрет только своему экземпляру | ✅ на стыке transport | `beta::env_probe` не видит `ALPHA_TOKEN`; `alpha::env_probe` видит; пул-ключ использует blake3-отпечаток секрета (ротация = новый ключ = новая сессия) |
| Динамическое обновление каталога | ✅ механизм gateway | TTL-кеш (default 300s) + `ctx_tools refresh` → `catalog::invalidate()` (кеш+пул); добавление сервера `delta` в конфиг видно на следующем rebuild |
| Поиск сужает кандидатов по описанию | ✅ но см. пробел 3 | BM25-ранжирование по `description` в top-N ChoiceCard |

## Контрактные пробелы (фиксируются, не скрываются)

1. **Полные `inputSchema` и `annotations` не видны агенту.** `CatalogEntry` хранит только
   `description` (первая строка в карточке) и компактную сводку `params: "text*"`. Исходная схема
   проходит только насквозь в момент `tools/call` (аргументы — passthrough без валидации gateway).
   Аннотации инструмента отбрасываются при агрегации. → Для сохранения нативной поверхности нужен
   additive-механизм показа полной схемы (например, действие `describe` в `ctx_tools` или расширенная карточка).
2. **Результаты вызова нормализуются к тексту.** `client::result_to_text`: текстовые блоки склеиваются,
   изображения/не-текст → `[image content omitted by gateway]`, `structuredContent` не пересылается verbatim;
   вывод дополнительно прогоняется через scrubbing секретов и opt-in postprocess (compress/spill/index).
3. **BM25-find делает fan-out на все enabled-экземпляры.** `catalog::build` коннектится к каждому
   `[[gateway.servers]]` с `enabled=true` (spawn+handshake+tools/list), единично за TTL (single-flight gate).
   Это допустимо только пока project overlay ограничивает множество enabled выбранными экземплярами;
   семантически «discovery запускает только выбранный экземпляр» обеспечивает путь прямого вызова.
4. **Наследование env детьми stdio.** Ребёнок наследует весь env процесса lean-ctx: все `LEAN_CTX_SECRET_*`,
   экспортированные harr `exec-leanctx`, видимы каждому stdio-ребёнку (значения). Изоляция держится на
   доверенном runner (`harr-mcp-run` → `manager.py run`), а не на санитизации env в gateway. Требуется
   проверка санитизации в `manager.py run` (этап 3) и явная строка в модели доверия (этап 4).
5. **`invalidate()` вызывается только из `ctx_tools refresh`.** Автоматического
   `tools/list_changed` от downstream к агенту нет; инвалидация при смене credential binding в harr
   достигается перезапуском сессии lean-ctx (env секретов фиксируется на старте процесса).

## Следствия для реализации (этап 5)

- Имена экземпляров = имена `[[gateway.servers]]` → квалификация `<instance>::<tool>` бесплатна.
- Коллизии: dedup по handle в каталоге уже есть; для двух экземпляров одного вендора имена экземпляров
  обязаны быть уникальными в effective registry (валидация overlay).
- Credential binding: `secret_env`/`secret_headers` + env `LEAN_CTX_SECRET_<hex(id)>` — профиль = id
  memento; ротация меняет значение и отпечаток пула; disable = удаление/отключение записи gateway.
- HTTP upstream: `secret_headers` c `format = "Bearer {secret}"`, sensitive-флаг, OAuth как альтернатива.

## Этап 3 — свойства текущего secret store (memento backend)

**Backend:** плоские файлы `~/.config/harr/secrets/<file>` (`common/shell/secret.sh`,
`common/mcp/manager.py`). Отдельного демо/шифрования нет — защита на диске = файловые права.

| Свойство | Состояние | Доказательство |
|---|---|---|
| Место хранения и граница чтения | файлы `~/.config/harr/secrets/` (dir 0700), читают только `manager.py` (`exec-leanctx`, `run_server`→`service_secret_env`), `git_https.py` (PAT file), `ein_instances.py`, `doctor.py` (presence/probe) | grep-трасса читателей; права `-rw-------` / `drwx------` |
| Защита на диске | umask 077 + `chmod 0600` при записи (`write_secret_file`); plaintext | `common/shell/secret.sh:3-9` |
| Backup/export/prune | команд export/backup секретов нет; prune касается workspace-store, не секретов | CLI-хелп `harr`; `manager.py workspace_prune_command` |
| Обновление/ротация/удаление | `harr secret set` перезаписывает (НЕ атомарно: `printf > file`), `unset` = `rm -f`; кеша значений нет (чтение на spawn; env процесса gateway фиксируется на старте → ротация требует новую сессию) | `secret.sh:28-55`, `exec_leanctx` |
| Маскирование в логах/ошибках | harr не печатает значения (`secret.sh:1`, `cmd_secret_status` — только configured/missing); lean-ctx: `redacted_stdio_env`/`redacted_values` (Debug), отпечатки blake3 в pool-identity, ошибки = безопасные id (`missing secret memento 'mcp/test/missing'`) | `config.rs`, `pool.rs`, эксперимент этапа 1 |
| Стабильный ID + отдельные ссылки | `memento_id` в registry → env `LEAN_CTX_SECRET_<hex(id)>`; значение меняется при ротации, ссылка постоянна | `manager.py memento_var`, `memento.rs env_name` |

**Пробелы (закрываются этапом 5, не скрыты):**

1. `run_server` строит env ребёнка как `os.environ.copy()` и НЕ вычищает `LEAN_CTX_SECRET_*` —
   реальный upstream-процесс (внук gateway) видит все секреты, экспортированные gateway. Фикс:
   strip в `run_server` (свой секрет ребёнок получает через `service_secret_env`).
2. Ротация не атомарна (`printf '%s\n' > file`) — нужен tmp+rename.
3. Слой credential-профилей (стабильный ID, привязка к instance+endpoint, явное межпроектное
   разделение) отсутствует — вводится этапом 5 поверх подтверждённых свойств хранилища.
4. Невыбранные секреты экспортируются в env gateway целиком (`exec_leanctx` экспортирует все
   секреты registry) — скоупится до отрендеренных инстансов сессии (этап 5).

## Этап 5–6 — реализация и приёмка (2026-11-17)

**Реализовано** (коммиты на ветке `codex/mcp-adapters-execution`, base = master):

- `common/mcp/project_overlay.py` — fail-closed манифест `.harr/mcp.json` (закрытая схема:
  только `schema/instances/extensions`; секреты/команды/аргументы/env исключены схемой),
  HTTPS-only эндпоинты (loopback-исключение), user-local trust по дайджесту
  (`~/.config/harr/projects/<key>/mcp-trust.json`), смена дайджеста = untrusted.
- `common/mcp/profiles.py` — user-local credential-профили (стабильный ID, провайдер,
  утверждённый endpoint, ссылка на секрет без байтов, состояние, явные `bound_projects`),
  атомарная запись 0600 (tmp+rename), отпечаток состояний для инвалидации.
- `common/mcp/manager.py` — per-session рендер: trusted overlay → effective registry
  (глобальный выбор + overlay-инстансы + доверенные http-расширения; disable через overlay)
  → сессионный `config.toml` в `~/.config/harr/mcp-sessions/<cache-key>/` (0700/0600,
  allow_paths/shell_allowlist наследуются от глобального конфига) → `LEAN_CTX_CONFIG_DIR`;
  экспорт `LEAN_CTX_SECRET_*` **только** для секретов отрендеренных инстансов;
  `run_server` вычищает `LEAN_CTX_SECRET_*` из env реального upstream (фикс находки 4
  этапа 3); CLI: `resolve`, `project {status|trust|revoke}`, `profile {list|set|enable|disable|remove}`.
- `common/mcp/registry.json` — новый ключ `providers` (определения для project-выбора;
  первый — `gitlab-official`, http + `profile_endpoint` + OAuth). Глобальный `servers`
  и рендер не изменены (регрессия `tests/mcp-registry.py` зелёная).
- `common/shell/secret.sh` — атомарная ротация (tmp+rename, фикс находки 2 этапа 3).
- CLI shell: `harr mcp resolve|project|profile`, usage-текст.
- `.github/workflows/selftest.yml` — py_compile новых модулей + шаги overlay/runtime-тестов.

**Инвалидация:** cache-key сессии = sha(формат, project key, дайджест registry, дайджест
манифеста, trust-дайджест, отпечаток состояний профилей) — любое изменение конфигурации
инстанса или credential binding даёт новый ключ; живые сессии подхватывают enable/disable
на следующем `ctx_tools`-действии; ротация значения секрета требует новой сессии
(задокументировано в дизайн-доке).

**Приёмка (этап 6):**

- `tests/mcp-project-overlay.py` — 9 секций PASS: fail-closed валидация манифеста
  (команда/секрет/не-HTTPS/userinfo/неизвестные поля отклоняются), trust-цикл, права
  профилей 0600 + атомарность, merge-семантика (disable/профиль/конфликты/unbound),
  scoped export (секрет disabled-инстанса не экспортируется), end-to-end профиль-инстанс
  через CLI, санитизация `run_server` (секрет не утекает в upstream), атомарная ротация,
  trust-CLI round-trip; диагностика без значений секретов.
- `tests/mcp-adapter-runtime.py` — PASS на деплой-бинарнике `3.11.0-harr-unified.7`
  (скип без бинарника): холодный старт 0 спавнов + статический tools/list; прямой
  квалифицированный вызов поднимает **только** адресуемый инстанс и повторяется на нём же;
  два инстанса одного вендора держат разные нативные поверхности; wiring секретов на
  транспортном стыке изолирован; отсутствующий memento = fail-closed (ghost ни разу не
  спавнен); каталог агрегирует оба вендора.
- Регрессии: `tests/mcp-registry.py`, `tests/mcp-selection.py` — PASS.

**Остались blocker'ы (в дизайн-доке, не скрыты):** полные inputSchema/annotations и
`structuredContent` не пробрасываются агенту (аддитивная апстрим-работа в LeanCTX);
официальный GitLab MCP требует интерактивной OAuth-авторизации (`lean-ctx addon auth`),
headless PAT отклонён эндпоинтом (этап 2); поведение streamable-HTTP клиента при
cross-origin redirect до включения profile-bound HTTP-инстансов требует проверки.

## ПОПРАВКА к этапу 2 (17.11.2026, после отката мержа)

Первоначальный вывод «официальный GitLab MCP — OAuth-only, PAT отвергается» был ошибочен:
он сделан на переходящем серверном окне 401 (REST тем же Bearer-токеном: 401 в
21:36–21:44, затем стабильно 200 (10/10) в 21:45+; бисекция заголовков/HTTP-версий/IPv4
и тест вне сандбокса разницы не дали — отказ на стороне GitLab). Фактическая причина
отказа MCP-эндпоинта на текущем PAT `bluemouse-harr` — отсутствие scope `mcp`
(challenge: `scope="mcp"`); REST тем же токеном работает. Ожидаемый путь: PAT со
scope `mcp` через профиль (`secret_headers` Authorization Bearer); OAuth DCR —
альтернатива. Полная хронология: `docs/mcp-adapter-execution-log.md`.
