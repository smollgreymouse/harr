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
