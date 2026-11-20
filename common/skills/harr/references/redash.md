# Redash MCP

`redash` uses pinned `@suthio/redash-mcp@0.1.1` over stdio, behind Harr's
fail-closed MCP tool allowlist proxy. The proxy exposes metadata tools, saved
query execution, parameterized query execution, and ad-hoc SQL. Ad-hoc SQL can
use any data source available to the configured Redash token.
Dashboard and visualization mutations, CSV refresh, and other write tools stay
hidden. Database permissions remain enforced by the source credentials.

Enable with `harr mcp add redash` and `harr install mcp`. Configure
`~/.config/harr/mcp/redash.env` with `REDASH_URL` (no secrets), then
`harr secret set redash`. Check `harr secret status` and `harr status`.

`list_queries`, `get_query`, and `get_query_parameters` inspect saved-query
definitions and parameters. `execute_query` and
`execute_parameterized_query` run saved queries and return result rows.
`execute_adhoc_query` runs SQL against a selected Redash data source and returns
result rows. The proxy forwards the upstream schema and arguments unchanged.

Do not paste API keys in prompts or check them into repositories.
