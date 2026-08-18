# Harr

Harr is a local harness for MCP/context-engineering infrastructure.

The name is both an Odin reference and a phonetic joke on “harness”.

## Goal

Keep the normal agent tool surface small. The agent sees LeanCTX; specialized MCPs stay behind the LeanCTX gateway and are discovered/called only when needed.

```text
Codex / OpenCode
      |
      | normal MCP surface: LeanCTX only
      v
LeanCTX 3.9.15
      |
      +-- stdio -----------> CodeGraph 1.5.0
      |                     inherits LeanCTX cwd
      |
      +-- HTTP :3334 -----> GitLab MCP 2.1.48 -> GitLab API
      |
      +-- future MCPs ----> hidden behind the same gateway
```

Direct registrations of CodeGraph/Git/GitLab may be useful as temporary diagnostics, but must not remain in the normal profile because their tool schemas defeat the context-saving purpose of the gateway.

## Managed stack

- LeanCTX `3.9.15` — pinned MCP gateway;
- `@zereight/mcp-gitlab` `2.1.48` — long-lived Streamable HTTP user service at `127.0.0.1:3334/mcp`;
- CodeGraph `1.5.0` — installed by Harr, spawned by LeanCTX over stdio per agent/repository;
- compact host-specific tool-routing policy for Codex and OpenCode;
- diagnostic-only `harr` and `lean-ctx` skills.

## Install

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh
```

The installer is user-level; do not use `sudo`. It installs the pinned stack and applies the agent policy, but does not start/restart GitLab MCP automatically to avoid colliding with a foreground test process on port `3334`.

After stopping any foreground GitLab MCP process:

```bash
harr mcp start gitlab
harr status
```

Useful installer modes:

```bash
./install.sh --start      # install and restart long-lived MCP services
./install.sh --harr-only  # update Harr + agent policy/skills only
```

## Compact agent policy

The source of truth is one template:

```text
linux/files/policy/tool-routing.template.md
```

Host adapters contain only LeanCTX tool ids:

```text
linux/files/hosts/codex.env
linux/files/hosts/opencode.env
```

For example, Codex uses `ctx_tools`; OpenCode uses `lean-ctx_ctx_tools`. Harr renders the same policy with the correct host ids.

The permanent policy is intentionally small and is based on the OpenCode routing policy developed for this setup:

- MCP for investigation; native host editor for edits;
- normal MCP surface: LeanCTX only;
- cross-file structure/flow/relationships/dependencies/architecture/impact -> **CodeGraph first**;
- CodeGraph calls sequentially; returned source counts as already read;
- unresolved exact evidence -> narrowly targeted LeanCTX read/search/glob/shell;
- Git operations -> `git-mcp` through the gateway when configured;
- GitLab API data -> `gitlab` through the gateway;
- uncommon LeanCTX capabilities -> `ctx_call`;
- no broad repository inventory after CodeGraph and no duplicate direct+gateway investigation;
- build/test only on explicit request.

Harr injects only its marked block into existing global rules:

```text
~/.codex/AGENTS.md
~/.config/opencode/AGENTS.md
```

Markers:

```text
<!-- harr-tool-policy:start -->
...
<!-- harr-tool-policy:end -->
```

Everything outside that block remains user-owned. The first pre-Harr version of each global AGENTS file is backed up under:

```text
~/.local/libexec/harr/backup/agents/
```

Apply/check policy and diagnostic skills:

```bash
harr agents apply
harr agents apply codex
harr agents apply opencode
harr agents status
```

`harr install all` and `harr install leanctx` also re-apply the agent policy.

## Diagnostic skills

The installed `harr` and `lean-ctx` skills are **not** the normal routing prompt. Their descriptions explicitly restrict them to stack/component diagnostics so ordinary coding tasks do not load them unnecessarily.

```text
~/.codex/skills/{harr,lean-ctx}/
~/.config/opencode/skills/{harr,lean-ctx}/
```

Harr copies each whole skill directory, including lazy `references/` files. References should be loaded only when diagnosing the relevant component.

## Why CodeGraph stays stdio

LeanCTX spawns downstream stdio servers without overriding the child working directory. CodeGraph therefore inherits the agent/LeanCTX cwd and can resolve the nearest project-local `.codegraph` index without a Harr config file in every repository.

LeanCTX config:

```toml
[[gateway.servers]]
name = "codegraph"
transport = "stdio"
enabled = true
command = "codegraph"
args = ["serve", "--mcp"]
url = ""
```

If CodeGraph resolves the wrong project, fix the agent/LeanCTX cwd. Do not introduce a machine-global project root or per-project Harr config as a workaround.

## GitLab

GitLab MCP is a long-lived Harr user service because its native Streamable HTTP path is stable for this setup:

```text
http://127.0.0.1:3334/mcp
```

Harr exposes the complete GitLab MCP tool surface behind the gateway:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

The PAT is not stored in Git or LeanCTX TOML. It lives locally at:

```text
~/.config/harr/secrets/gitlab-pat
```

with mode `0600`. Harr's `lean-ctx` wrapper restores it through LeanCTX secret-memento handling.

```bash
harr secret set gitlab
harr secret status
harr secret unset gitlab
```

## Commands

Components:

```bash
harr install all
harr install leanctx
harr install mcp
```

Long-lived MCP services:

```bash
harr mcp list
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab -f
```

LeanCTX:

```bash
harr leanctx apply
harr leanctx status
```

Everything together:

```bash
harr status
```

## Installed layout

```text
~/.local/bin/harr
~/.local/bin/lean-ctx
~/.local/bin/codegraph
~/.local/libexec/harr/
  cli/
  mcp/
  leanctx/
  policy/
  hosts/
  skills/
  vendor/lean-ctx/3.9.15/lean-ctx
~/.local/share/harr/npm/
~/.config/harr/
  runtime.env
  mcp/gitlab.env
  secrets/gitlab-pat
~/.config/lean-ctx/config.toml
~/.config/systemd/user/harr-mcp-gitlab.service
```
