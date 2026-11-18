# Web Search MCP in Harr

Web Search Prime is an optional **remote HTTP** MCP behind LeanCTX:

```text
Host -> LeanCTX -> https://api.z.ai/api/mcp/web_search_prime/mcp
```

It is Z.ai's coding-plan service: authentication uses the GLM Coding Plan API key
(`harr secret set websearch`; the same key serves `websearch`, `webreader` and
`zread`). Harr stores the raw key and LeanCTX sends it as
`Authorization: Bearer <key>` through a secret-header memento; the key never
appears in configuration or agent context.

Tools:

- `webSearchPrime` — web search returning page titles, URLs, summaries and site names.

## Billing

Per the GLM Coding Plan credit rules, every MCP tool call to this server is
billed **per call** (output-multiplier 1.2 credit per call), independent of the
payload size. Batch related lookups into one targeted query instead of issuing
many narrow calls; `harr doctor websearch` uses catalog-only probes and never
spends a call.

## Routing rules

- Use for web research, real-time facts, and public information that local
  repositories and the Harr Kibana/GitLab routes cannot answer.
- Gateway discovery is ranked: search for the exact bare tool name
  (`webSearchPrime`) and call it as `websearch::webSearchPrime` through
  `ctx_tools`.
- Keep queries narrow; a search result enters the context as input tokens on
  the next turn, which usually dominates the per-call fee.
