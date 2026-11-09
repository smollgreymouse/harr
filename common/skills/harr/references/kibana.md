# Kibana MCP in Harr

Kibana is an optional read-only on-demand MCP.

Route:
agent -> LeanCTX -> harr-mcp-run kibana -> kibana-agent mcp -> Kibana /api/console/proxy -> Elasticsearch

Harr pins the smollgreymouse/kibana-agent fork at commit 6334b36184d2d598d52339f6322fa1742b279f2f.
The fork adds KIBANA_API_KEY authentication, multiple trusted Kibana endpoints, per-endpoint API keys, and pins the Python MCP SDK to the v1 API used by kibana-agent.
Runtime installation and execution use uvx; no Docker container and no direct Elasticsearch endpoint are required.

Configure one or more non-secret endpoints in ~/.config/harr/mcp/kibana.env:
KIBANA_URL=https://kibana.example.com

Multiple endpoints are comma- or whitespace-separated. The first URL is the default:
KIBANA_URL=https://kibana.example.com,https://kibana-staging.example.com

Store API key material separately:
harr secret set kibana
harr secret status

A single stored KIBANA_API_KEY is shared by all configured URLs. If endpoints use different keys, store one comma-separated key per KIBANA_URL in exactly the same order. Harr injects the resulting secret only as KIBANA_API_KEY; it is never persisted in kibana.env or exposed by MCP tools.

The model can discover the configured endpoint list with list_kibana_endpoints. This returns only URLs plus which one is the default; it never returns API keys. When more than one endpoint is available and the target environment is not already unambiguous, call list_kibana_endpoints first and pass the exact chosen URL as kibana_url to the subsequent network tool.

All network tools expose an optional kibana_url argument. It may select only a URL already present in KIBANA_URL. The MCP automatically chooses the matching API key for that URL and rejects any unconfigured endpoint before sending a request.

The MCP is intentionally read-only. Useful tools include list_kibana_endpoints, list_data_views, search_logs, count_documents, get_histogram, get_context, get_mapping, list_fields, list_aliases, tail_logs, raw_es_query, and get_discover_url.
Use list_data_views to find Kibana Data View names; search_logs resolves their names to backing Elasticsearch index patterns.
For distinct values, counts, or distributions within large unstructured log strings, call raw_es_query with a read-only POST <index>/_search request, size: 0, runtime_mappings, and terms aggregations. This performs server-side analysis and returns compact buckets instead of pulling thousands of documents. search_logs can return large individual logs as _truncated; do not use it for bulk export when a server-side aggregation will answer the question.
raw_es_query still passes through kibana-agent's read-only guard. Prefer targeted tools and keep index patterns, time windows, fields, and result sizes narrow.

This route is suitable when Kibana is reachable but Elasticsearch is private: kibana-agent forwards allowed Elasticsearch reads through Kibana's /api/console/proxy.

Kibana Data View names/IDs are accepted by the normal query tools and resolved to their Elasticsearch title patterns. Use list_data_views when you need to discover the available Data Views explicitly.
