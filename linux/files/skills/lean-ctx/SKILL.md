---
name: lean-ctx
description: Component reference for LeanCTX on a Harr-managed machine: direct ctx_* surface, gateway semantics, project/cwd behavior, secret handling, and LeanCTX-specific troubleshooting. Harr skill owns cross-tool routing and priority.
---
<!-- harr-managed-skill-v1 -->

# LeanCTX under Harr

This skill documents the **LeanCTX component only**. It is not the source of truth for choosing between CodeGraph, LeanCTX, GitLab MCP, Git MCP or other Harr-managed tools.

For cross-tool priority and sequences such as **CodeGraph first**, load/follow the `harr` skill.

## Ownership contract

- Harr owns the LeanCTX binary, pinned version, wrapper and config.
- Do **not** run upstream `lean-ctx setup`, `lean-ctx onboard`, or `lean-ctx update`.
- Repair with `harr status`, `harr install all`, and `harr leanctx apply`.
- Harr currently pins LeanCTX to 3.9.15.

## Direct LeanCTX surface

The Harr profile intentionally exposes:

- `ctx_read`
- `ctx_shell`
- `ctx_search`
- `ctx_glob`
- `ctx_tools`
- `ctx_call`

Do not assume `ctx_compose`, `ctx_session`, `ctx_knowledge`, `ctx_callgraph`, `ctx_patch` or other LeanCTX tools are directly advertised. Discover/invoke rare LeanCTX capabilities through `ctx_call` rather than expanding the permanent MCP surface.

Editing is intentionally outside LeanCTX: use the host's native editor. `ctx_edit` and `ctx_patch` are disabled.

## Gateway semantics

LeanCTX can expose downstream MCP capabilities through `ctx_tools` / `ctx_call`. Which downstream should be preferred over a direct MCP route is decided by the Harr skill, not here.

Current downstreams include:

- CodeGraph compatibility/fallback route: LeanCTX spawns `codegraph serve --mcp` over stdio.
- GitLab normal route: LeanCTX connects to Harr's Streamable HTTP GitLab MCP at `http://127.0.0.1:3334/mcp`.

Gateway calls should be sequential unless a component explicitly documents otherwise.

## CodeGraph cwd behavior through LeanCTX

For the gateway CodeGraph route, CodeGraph is deliberately not a global daemon. LeanCTX spawns it as a stdio child; the child inherits LeanCTX's cwd and therefore resolves the current project from that cwd and its `.codegraph` index.

If this route resolves a wrong project, verify the agent/LeanCTX cwd and restart from the correct repository root. Do not add a machine-global project path or per-project Harr config as a workaround.

## GitLab authentication

The GitLab PAT is not stored in LeanCTX TOML. Harr's `lean-ctx` wrapper exposes the secret through LeanCTX secret-memento handling, and LeanCTX sends it to GitLab MCP as `Private-Token`.

Never print/read back the PAT. If it is missing, the user can set it with:

```bash
harr secret set gitlab
```

## LeanCTX diagnostics

```bash
harr status
harr leanctx status
harr leanctx apply
harr install all
```

For GitLab service diagnostics use Harr's service commands; CodeGraph gateway lifecycle belongs to the LeanCTX stdio session.
