# Kibana MCP in Harr

Kibana is an optional read-only on-demand MCP.

Route:
agent -> LeanCTX -> harr-mcp-run kibana -> kibana-agent mcp -> Kibana /api/console/proxy -> Elasticsearch

Harr pins the smollgreymouse/kibana-agent fork at commit 2998352c4c360d10d8d1dfc114dc7d26217d537c.
The fork adds KIBANA_API_KEY authentication and pins the Python MCP SDK to the v1 API used by kibana-agent.
Runtime installation and execution use uvx; no Docker container and no direct Elasticsearch endpoint are required.

Configure the non-secret endpoint in ~/.config/harr/mcp/kibana.env:
KIBANA_URL=https://kibana.example.com

Store the API key separately:
harr secret set kibana
harr secret status

Harr injects the secret only as KIBANA_API_KEY. The fork sends it as Authorization: ApiKey ... to Kibana and never persists it in a kibana-agent profile.

The MCP is intentionally read-only. Useful tools include search_logs, count_documents, get_histogram, get_context, get_mapping, list_fields, list_aliases, tail_logs, raw_es_query, and get_discover_url.
raw_es_query still passes through kibana-agent's read-only guard. Prefer targeted tools and keep index patterns, time windows, fields, and result sizes narrow.

This route is suitable when Kibana is reachable but Elasticsearch is private: kibana-agent forwards allowed Elasticsearch reads through Kibana's /api/console/proxy.

Kibana Data View names/IDs are accepted by the normal query tools and resolved to their Elasticsearch title patterns. Use list_data_views when you need to discover the available Data Views explicitly.
