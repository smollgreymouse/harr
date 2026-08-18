# CodeGraph in Harr

CodeGraph is Harr's primary code-structure and relationship engine.

Use it **first** for symbols, references, callers/callees, architecture, dependencies and blast radius. For a known file/range or exact text lookup, use LeanCTX directly instead.

## Normal route

```text
agent -> LeanCTX -> ctx_tools -> CodeGraph
```

LeanCTX spawns `codegraph serve --mcp` over stdio. The child inherits LeanCTX's cwd, so project binding follows the current agent/repository cwd and nearest `.codegraph` index. Harr needs no per-project config.

A direct CodeGraph MCP may also be installed/registered by Harr as a **diagnostic bypass**. It is not the normal route because exposing specialized MCPs directly defeats the gateway's tool-surface/context savings.

Never query gateway CodeGraph and direct CodeGraph for the same investigation unless diagnosing the gateway.

## Interaction with LeanCTX

```text
CodeGraph first
  -> identify relevant symbols/files/relationships
LeanCTX
  -> only missing exact reads/searches
native editor
  -> edit
Git MCP through gateway
  -> Git operations when needed
```

Source text already returned by CodeGraph counts as read; do not immediately fetch it again.

If the gateway CodeGraph route resolves the wrong project, diagnose agent/LeanCTX cwd instead of adding machine-global or per-project Harr root configuration.
