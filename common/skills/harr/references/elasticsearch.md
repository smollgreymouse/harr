# Elasticsearch MCP in Harr

Elasticsearch is an optional on-demand stdio MCP declared in `common/mcp/registry.json`:

```text
agent -> LeanCTX gateway -> harr-mcp-run elasticsearch
      -> docker run docker.elastic.co/mcp/elasticsearch:0.4.6 stdio
      -> Elasticsearch
```

This is Elastic's official `elastic/mcp-server-elasticsearch` server. The pinned 0.4.6 release supports Elasticsearch 8.x and 9.x. It is especially useful for pre-9.2 clusters such as 8.19.x, where the newer Agent Builder MCP endpoint is unavailable. Upstream is deprecated in favor of Agent Builder on Elastic 9.2+ and receives critical security fixes only.

Docker must be available in `PATH`. `harr install mcp` pulls the pinned image when Elasticsearch is enabled; LeanCTX starts the container on demand over stdio, so Harr does not expose another listening port.

Configure the non-secret cluster endpoint in the Harr-local `mcp/elasticsearch.env` generated from `common/mcp/elasticsearch.env.example`:

```text
ES_URL=https://elasticsearch.example.com:9200
```

The URL must be reachable from the Docker container. In particular, `localhost` inside the container is not the host machine.

Store the API key separately:

```text
harr secret set elasticsearch
harr secret status
```

The registry stores it as the `elasticsearch-api-key` Harr secret and injects it as `ES_API_KEY` only for the MCP process/container. Do not put the key in `elasticsearch.env`, LeanCTX configuration, or the repository.

## Read-only data workflow

The server exposes five tools:

```text
list_indices
get_mappings
search
esql
get_shards
```

Prefer `esql` for bounded time-window analysis, aggregation and correlation; use `search` for targeted Query DSL retrieval. Call `get_mappings` only when the needed field schema is unknown. Avoid broad index discovery or unbounded result sets when a known index pattern and time range are available.

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

Tighten the index patterns to the data the agent actually needs. `read` permits document search and ES|QL reads; `view_index_metadata` permits mapping/schema discovery; `monitor` supports the CAT index/shard discovery tools. None of these privileges grants index writes.

For an Elasticsearch 8.19.x cluster, this MCP is the intended Harr route for direct data investigation. After upgrading to Elastic 9.2+, evaluate the built-in Agent Builder MCP separately rather than silently changing this registry entry.
