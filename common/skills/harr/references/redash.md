# Redash MCP (Harr metadata-only)

`redash` uses pinned `@suthio/redash-mcp@0.1.1` over stdio, behind Harr's
fail-closed MCP tool allowlist proxy. No ad-hoc SQL, saved query execution,
CSV refresh, dashboard mutation, visualization mutation, or writes are permitted.
This restricts MCP tools, not Redash user credentials: use a dedicated least-
privilege API key and read-only database credentials wherever possible.

Enable with `harr mcp add redash` and `harr install mcp`. Configure
`~/.config/harr/mcp/redash.env` with `REDASH_URL` (no secrets), then
`harr secret set redash`. Check `harr secret status` and `harr status`.

Saved-query tools are metadata-only: `list_queries` lists saved query
definitions; `get_query` returns saved-query metadata and its SQL definition;
`get_query_parameters` returns saved parameter metadata. None of these tools
executes SQL, refreshes query results, or returns result rows. Other available
operations inspect data sources, schemas, dashboards and layouts, visualizations,
and widget parameter mappings. To examine result rows, use an explicitly
reviewed separate workflow; this integration never executes SQL.

Do not paste API keys in prompts or check them into repositories.
