# Zread MCP in Harr

Zread is an optional **remote HTTP** MCP behind LeanCTX:

```text
Host -> LeanCTX -> https://api.z.ai/api/mcp/zread/mcp
```

It is Z.ai's coding-plan service for public GitHub repository research:
authentication uses the GLM Coding Plan API key (`harr secret set zread`; the
same key serves `websearch`, `webreader` and `zread`). Harr stores the raw key
and LeanCTX sends it as `Authorization: Bearer <key>` through a secret-header
memento.

Tools:

- `search_doc` — search repository documentation, issues, PRs and contributor news.
- `get_repo_structure` — directory structure and file list of a GitHub repository.
- `read_file` — read the full content of a specified repository file.

## Billing

Per the GLM Coding Plan credit rules, every MCP tool call to this server is
billed **per call** (output-multiplier 1.2 credit per call). Returned file
contents enter the context as input tokens on the next turn.

## Routing rules

- Prefer Zread over cloning a public repository for evaluation, dependency
  research, and issue/history troubleshooting.
- Use exact repo and file locators; keep queries narrow and batch related
  questions into one `search_doc` call.
- For private repositories or local checkouts, use the ordinary local
  repository routing instead.
