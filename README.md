# Harr

> *Herblindi ok Hár.*
>
> **Harr er reiði Hárs.**
>
> — *Grímnismál 46* / with apologies to the skalds

A global harness for token-efficient MCP infrastructure.

## Design

Harr is not merged into another global harness. On first installation it takes **clean ownership of its global layer**, after saving an exact rollback snapshot. Project-level configuration is deliberately out of scope.

Harr-managed specialized MCPs stay behind LeanCTX so their large schemas do not live permanently in the agent context. Unrelated third-party MCPs and skills may coexist globally.

```text
Codex / OpenCode
      |
      | Harr-managed route: LeanCTX
      v
LeanCTX 3.9.15
      |
      +-- stdio -----------> CodeGraph 1.5.0
      |                     inherits LeanCTX cwd
      |
      +-- HTTP :3334 -----> GitLab MCP 2.1.48 -> GitLab API
      |
      +-- future Harr MCPs -> gateway when appropriate

Unrelated third-party MCPs/skills may coexist beside this stack.
```

Direct Harr-managed CodeGraph/GitLab registrations are not part of the normal profile; they are diagnostic/on-demand bypasses only.

## Quickstart

Fresh install:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean --start
```

Configure the GitLab PAT once:

```bash
harr secret set gitlab
```

Check the whole harness:

```bash
harr status
```

Expected normal routing after restarting/reopening Codex or OpenCode:

```text
Codex / OpenCode -> LeanCTX
                    +-> CodeGraph   (stdio, per-project cwd)
                    +-> GitLab MCP  (HTTP, Harr user service)
```

For later Harr updates:

```bash
cd harr
git pull
./install.sh
```

Rollback the entire global Harr takeover:

```bash
harr uninstall
```

If a foreground test instance of `mcp-gitlab` is already using port `3334`, stop it before the first `--start` install.

## First install

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean
```

`--clean` is required for the first takeover. Before writing global state, Harr snapshots the existing global harness under:

```text
~/.local/share/harr-state/pre-harr/
```

Later updates do not replace that original snapshot:

```bash
./install.sh
```

Useful modes:

```bash
./install.sh --clean --start  # first takeover + start/restart long-lived MCP services
./install.sh --harr-only      # update Harr/global policy/config/skills only
```

The installer is user-level; do not use `sudo`.

## What clean takeover owns

Harr owns and regenerates:

- global Codex `AGENTS.md`, Harr/LeanCTX diagnostic skills, and the Harr-owned `mcp_servers.lean-ctx` entry in `config.toml`;
- global OpenCode `AGENTS.md`, Harr/LeanCTX diagnostic skills, and the active global OpenCode harness config;
- Harr LeanCTX binary/wrapper/config;
- Harr CodeGraph wrapper/private package;
- Harr GitLab MCP service/config/secret handling;
- Harr-private runtime/state directories.

Harr does **not** touch project-level `AGENTS.md`, `.opencode`, skills, CodeGraph indexes, or other repository files.

### Replacing `opencode-workflow`

The OpenCode clean takeover recognizes and removes the retired workflow pieces from the active global OpenCode config:

- `flow`, `wf-design`, `wf-build`, reviewer/explorer and old adapter agents;
- `opencode-mcp-triage`;
- direct `codegraph` and `gitlab` registrations managed by the old/Harr stack;
- old workflow-wide tool/permission overrides;
- old workflow commands (`quick`, `safe`, `review`, `validate`, `build-*`).

It preserves unrelated providers, plugins, MCPs, agents and third-party skill directories. The old `opencode-workflow` repository itself is not used by Harr and may be removed independently.

### Codex MCP registration

Codex uses `${CODEX_HOME:-~/.codex}/config.toml`. Harr owns only this entry:

```toml
[mcp_servers.lean-ctx]
command = "/home/<user>/.local/bin/lean-ctx"
enabled = true
```

The absolute launcher path is intentional: desktop/IDE hosts do not have to inherit `~/.local/bin` in `PATH`.

When a `codex` CLI is available, Harr uses the official writer equivalent to:

```bash
codex mcp add lean-ctx -- ~/.local/bin/lean-ctx
```

The Codex CLI loads the existing MCP registry, replaces/adds only `lean-ctx`, and preserves the other configured MCP servers. If the host does not expose a `codex` CLI in `PATH`, Harr uses a narrow TOML fallback that rewrites only the `mcp_servers.lean-ctx` table and validates the complete resulting file with Python `tomllib`.

All unrelated Codex settings and MCPs remain in place. The entire pre-Harr `config.toml` is part of the clean rollback snapshot.

## Rollback / uninstall

```bash
harr uninstall
```

or from the repository:

```bash
./uninstall.sh
```

Before rollback Harr saves the current Harr state under:

```text
~/.local/share/harr-uninstall-backups/<timestamp>/
```

Then it restores the exact pre-Harr global snapshot, removes paths Harr created when they did not previously exist, disables its service, and leaves every project untouched.

## Compact AI routing policy

The source of truth is one small template:

```text
linux/files/policy/tool-routing.template.md
```

Host adapters provide only host-specific tool ids/behavior:

```text
linux/files/hosts/codex.env
linux/files/hosts/opencode.env
```

The permanent policy keeps the original token-saving OpenCode rules:

- MCP for investigation; native host editor for edits;
- cross-file structure/flow/relationships/dependencies/architecture/impact -> **CodeGraph first**;
- CodeGraph calls sequentially; returned source counts as already read;
- missing exact evidence -> narrow LeanCTX read/search/glob/shell;
- all Git repository/local/remote operations -> exact `git ...` commands through `ctx_shell`;
- GitLab API data -> `gitlab` through the gateway;
- uncommon LeanCTX capabilities -> `ctx_call`;
- no broad repository inventory after CodeGraph;
- no duplicate gateway/direct investigation;
- build/test only on explicit request.

OpenCode gets `lean-ctx_ctx_*` ids and keeps the stricter `Do not use native read/grep/glob/bash` host rule. Codex gets bare `ctx_*` ids and allows native equivalents only as narrow fallback.

The generated policy is the **entire Harr-owned global AGENTS file**, not a block merged into old rules.

```bash
harr agents apply
harr agents status
```

## Diagnostic skills

`harr` and `lean-ctx` skills are diagnostic/reference material, not the normal routing prompt. Their descriptions explicitly discourage loading them for ordinary repository work.

```text
~/.codex/skills/{harr,lean-ctx}/
~/.config/opencode/skills/{harr,lean-ctx}/
```

Other skill directories are untouched.

## CodeGraph project binding

CodeGraph deliberately stays stdio behind LeanCTX:

```toml
[[gateway.servers]]
name = "codegraph"
transport = "stdio"
enabled = true
command = "codegraph"
args = ["serve", "--mcp"]
url = ""
```

LeanCTX does not override the child working directory, so CodeGraph inherits the current agent/LeanCTX cwd and resolves the project-local `.codegraph` index. No Harr file or machine-global project root is required per repository.

If the wrong project is resolved, fix the host/LeanCTX cwd rather than adding per-project Harr configuration.

## Git

Git is intentionally **not** a Harr MCP component. Use exact `git ...` commands through LeanCTX `ctx_shell` for local repository state/history/branches as well as remote `fetch`/`pull`/`push` operations. GitLab MCP is reserved for GitLab API data such as merge requests, pipelines, jobs, issues and project/server metadata.

## GitLab

GitLab MCP is a long-lived Harr user service at:

```text
http://127.0.0.1:3334/mcp
```

Harr exposes the full GitLab tool catalog behind LeanCTX:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

The PAT is stored only locally at:

```text
~/.config/harr/secrets/gitlab-pat
```

with mode `0600`; the Harr LeanCTX wrapper supplies it through LeanCTX secret-memento handling.

```bash
harr secret set gitlab
harr secret status
harr secret unset gitlab
```

## Commands

```bash
harr status
harr hosts status
harr agents status
harr leanctx status

harr install all
harr install leanctx
harr install mcp

harr mcp list
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab -f

harr uninstall
```

The installer enables the GitLab user service but does not start/restart it unless `--start` is supplied. This avoids colliding with a foreground MCP test process already using port `3334`.

## Installed layout

```text
~/.local/bin/harr
~/.local/bin/lean-ctx
~/.local/bin/codegraph
~/.local/libexec/harr/
  cli/
  hosts/
  leanctx/
  mcp/
  policy/
  skills/
  state/
  vendor/lean-ctx/3.9.15/lean-ctx
~/.local/share/harr/npm/
~/.local/share/harr-state/pre-harr/       # independent rollback state
~/.config/harr/
  runtime.env
  mcp/gitlab.env
  secrets/gitlab-pat
~/.config/lean-ctx/config.toml
~/.config/systemd/user/harr-mcp-gitlab.service

${CODEX_HOME:-~/.codex}/
  config.toml                 # Harr owns only mcp_servers.lean-ctx
  AGENTS.md
  skills/{harr,lean-ctx}/

${XDG_CONFIG_HOME:-~/.config}/opencode/
  opencode.jsonc
  AGENTS.md
  skills/{harr,lean-ctx}/
```
