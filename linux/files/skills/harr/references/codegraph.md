# CodeGraph in Harr

CodeGraph is Harr's primary code-structure and relationship engine.

## When to use it

Use CodeGraph **first** for:

- symbol discovery;
- references and callers/callees;
- architectural exploration;
- dependency tracing;
- change impact / blast radius;
- locating the relevant implementation before reading files broadly.

Do not use CodeGraph merely to read a known file or exact line range; use LeanCTX for that.

## Routes

Harr may expose the same CodeGraph capability through more than one route:

1. **Direct CodeGraph MCP** — preferred when the agent host has it registered.
2. **CodeGraph through LeanCTX gateway** — compatibility/fallback route.

These are two transports to the same logical capability, not two independent sources that should both be queried.

### Route preference

Prefer direct CodeGraph when available because it removes one gateway hop and lets the agent host provide its normal MCP root/workspace context directly.

If direct CodeGraph is unavailable, use the LeanCTX gateway route. Harr keeps that route functional by having LeanCTX spawn `codegraph serve --mcp` as a stdio child; the child inherits LeanCTX's cwd and resolves the nearest `.codegraph` index.

Never call both routes for the same question just to compare answers. Use the secondary route only when the primary route is unavailable, fails, or is being diagnosed.

## Interaction with LeanCTX

Normal code-investigation sequence:

```text
CodeGraph first
    -> identify symbols/files/relationships
LeanCTX second
    -> read exact implementation/config/text that CodeGraph did not already return
native editor
    -> edit
Git MCP
    -> repository state/history/network Git operations when needed
```

Source text already returned by CodeGraph counts as read. Do not immediately repeat the same material through `ctx_read`/`ctx_search`.

For an exact known text lookup where graph reasoning adds no value, skip CodeGraph and use LeanCTX directly.

## Project binding

CodeGraph indexes remain project-local (`.codegraph`). Harr does not require a Harr config file inside each repository.

For the LeanCTX-gateway route, project binding follows the agent/LeanCTX cwd because the stdio CodeGraph child inherits that cwd.

For the direct route, use the project/workspace root supplied by the agent host.

If CodeGraph resolves the wrong project, diagnose the route's root/cwd instead of creating a machine-global project setting.
