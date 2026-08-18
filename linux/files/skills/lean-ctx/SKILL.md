---
name: lean-ctx
description: Harr-managed LeanCTX routing for repository research, CodeGraph analysis, GitLab access, shell/search/read operations, and MCP troubleshooting. Use this instead of upstream LeanCTX setup instructions on a Harr-managed machine.
---
<!-- harr-managed-skill-v1 -->

# LeanCTX under Harr

## Ownership contract

This machine uses **Harr** as the owner of the LeanCTX stack.

- Do **not** run the upstream LeanCTX installer, `lean-ctx setup`, `lean-ctx onboard`, or `lean-ctx update`.
- Do **not** independently install/upgrade CodeGraph or `@zereight/mcp-gitlab`.
- Repair or re-apply the managed stack with `harr status`, `harr install all`, and `harr leanctx apply`.
- Harr pins LeanCTX to 3.9.15 because newer versions are currently excluded from this environment.

## Managed topology

```text
agent host (Codex / OpenCode)
        |
        | MCP, cwd = target repository
        v
LeanCTX 3.9.15
        |
        +-- stdio child --> CodeGraph (`codegraph serve --mcp`)
        |                  inherits LeanCTX cwd
        |
        +-- Streamable HTTP --> GitLab MCP
                               http://127.0.0.1:3334/mcp
                               long-lived Harr user service
```

`node-repl` is intentionally outside the LeanCTX gateway. If the host application provides browser/Node tooling internally, use that host-provided route; do not add `node-repl` to LeanCTX.

## Project binding: CodeGraph

CodeGraph is deliberately **not** a machine-global service and has no Harr per-project config.
LeanCTX spawns it over stdio, and the child inherits LeanCTX's current working directory. CodeGraph therefore resolves the current repository from that cwd (and its own `.codegraph` index).

Before code analysis, ensure the agent host / LeanCTX process was started with cwd at the target repository root. If CodeGraph reports a wrong root, verify cwd and restart the host/LeanCTX from the correct repository root. Do not introduce `HARR_CODEGRAPH_PROJECT_ROOT`, an HTTP bridge, or project-specific Harr configuration to work around a cwd problem.

## Direct LeanCTX surface

The Harr profile intentionally exposes a small direct surface:

- `ctx_read`
- `ctx_shell`
- `ctx_search`
- `ctx_glob`
- `ctx_tools`
- `ctx_call`

Do not assume that `ctx_compose`, `ctx_session`, `ctx_knowledge`, `ctx_callgraph`, `ctx_patch`, or other LeanCTX tools are directly advertised. Discover or invoke rare LeanCTX capabilities through `ctx_call` rather than requiring more direct MCP registrations.

Editing is intentionally outside LeanCTX: use the host's native Edit/StrReplace facilities. `ctx_edit` and `ctx_patch` are disabled in this profile.

## Routing policy

For symbol search, reference/call tracing, architecture, and blast-radius analysis, use **CodeGraph first through the LeanCTX gateway**. Preferred call:

```text
ctx_tools(action="call", tool="codegraph::codegraph_explore", arguments={"query":"..."})
```

If `ctx_tools` is not directly exposed by the host, invoke it through `ctx_call`. Gateway calls should be sequential. Treat source returned by CodeGraph as already read; do not immediately duplicate the same investigation with repository grep/search.

For ordinary repository access use `ctx_read`, `ctx_search`, `ctx_glob`, and `ctx_shell` instead of native read/grep/find/shell when those direct LeanCTX tools are available.

For GitLab data, discover and call `gitlab::*` tools through `ctx_tools`. GitLab MCP is machine-global HTTP infrastructure managed by Harr; it is not spawned per project.

For Git remote/fetch/pull/push/branches/history/commits, use the separately registered direct Git MCP when available; do not route Git operations through the LeanCTX GitLab gateway.

## GitLab authentication

The GitLab PAT is not stored in the LeanCTX config. Harr stores it privately and the Harr `lean-ctx` wrapper exposes it to LeanCTX through a secret memento; LeanCTX sends it to the GitLab MCP as `Private-Token`.

Never print, read back, copy into prompts, or commit the secret. If authentication is missing, ask the user to run:

```bash
harr secret set gitlab
```

## Diagnostics

Start with:

```bash
harr status
```

GitLab service diagnostics:

```bash
harr mcp status gitlab
harr mcp logs gitlab
```

LeanCTX/config repair:

```bash
harr leanctx status
harr leanctx apply
harr install all
```

CodeGraph has no `harr mcp start/stop` lifecycle. It is spawned on demand by LeanCTX; diagnose its project binding from the LeanCTX/agent cwd instead.
