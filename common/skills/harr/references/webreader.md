# Web Reader MCP in Harr

Web Reader is an optional **remote HTTP** MCP behind LeanCTX:

```text
Host -> LeanCTX -> https://api.z.ai/api/mcp/web_reader/mcp
```

It is Z.ai's coding-plan service: authentication uses the GLM Coding Plan API key
(`harr secret set webreader`; the same key serves `websearch`, `webreader` and
`zread`). Harr stores the raw key and LeanCTX sends it as
`Authorization: Bearer <key>` through a secret-header memento.

Tools:

- `webReader` — fetch a public web page by URL: title, main content, metadata and links.

## Billing

Per the GLM Coding Plan credit rules, every MCP tool call to this server is
billed **per call** (output-multiplier 1.2 credit per call). The fetched page
also enters the context as input tokens on the next turn, which usually
dominates the per-call fee.

## Routing rules

- Use `webreader::webReader` through `ctx_tools` for reading a specific public
  page, typically the exact page found by a `websearch` hit.
- Prefer targeted URLs over crawling link lists; avoid re-reading the same page.
- A browser remains the fallback when Web Reader cannot reach or render the
  required content; state that limitation before switching.
