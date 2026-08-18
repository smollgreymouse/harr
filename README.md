# Harr

Harr is a local harness for MCP/context-engineering infrastructure.

The name is both an Odin reference and a phonetic joke on “harness”.

## Managed stack

Harr pins and installs the stack it is built around:

- LeanCTX `3.9.15` — MCP gateway used by the agent;
- `@zereight/mcp-gitlab` `2.1.48` — native Streamable HTTP on `127.0.0.1:3334/mcp`;
- CodeGraph `1.5.0` — installed by Harr, but spawned by LeanCTX over stdio per agent/project context;
- Harr-aware `lean-ctx` and `harr` agent skills for Codex and OpenCode.

The resulting topology is deliberately hybrid:

```text
Codex / OpenCode
      |
      | stdio: lean-ctx
      v
LeanCTX 3.9.15
      |
      +-- stdio spawn -------> CodeGraph
      |                        inherits LeanCTX cwd
      |                        -> project-local .codegraph resolution
      |
      +-- Streamable HTTP --> GitLab MCP :3334 --> GitLab API
```

This is intentional. GitLab is long-lived HTTP because its stdio path was problematic in the affected LeanCTX setup. CodeGraph stays stdio because that preserves the caller/project working directory without any per-project Harr config.

`node-repl` is intentionally not part of Harr or the LeanCTX gateway.

## Install

Linux user-level installation:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh
```

The default installer installs/updates Harr, the complete pinned stack, and Harr-managed agent skills. It does not start/restart the GitLab MCP service automatically, so an already-running foreground server cannot collide with port `3334`.

After stopping any foreground GitLab MCP test process:

```bash
harr mcp start gitlab
harr status
```

To install and immediately restart managed services:

```bash
./install.sh --start
```

To update only Harr itself and its managed skills without downloading components:

```bash
./install.sh --harr-only
```

Harr uses a private npm prefix under `~/.local/share/harr/npm`; it does not need GitLab MCP or CodeGraph to be globally installed. A Node.js 20–24 runtime and npm must be available while installing/running the Node-based components.

## What is installed

```text
~/.local/bin/harr
~/.local/bin/lean-ctx                       # Harr wrapper
~/.local/bin/codegraph                      # Harr wrapper
~/.local/libexec/harr/
  cli/
  mcp/
  leanctx/
  skills/
  vendor/lean-ctx/3.9.15/lean-ctx          # real pinned binary
~/.local/share/harr/npm/                    # private npm runtime
~/.config/harr/
  runtime.env
  mcp/gitlab.env
  secrets/gitlab-pat
~/.config/lean-ctx/config.toml              # Harr-managed LeanCTX profile
~/.config/systemd/user/
  harr-mcp-gitlab.service
~/.codex/skills/{lean-ctx,harr}/SKILL.md
~/.config/opencode/skills/{lean-ctx,harr}/SKILL.md
```

A pre-existing non-Harr LeanCTX config is backed up before Harr takes ownership. Existing non-Harr `lean-ctx` and `codegraph` launchers are also backed up once under `~/.local/libexec/harr/backup/`. Existing non-Harr `lean-ctx`/`harr` skills are backed up once under `~/.local/libexec/harr/backup/skills/` before Harr replaces them.

## Agent guidance

Harr owns the `lean-ctx` skill on a Harr-managed machine because the upstream skill's generic setup/update instructions are not appropriate for a pinned harness. The Harr version documents the actual topology, minimal direct tool surface, CodeGraph cwd inheritance, GitLab HTTP/secret routing, and diagnostics.

Manage skill installation with:

```bash
harr agents apply
harr agents apply codex
harr agents apply opencode
harr agents status
```

`harr install all` and `harr install leanctx` re-apply the managed skills.

Harr deliberately does **not** overwrite a user's global `AGENTS.md`. A canonical Harr-aware example is versioned at [`docs/AGENTS.global.example.md`](docs/AGENTS.global.example.md); merge/copy that policy explicitly so personal working agreements remain user-owned.

## Why CodeGraph stays stdio

LeanCTX starts stdio downstream servers with a normal child process and does not override the child's working directory. The child therefore inherits the LeanCTX process cwd.

CodeGraph's MCP session uses an explicit MCP root when one exists, otherwise falls back to its own `process.cwd()` and walks upward to find the nearest indexed `.codegraph` project. This is exactly the behavior wanted for Codex/OpenCode projects: no machine-global project path and no Harr file in every repository.

The Harr LeanCTX config therefore uses:

```toml
[[gateway.servers]]
name = "codegraph"
transport = "stdio"
enabled = true
command = "codegraph"
args = [
    "serve",
    "--mcp",
]
url = ""
```

Harr installs `~/.local/bin/codegraph` as a wrapper around its pinned private CodeGraph package. The wrapper does not change directory, so the project cwd is preserved through the chain:

```text
agent cwd -> LeanCTX cwd -> spawned codegraph cwd
```

Each project still needs its normal CodeGraph index (`codegraph init`). No Harr project config is required.

## GitLab secret handling

Harr does not put the GitLab PAT into the repository or into the LeanCTX TOML.

The token is stored locally as:

```text
~/.config/harr/secrets/gitlab-pat
```

with mode `0600`. Harr's `lean-ctx` wrapper exports it using LeanCTX's secret-memento environment variable before executing the real LeanCTX binary. The generated gateway config contains only:

```toml
[gateway.servers.secret_headers]
Private-Token = { id = "mcp/gitlab/default" }
```

If an existing LeanCTX config contains a literal `Private-Token`, `harr leanctx apply` migrates it to Harr secret storage before replacing the config.

Manage the token with:

```bash
harr secret set gitlab
harr secret status
harr secret unset gitlab
```

## GitLab tool surface

Harr deliberately exposes the complete GitLab MCP tool surface:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

Actual GitLab permissions are still bounded by the PAT supplied to LeanCTX.

## Component installation

Reinstall the complete pinned stack and re-apply agent skills:

```bash
harr install all
```

Or just LeanCTX plus its managed agent guidance:

```bash
harr install leanctx
```

Or the Node-based components (GitLab MCP + CodeGraph):

```bash
harr install mcp
```

## MCP service orchestration

Only long-lived MCP daemons appear here. CodeGraph is intentionally not a service; LeanCTX starts it per downstream stdio session.

```bash
harr mcp list
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab -f
```

`all` remains accepted for lifecycle commands, so future Harr-managed MCP daemons can be added without changing the command model:

```bash
harr mcp start all
harr mcp restart all
harr mcp stop all
harr mcp enable all
harr mcp disable all
```

## Status

```bash
harr status
```

shows pinned/installed component versions, LeanCTX config/secret state, Harr-managed agent-skill state, and all long-lived Harr MCP service endpoints.

## LeanCTX

Reapply the Harr-managed profile:

```bash
harr leanctx apply
```

Check ownership/config state:

```bash
harr leanctx status
```

The generated profile keeps the research/shell/archive policy from the original setup, pins LeanCTX `3.9.15`, uses stdio for project-sensitive CodeGraph, and HTTP for Harr-managed GitLab MCP.
