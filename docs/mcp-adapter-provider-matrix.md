# Этап 2 — матрица поверхностей провайдеров

**Дата:** 2026-11-17. **Хост GitLab:** `https://gitlab.sca.ad-tech.ru` (self-hosted EE, `19.5.1-ee`).
Захват через разрешённый маршрут: harr runner (`harr-mcp-run gitlab`) + LeanCTX gateway.
Заголовки авторизации и значения секретов не сохранялись; surface-захват содержит только
имена/описания/схемы/аннотации.

## Провайдер A — текущий: zereight mcp-gitlab (stdio, harr-managed)

- `serverInfo: zereight-gitlab-mcp-server v2.1.48`, MCP protocol `2025-03-26`.
- **216 инструментов**; полный захват: `docs/mcp-adapter-provider-matrix-gitlab-zereight.json`
  (имя, annotations, required, properties; исходный полный дамп с `inputSchema` целиком —
  вне git, 242 КБ, `/tmp/harr-mcp-adapter-stage2/zereight_surface.json`).
- Все 216 инструментов несут `inputSchema` и `annotations` (`readOnlyHint`, `destructiveHint`,
  `openWorldHint`); `outputSchema` — 0 (результаты нетипизированы, текст/JSON-в-тексте).

**Proof of routing (через gateway, квалифицированное имя):**

| Проверка | Результат |
|---|---|
| `ctx_tools find "merge request"` | каталог 216 инструментов, `gitlab::get_merge_request` и др. в top-5 |
| `gitlab::health_check {}` (read-only) | `{"status":"ok","authenticated":true,"gitlab_url":"https://gitlab.sca.ad-tech.ru/api/v4","version":"19.5.1-ee"}` |
| Негатив: `gitlab::get_merge_request {project_id: 99999999}` | ошибка всплыла verbatim: `GitLab API error: 404 Not Found / 404 Project Not Found`; сессия evicted; fallback на другой экземпляр/credential — нет (код: `proxy()` не ретраит и не переключает) |
| Квалификатор принадлежит upstream | вызов ушёл в runner `gitlab` (единственный экземпляр в тестовом конфиге), credential `mcp/gitlab/default` только ему |

## Провайдер B — официальный GitLab remote MCP (`/api/v4/mcp`)

- Эндпоинт существует: `https://gitlab.sca.ad-tech.ru/api/v4/mcp` → `401` с challenge
  `www-authenticate: Bearer realm="GitLab", scope="mcp",
  resource_metadata=".../.well-known/oauth-protected-resource/api/v4/mcp"`.
- Metadata защищённого ресурса: `authorization_servers: ["https://gitlab.sca.ad-tech.ru"]`,
  `scopes_supported: ["mcp"]` — **OAuth 2.0 (DCR), PAT не принимается**.
- Попытки неинтерактивной аутентификации: `Authorization: Bearer <PAT>` → 401;
  `PRIVATE-TOKEN: <PAT>` → 401. PAT уходит только собственному хосту GitLab.
- **Блокер захвата tools/list:** требуется одноразовая интерактивная OAuth-авторизация
  (браузерный flow; в LeanCTX реализован как `lean-ctx addon auth <name>` #1391, токен хранится
  в OAuth-сторе gateway). Без неё матрица официального провайдера не снимается — это
  **unresolved blocker**, а не поддерживаемое поведение. Сравнение "каких инструментов нет у
  второго провайдера" отложено до прохождения OAuth.

## Выводы для контракта (этап 4)

1. Два экземпляра одного вендора (GitLab) обязаны различаться **именем экземпляра**
   (`gitlab` vs `gitlab-official`) — квалификация `<instance>::<tool>` даёт независимые
   поверхности без переименования нативных инструментов.
2. Поверхности не приводятся к общему знаменателю: zereight отдаёт 216 собственных имён;
   официальный remote будет отдавать свой набор — разница остаётся видимой в исходном виде.
3. `annotations` существуют у zereight и теряются агрегатором каталога LeanCTX (пробел 1 из
   этапа 1) — для нативной поверхности их надо пробрасывать (additive-изменение ctx_tools).
4. Типы результатов: zereight возвращает текстовые блоки с JSON-строкой внутри; gateway
   склеивает текст и скрабит секреты; `structuredContent` не пересылается (пробел 2).
