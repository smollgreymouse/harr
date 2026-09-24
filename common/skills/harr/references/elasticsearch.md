# Elasticsearch MCP in Harr

Elasticsearch is an optional on-demand stdio MCP declared in `common/mcp/registry.json`:

```text
agent -> LeanCTX gateway -> harr-mcp-run elasticsearch
      -> @elastic/mcp-server-elasticsearch@0.3.1
      -> Elasticsearch
```

Harr uses Elastic's official npm package from the `elastic/mcp-server-elasticsearch` repository. The npm line is pinned to 0.3.1 and runs directly on Node.js, so Elasticsearch support adds no Docker/container dependency. The package is deprecated upstream in favor of the newer 0.4.x container line and Agent Builder on Elastic 9.2+, but it remains the official Elastic package and is suitable for direct read-only access to Elasticsearch 8.x.

Configure the non-secret cluster endpoint in the Harr-local `mcp/elasticsearch.env` generated from `common/mcp/elasticsearch.env.example`:

```text
ES_URL=https://elasticsearch.example.com:9200
ES_VERSION=8
OTEL_LOG_LEVEL=none
```

`ES_VERSION=8` is important for Elasticsearch 8.x, including 8.19.x, because this npm release otherwise assumes Elasticsearch 9.x behavior.

Store the API key separately:

```text
harr secret set elasticsearch
harr secret status
```

The registry stores it as the `elasticsearch-api-key` Harr secret and injects it as `ES_API_KEY` only for the MCP process. Do not put the key in `elasticsearch.env`, LeanCTX configuration, or the repository.

## Read-only data workflow

The official npm 0.3.1 server exposes four tools:

```text
list_indices
get_mappings
search
get_shards
```

Use `search` with Elasticsearch Query DSL for targeted retrieval and aggregations. Call `get_mappings` only when the needed field schema is unknown. Keep index patterns, time ranges, returned fields and `size` narrow to avoid unnecessary model context.

This npm release does **not** expose the later `esql` tool. ES|QL was added in the 0.4.x Rust/container line. Harr deliberately prefers the official Node package here to avoid making Docker a runtime dependency; if ES|QL becomes mandatory, either switch this component to the 0.4.x runtime or move to Agent Builder after upgrading Elastic to 9.2+.

A practical read-only API key for logs/metrics can use a role descriptor like:

```json
{
  "cluster": ["monitor"],
  "indices": [
    {
      "names": ["logs-*", "metrics-*"],
      "privileges": ["read", "view_index_metadata"]
    }
  ]
}
```

Tighten the index patterns to the data the agent actually needs. `read` permits document search and aggregations; `view_index_metadata` permits mapping/schema discovery; `monitor` supports the CAT index/shard discovery tools. None of these privileges grants index writes.

For Elasticsearch 8.19.x this gives Harr a compact official read-only data route without Docker. After upgrading to Elastic 9.2+, evaluate the built-in Agent Builder MCP separately rather than silently changing this registry entry.
