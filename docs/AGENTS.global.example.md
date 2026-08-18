# Working agreements

## Global skills

- Не загружай все skills на старте; читай только нужный `SKILL.md` и только необходимые ему references.
- Глобальные skills вне активного репозитория читай нативно; не используй для них CodeGraph/LeanCTX.
- Skill `harr` загружай только для установки/диагностики harness, а не для обычной работы с кодом.

## Repository tool routing

- Основной MCP-вход — **LeanCTX**; специализированные MCP обычно вызываются через его gateway, чтобы не держать их tool surface в контексте.
- Структура кода, символы, references/callers, архитектура, зависимости, blast radius → **CodeGraph first** через `ctx_tools`; не перечитывай сразу то, что CodeGraph уже вернул.
- Git status/branches/history/remotes/fetch/pull/push/commits → **git-mcp через LeanCTX gateway**.
- GitLab MR/pipeline/job/issue/project/server data → **gitlab через LeanCTX gateway**.
- Известные файлы/диапазоны, exact-text search, glob, shell/tests → `ctx_read` / `ctx_search` / `ctx_glob` / `ctx_shell`.
- Редактирование → native editor; `ctx_edit`/`ctx_patch` не использовать.
- Direct CodeGraph/Git/GitLab MCP, если зарегистрированы, — только diagnostic bypass при поломке gateway; не дублируй один запрос через direct и gateway.
- Для редких LeanCTX-возможностей используй `ctx_call`, не расширяя постоянный MCP surface.

## Project binding

- CodeGraph через LeanCTX запускается stdio-child и наследует cwd LeanCTX; при неверном root исправляй cwd, а не создавай per-project Harr config.
