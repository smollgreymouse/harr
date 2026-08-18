# Harr

Harr is a small local harness supervisor for long-lived MCP infrastructure.

The name is both an Odin reference and a phonetic joke on “harness”.

## Managed stack

Harr pins and installs the stack it is built around:

- LeanCTX `3.9.15` — MCP gateway used by the agent;
- `@zereight/mcp-gitlab` `2.1.48` — native Streamable HTTP on `127.0.0.1:3334/mcp`;
- CodeGraph `1.5.0` — semantic code intelligence;
- Supergateway `3.4.3` — stateful stdio → Streamable HTTP bridge for CodeGraph on `127.0.0.1:3333/mcp`.

The resulting topology is:

```text
Codex / OpenCode
      |
      | stdio: lean-ctx
      v
LeanCTX 3.9.15
      |
      +-- Streamable HTTP --> Harr CodeGraph bridge :3333 --> CodeGraph stdio
      |
      +-- Streamable HTTP --> GitLab MCP :3334 --> GitLab API
```

`node-repl` is intentionally not part of Harr or the LeanCTX gateway.

## Install

Linux user-level installation:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh
```

The default installer installs/updates Harr and the complete pinned stack. It does not start/restart MCP services automatically, so an already-running foreground server cannot collide with ports `3333` or `3334`.

After stopping any foreground test processes:

```bash
harr mcp start all
harr status
```

To install and immediately restart managed services:

```bash
./install.sh --start
```

To update only Harr itself without downloading components:

```bash
./install.sh --harr-only
```

Harr uses a private npm prefix under `~/.local/share/harr/npm`; it does not need the GitLab MCP, CodeGraph, or Supergateway packages to be globally installed. A Node.js 20–24 runtime and npm must be available while installing/running the Node-based components.

## What is installed

```text
~/.local/bin/harr
~/.local/bin/lean-ctx                       # Harr wrapper
~/.local/bin/codegraph                      # Harr wrapper
~/.local/libexec/harr/
  cli/
  mcp/
  leanctx/
  vendor/lean-ctx/3.9.15/lean-ctx          # real pinned binary
~/.local/share/harr/npm/                    # private npm runtime
~/.config/harr/
  runtime.env
  mcp/gitlab.env
  mcp/codegraph.env
  secrets/gitlab-pat
~/.config/lean-ctx/config.toml              # Harr-managed LeanCTX profile
~/.config/systemd/user/
  harr-mcp-gitlab.service
  harr-mcp-codegraph.service
```

A pre-existing non-Harr LeanCTX config is backed up before Harr takes ownership. Existing non-Harr `lean-ctx` and `codegraph` launchers are also backed up once under `~/.local/libexec/harr/backup/` before Harr installs its wrappers.

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

## CodeGraph bridge

CodeGraph currently speaks stdio MCP, so Harr runs it behind a stateful Supergateway bridge. Harr pins Supergateway and applies a checked patch to bind the Streamable HTTP listener to `127.0.0.1` rather than all interfaces.

LeanCTX's downstream MCP client does not forward the parent client's workspace roots to CodeGraph. Therefore `~/.config/harr/mcp/codegraph.env` contains an optional fixed root:

```text
HARR_CODEGRAPH_PROJECT_ROOT=
```

Leave it empty for a global bridge and pass CodeGraph's `projectPath` tool argument, or set it to a project path and restart CodeGraph:

```bash
$EDITOR ~/.config/harr/mcp/codegraph.env
harr mcp restart codegraph
```

Each project still needs a CodeGraph index (`codegraph init`) as usual. Harr installs a normal `~/.local/bin/codegraph` wrapper so the pinned private copy is available for CLI use.

## Component installation

Reinstall the complete pinned stack:

```bash
harr install all
```

Or just the LeanCTX side:

```bash
harr install leanctx
```

Or the Node-based MCP runtime (GitLab MCP + CodeGraph + bridge):

```bash
harr install mcp
```

## MCP orchestration

```bash
harr mcp list
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab -f

harr mcp start codegraph
harr mcp stop codegraph
harr mcp restart codegraph
harr mcp status codegraph
harr mcp logs codegraph -f
```

`all` is accepted by lifecycle commands:

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

shows pinned/installed component versions, LeanCTX config/secret state, and all Harr-managed MCP service endpoints.

## LeanCTX

Reapply the Harr-managed profile:

```bash
harr leanctx apply
```

Check ownership/config state:

```bash
harr leanctx status
```

The generated profile keeps the research/shell/archive policy from the original setup, uses LeanCTX `3.9.15`, and routes downstream GitLab and CodeGraph through HTTP endpoints managed by Harr.
