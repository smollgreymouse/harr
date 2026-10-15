# Kibana MCP in Harr

Kibana is an optional read-only on-demand MCP.

Route:
agent -> LeanCTX -> harr-mcp-run kibana -> kibana-agent mcp -> Kibana /api/console/proxy -> Elasticsearch

Harr pins the smollgreymouse/kibana-agent fork at commit 73cb2aa03462c44616601d5299515ff45ed36d7f.
The fork adds KIBANA_API_KEY authentication and pins the Python MCP SDK to the v1 API used by kibana-agent.
Runtime installation and execution use uvx; no Docker container and no direct Elasticsearch endpoint are required.

Configure the non-secret endpoint in ~/.config/harr/mcp/kibana.env:
KIBANA_URL=https://kibana.example.com

Store the API key separately:
harr secret set kibana
harr secret status

Harr injects the secret only as KIBANA_API_KEY. The fork sends it as Authorization: ApiKey ... to Kibana and never persists it in a kibana-agent profile.

The MCP is intentionally read-only. Useful tools include list_data_views, search_logs, count_documents, get_histogram, get_context, get_mapping, list_fields, list_aliases, tail_logs, raw_es_query, and get_discover_url.
Use list_data_views to find Kibana Data View names; search_logs resolves their names to backing Elasticsearch index patterns.
For distinct values, counts, or distributions within large unstructured log strings, call raw_es_query with a read-only POST <index>/_search request, size: 0, runtime_mappings (extract the field from each log), and terms aggregations. This performs server-side analysis and returns compact buckets instead of pulling thousands of documents. search_logs can return large individual logs as _truncated; do not use it for bulk export when a server-side aggregation will answer the question.
raw_es_query still passes through kibana-agent's read-only guard. Prefer targeted tools and keep index patterns, time windows, fields, and result sizes narrow.

This route is suitable when Kibana is reachable but Elasticsearch is private: kibana-agent forwards allowed Elasticsearch reads through Kibana's /api/console/proxy.

Kibana Data View names/IDs are accepted by the normal query tools and resolved to their Elasticsearch title patterns. Use list_data_views when you need to discover the available Data Views explicitly.
