# Working agreements

## Глобальные skills вне репозитория

- Не загружай все глобальные skills на старте: выбери подходящий skill из доступного каталога, затем прочитай только его `SKILL.md` и явно необходимые им файлы.
- Для работы с LeanCTX/MCP-маршрутизацией используй Harr-managed skill `lean-ctx`; для установки, версий, сервисов, secrets и ремонта harness используй skill `harr`.
- Для выбранного skill вне активного репозитория используй встроенное нативное чтение файлов. Не вызывай для этих файлов CodeGraph или `lean-ctx`: оба инструмента должны оставаться привязаны к корню целевого репозитория.
- Это исключение даёт только read-only доступ к каталогам `/home/nmkartsev/.codex/skills/.system/`, `/home/nmkartsev/.codex/plugins/cache/openai-curated-remote/github/0.1.8-2841cf9749ae/skills/` и `/home/nmkartsev/.cache/JetBrains/CLion2026.1/aia/agents/.agents/skills/`.
- Для любых остальных путей сохраняются правила `lean-ctx` ниже.

## Harr-managed MCP topology

- Владелец локального context/MCP stack — **Harr**. Не устанавливай и не обновляй LeanCTX, CodeGraph или GitLab MCP напрямую; для этого используй `harr status`, `harr install all`, `harr leanctx apply` и `harr mcp ...`.
- **LeanCTX 3.9.15, прямой минимальный профиль:** `ctx_read`, `ctx_shell`, `ctx_search`, `ctx_glob`, `ctx_tools`, `ctx_call`. Это основной вход для исследования репозитория и доступа к gateway-возможностям по требованию.
- **CodeGraph через LeanCTX gateway:** LeanCTX запускает `codegraph serve --mcp` как stdio child для текущей agent-сессии. CodeGraph не является Harr/systemd service и намеренно наследует cwd LeanCTX, поэтому привязка к проекту определяется рабочим каталогом agent/LeanCTX, а не отдельным Harr-конфигом проекта.
- **GitLab через LeanCTX gateway:** `mcp-gitlab` — long-lived Harr user service с Streamable HTTP endpoint `http://127.0.0.1:3334/mcp`. LeanCTX передаёт PAT через secret header; никогда не читай и не печатай сам PAT.
- **node-repl:** намеренно не входит в LeanCTX gateway. Если host-приложение предоставляет Node/browser tooling внутренним маршрутом, используй его; не добавляй `node-repl` в LeanCTX.
- **Прямой `git-mcp`:** Git-состояние, remote, fetch, pull, push, ветки, история и коммиты. Для сетевых Git-операций это основной маршрут, не LeanCTX gateway.
- Не рассчитывай на прямые регистрации `codegraph` или `gitlab` в agent host: штатный маршрут для них — через LeanCTX gateway.

## Исследование кода через LeanCTX gateway

- Для поиска символов, трассировки ссылок и вызовов, архитектурного анализа и оценки blast radius первым вызовом используй CodeGraph через LeanCTX gateway: `ctx_tools` с `action="call"`, `tool="codegraph::codegraph_explore"` и прямыми аргументами `{ "query": "..." }`. Если `ctx_tools` не выведен отдельным инструментом, вызови его через `ctx_call`.
- Вызовы CodeGraph и других gateway tools выполняй последовательно. Не дублируй результат CodeGraph поиском по репозиторию: исходный код в ответе считай уже прочитанным.
- Для обычного доступа к репозиторию используй LeanCTX: `ctx_read` вместо `read`/`cat`/`head`/`tail`, `ctx_shell` вместо shell/bash, `ctx_search` вместо `grep`/`rg`, `ctx_glob` вместо `find`/`ls`. Нативные команды допустимы только для конфигураций, документации, сгенерированного или неиндексируемого контента, либо если соответствующий инструмент LeanCTX недоступен или вернул ошибку.
- Для редких или сложных возможностей LeanCTX не расширяй прямую MCP-регистрацию: сначала узнай доступную возможность и вызывай её через `ctx_call`.
- Перед началом работы с кодом убедись, что cwd agent/LeanCTX соответствует корню целевого репозитория. Это критично для CodeGraph: stdio child наследует этот cwd. Если CodeGraph сообщает неверный root, сначала проверь cwd и перезапусти agent/LeanCTX из корня нужного репозитория; не создавай `HARR_CODEGRAPH_PROJECT_ROOT`, HTTP bridge или per-project Harr config для обхода этой проблемы.
- Редактирование файлов выполняй нативными средствами рабочего окружения; `ctx_edit` и `ctx_patch` в этом профиле отключены.
- Для GitLab используй gateway tools `gitlab::*`, найденные через `ctx_tools`; для Git remote/history/branches используй прямой `git-mcp`.

## Диагностика harness

- Общая проверка: `harr status`.
- GitLab MCP: `harr mcp status gitlab`, затем при необходимости `harr mcp logs gitlab`.
- LeanCTX/config drift: `harr leanctx status`, `harr leanctx apply`; восстановление пинованных компонентов — `harr install all`.
- CodeGraph не имеет `harr mcp start/stop`: его lifecycle принадлежит LeanCTX stdio-сессии.
- Не запускай upstream `lean-ctx setup`, `lean-ctx onboard`, `lean-ctx update`, `codegraph install/upgrade` или глобальную установку Harr-managed MCP-пакетов.
