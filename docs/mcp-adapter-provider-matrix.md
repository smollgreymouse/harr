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
  `scopes_supported: ["mcp"]`.
- **ПОПРАВКА (после отката мержа, 17.11.2026 вечер):** первоначальный вывод
  «PAT не принимается, OAuth-only» был сделан на переходящем серверном окне 401
  (REST GitLab тем же токеном давал 401 в 21:36–21:44 и стабильно 200 (10/10) в 21:45+).
  Фактический отказ MCP-эндпоинта на текущем PAT — из-за отсутствия scope `mcp`
  (у `bluemouse-harr`: `api`, `read_api`, `ai_features`, `k8s_proxy`, … без `mcp`).
  Ожидаемо работает Bearer PAT **со scope `mcp`** — требуется проверка таким токеном;
  OAuth DCR — альтернатива, не обязательное требование. Подробности и хронология проб:
  `docs/mcp-adapter-execution-log.md`.
- **Блокер захвата tools/list (уточнён):** нужен токен со scope `mcp` (новый PAT +
  профиль) или OAuth DCR (`lean-ctx addon auth`). До проверки таким токеном матрица
  официального провайдера не снята; сравнение «каких инструментов нет у второго
  провайдера» отложено.

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
