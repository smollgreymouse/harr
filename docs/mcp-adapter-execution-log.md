# Исполнение плана MCP-адаптеров — полный лог (2026-11-17)

Полная хронология работ по `docs/project-mcp-adapters-execution-plan.md`, включая мерж,
откат и расследование спора об аутентификации официального GitLab MCP. Значения секретов
нигде не приводятся — только имена, хеши (sha12 blake3/sha256) и метаданные.

## Хронология

1. **Этап 0.** Ворктри `.worktrees/mcp-adapters-pr15` (ветка `codex/mcp-adapters-execution`)
   на head PR #15 `ed8e909`; путь зарегистрирован в Harr Workspace
   (skip-причина `same-repository-worktree`); base/head записаны в заметки PR
   (комментарий 1). Стек ребейзнут на master `af4aeb3` (3 PR-коммита — только доки).
2. **Этап 1 (gate) — PASSED.** Контракт LeanCTX `3.11.0-harr-unified.7` верифицирован
   рантаймом на изолированном конфиге (`LEAN_CTX_CONFIG_DIR=/tmp/harr-mcp-adapter-gate`):
   холодный старт 0 спавнов; `<instance>::<tool>`; прямой вызов поднимает только целевой
   upstream; no-fallback; fail-closed по секрету; TTL-каталог + `ctx_tools refresh`;
   find fan-out на все enabled. Пробелы зафиксированы (схемы/annotations/structuredContent,
   env-наследование детей).
3. **Этап 2.** Матрица: zereight — 216 инструментов (все с inputSchema+annotations),
   proof-of-routing `gitlab::health_check` → ok/authenticated, негатив 404 verbatim
   без fallback. Официальный `/api/v4/mcp` — на тот момент 401 на Bearer PAT и
   PRIVATE-TOKEN → ошибочный вывод «OAuth-only» (см. «Расследование» ниже).
4. **Этап 3.** Свойства secret store: файлы 0700/0600, без печати значений; пробелы —
   неатомарная ротация и утечка `LEAN_CTX_SECRET_*` в env upstream через `run_server`.
5. **Этап 4.** Дизайн-док переписан под верифицированный контракт (нативные поверхности,
   overlay + credential profiles; семантический фасад — вне скоупа).
6. **Этап 5.** Реализация: fail-closed overlay `.harr/mcp.json` (закрытая схема,
   HTTPS-only, digest-trust), профили с явными `bound_projects`, per-session gateway
   config (`LEAN_CTX_CONFIG_DIR` → `~/.config/harr/mcp-sessions/<key>/`), scoped экспорт
   секретов, санитизация env в `run_server`, атомарная ротация, CLI
   `harr mcp resolve|project|profile`, ключ `providers` в registry.json.
   По пути найден и исправлен баг: `manifest_path.parent` для `.harr/mcp.json` — это
   каталог `.harr`, а не корень проекта (trust сравнивался не от того ключа).
7. **Этап 6.** Приёмка: `tests/mcp-project-overlay.py` (9 секций) и
   `tests/mcp-adapter-runtime.py` (эрметика: два инстанса одного вендора, ленивость,
   изоляция wiring, fail-closed ghost) — PASS; регрессии registry/selection PASS.
8. **CI.** Прогон 1 (`d5c6b13`): linux ✅, windows ❌ (доки-дефект master,
   `tests/harr-doctor.py` WinError 193), macos ❌ (мой тест: сравнение unresolved-путей
   на macOS-симлинке `/var→/private/var`). В стек влит `e066cc8`
   (`codex/fix-harr-doctor-cross-platform`) — по решению пользователя; поправлен тест;
   прогон 2 (`1de6f3f`): **linux ✅ windows ✅ macos ✅**.
9. **Мерж.** PR #15 переведён в ready и смёржен в master (merge-commit `78a6979`)
   после вердикта по апгрейд-путу настроек (см. ниже — подтверждено: overlay-путь
   ленив и не затрагивает существующие `~/.config/harr`).
10. **Откат.** Пользователь оспорил вывод «OAuth-only» (у него curl с токеном работал).
    Откат: `git revert -m 1 78a6979` → master `a75721b`. PR-ветки и ворктри целы;
    исходный док пользователя в `/home/nmkartsev/Projects/harr/docs/` не тронут.

## Апгрейд-пут существующих настроек (вердикт до мержа, остаётся в силе)

Overlay-путь ленив: без `.harr/mcp.json` поведение побайтово прежнее (легаси-экспорт
секретов, без `LEAN_CTX_CONFIG_DIR`); selection/registry/env-файлы (`preserve`)/секреты
(0600) не затрагиваются; глобальный рендер LeanCTX контрактом `tests/mcp-registry.py`;
новые каталоги (`mcp-sessions/`, `mcp-profiles/`, `projects/`) создаются лениво 0700;
`run_server` вычищает только `LEAN_CTX_SECRET_*` (ни один провайдер этот префикс не
использует); `common/` копируется installer'ом целиком, рассинхрона manager/модули не
бывает, при отсутствии модулей — молча легаси-путь.

## Расследование «OAuth vs PAT» (после отката)

Спор: пользователь утверждал, что проверял официальный MCP-эндпоинт с токеном через curl
и это работало; мой этап 2 зафиксировал 401 на `Authorization: Bearer <PAT>` и
`PRIVATE-TOKEN: <PAT>` и вывод «OAuth-only». Результаты расследования:

1. **Серверный флап 401.** Вечером 17.11 REST GitLab отвергал валидные запросы
   переходящим образом: `/version` с тем же Bearer-токеном давал 401 в 21:36–21:44
   (в т.ч. когда параллельно node-fetch тем же токеном получал 200), а в 21:45+ —
   стабильно **200 (10/10)**. Бисекция заголовков (UA/Accept/HTTP1.1/HTTP2/IPv4),
   тест вне сандбокса — разницы нет: отказ был на стороне GitLab (подозрение на
   бекенд за балансировщиком или окно abuse-защиты). **Вывод этапа 2 сделан на
   отказавшем окне и был ошибочен.**
2. **PAT валиден.** Токен `bluemouse-harr` (expires 2027-10-21), scopes: `read_user`,
   `read_repository`, `read_virtual_registry`, `read_api`, `self_rotate`,
   `write_repository`, `write_virtual_registry`, `api`, `ai_features`, `create_runner`,
   `manage_runner`, `k8s_proxy` — REST аутентифицируется стабильно (200 на `/version`).
3. **MCP-эндпоинт требует scope `mcp`.** `POST /api/v4/mcp` с этим же Bearer PAT →
   `401` + `www-authenticate: Bearer realm="GitLab", scope="mcp",
   resource_metadata=".well-known/oauth-protected-resource/api/v4/mcp"`. У PAT нет
   scope `mcp` → эндпоинт честно отказывает. Это НЕ «PAT отвергаются категорически» —
   ожидаемо работает PAT **со scope `mcp`** (нужна проверка таким токеном; OAuth DCR —
   альтернативный путь, а не единственный).
4. Секретные байты нигде не печатались; вместо значений — хеши и метаданные
   (проверка значения в env ребёнка zereight выполнялась сравнением sha12).

### Исправленные выводы (замена блокера этапа 2)

- БЫЛО (ошибочно): «официальный GitLab MCP — OAuth-only, PAT не принимается».
- СТАЛО: «MCP-эндпоинт принимает Bearer-токены, но требует scope `mcp`; текущий PAT
  `bluemouse-harr` без этого scope получает 401+challenge. Путь включения: создать PAT
  со scope `mcp`, привязать к профилю (secret_headers Authorization Bearer), проверить
  initialize/tools/list. OAuth DCR остаётся запасным вариантом. Отдельно задокументирован
  переходящий серверный флап 401 на REST — при диагностике аутентификации повторять
  пробы серией, не делать вывод по одиночному 401.»

### Что осталось для повторного влития

1. Получить PAT со scope `mcp` (новый токен; self_rotate не добавляет scopes — токен
   создаётся пользователем), сохранить как новый секрет + профиль.
2. Проверить `initialize`/`tools/list` официального эндпоинта этим токеном → снять
   поверхность провайдера B, дополнить матрицу.
3. В registry.json поправить определение `gitlab-official` (`oauth: true` →
   secret_headers Bearer профиль без oauth) и прогнать тесты.
4. Создать новый PR из ветки `design/project-mcp-adapters` (после revert PR #15
   закрыт как merged и reopened быть не может) либо повторно смёржить по решению
   пользователя.

## Состояние артефактов

- master: `a75721b` (revert мержа) — изменения PR #15 в master отсутствуют.
- Ветка PR: `design/project-mcp-adapters` = `1de6f3f` (полный стек, CI 3 ОС зелёные).
- Бэкап-ветка: `codex/mcp-adapters-execution` (то же).
- Ворктри: `/home/nmkartsev/Projects/harr/.worktrees/mcp-adapters-pr15`.
- Доказательная база: `docs/mcp-adapter-gate-evidence.md` (этапы 1/3 + поправки),
  `docs/mcp-adapter-provider-matrix.md` (+ JSON поверхности zereight),
  этот лог, `docs/project-mcp-adapter-layer.md` (контракт).
