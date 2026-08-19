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
      +-- future MCPs -----> common registry -> platform runtime adapter

Unrelated third-party MCPs/skills may coexist beside this stack.
```

Direct Harr-managed CodeGraph/GitLab registrations are not part of the normal profile; they are diagnostic/on-demand bypasses only.

Platform-independent Harr assets have one source of truth under `common/`. In particular, `common/mcp/registry.json` declares Harr-managed downstream MCP transport, lifecycle, runtime/package, local env template and secret-memento routing. Linux and Windows consume that same registry; `linux/` and `windows/` contain platform-specific installation/lifecycle/path glue. `macos/` reserves the same boundary for a future launchd implementation; macOS installation is not implemented yet.



## Quickstart

Linux fresh install:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean --start
```

Windows fresh install from PowerShell:

```powershell
git clone https://github.com/smollgreymouse/harr.git
cd harr
.\install.ps1 -Clean -Start
```

If local PowerShell policy blocks scripts, use a process-local bypass rather than changing the machine policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Clean -Start
```

Configure the GitLab PAT once:

```text
harr secret set gitlab
```

Check the whole harness:

```text
harr status
```

Expected normal routing after restarting/reopening Codex or OpenCode:

```text
Codex / OpenCode -> LeanCTX
                    +-> CodeGraph   (stdio, per-project cwd)
                    +-> GitLab MCP  (HTTP, Harr-managed user process)
```

For later Harr updates:

```bash
# Linux
cd harr
git pull
./install.sh
```

```powershell
# Windows
cd harr
git pull
.\install.ps1
```

Rollback the entire global Harr takeover:

```text
harr uninstall
```

If a foreground test instance of a service MCP is already using its configured endpoint, stop it before the first start on either platform.



## Installation and lifecycle

### First install

Linux:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean
```

Windows:

```powershell
git clone https://github.com/smollgreymouse/harr.git
cd harr
.\install.ps1 -Clean
```

The clean flag is required for the first takeover. Before writing global state, Harr snapshots the existing global harness.

Linux snapshot:

```text
~/.local/share/harr-state/pre-harr/
```

Windows snapshot:

```text
%LOCALAPPDATA%\HarrState\pre-harr\
```

The Windows snapshot also records the pre-Harr user `PATH` and any scheduled-task names that the current MCP registry will own. When a later Harr version adds a new service MCP, the original snapshot is extended for that new task name **before** Harr registers it. Existing snapshot entries are never replaced.

Useful modes:

```bash
# Linux
./install.sh --clean --start
./install.sh --harr-only
```

```powershell
# Windows
.\install.ps1 -Clean -Start
.\install.ps1 -HarrOnly
```

The installers are user-level; do not run the Linux installer with `sudo` and do not require an elevated Windows shell.



### What clean takeover owns

Harr owns and regenerates:

- global Codex `AGENTS.md`, Harr/LeanCTX diagnostic skills, and the Harr-owned `mcp_servers.lean-ctx` entry in `config.toml`;
- global OpenCode `AGENTS.md`, Harr/LeanCTX diagnostic skills, and the active global OpenCode harness config;
- Harr LeanCTX binary/wrapper/config;
- Harr CodeGraph convenience launcher and private runtime package;
- registry-defined MCP lifecycle/config/secret handling;
- Harr-private runtime/state directories.

Harr does **not** touch project-level `AGENTS.md`, `.opencode`, skills, CodeGraph indexes, or other repository files.

The shared sources for platform-independent parts are:

```text
common/
  hosts/
  leanctx/
  mcp/
    registry.json
    manager.py
  policy/
  skills/
```

An ordinary new MCP is added to the registry plus any shared env/docs/policy material it needs. Platform installers are not edited unless the MCP genuinely requires platform-specific behavior.


### Rollback / uninstall

```text
harr uninstall
```

or from the repository:

```bash
# Linux
./uninstall.sh
```

```powershell
# Windows
.\uninstall.ps1
```

Before rollback Harr saves the current Harr state under:

```text
Linux:   ~/.local/share/harr-uninstall-backups/<timestamp>/
Windows: %LOCALAPPDATA%\HarrUninstallBackups\<timestamp>\
```

Then it restores the exact pre-Harr global snapshot, removes paths Harr created when they did not previously exist, disables/removes registry-owned platform lifecycle resources, and leaves every project untouched.



### Installed layout

Linux:

```text
~/.local/bin/
  harr
  lean-ctx
  codegraph
  harr-mcp-run

~/.local/libexec/harr/
  common/                       # installed copy of common/
  cli/                          # Linux CLI adapter
  leanctx/                      # Linux launcher adapter
  state/
  vendor/lean-ctx/3.9.15/lean-ctx

~/.local/share/harr/npm/
~/.local/share/harr-state/pre-harr/
~/.config/harr/
  runtime.env
  mcp/*.env
  secrets/*
~/.config/lean-ctx/config.toml
~/.config/systemd/user/harr-mcp@.service

${CODEX_HOME:-~/.codex}/
  config.toml                 # Harr owns only mcp_servers.lean-ctx
  AGENTS.md
  skills/{harr,lean-ctx}/

${XDG_CONFIG_HOME:-~/.config}/opencode/
  opencode.jsonc
  AGENTS.md
  skills/{harr,lean-ctx}/
```

Windows:

```text
%LOCALAPPDATA%\Harr\
  bin\{harr.cmd,lean-ctx.cmd,codegraph.cmd,harr-mcp-run.cmd}
  libexec\
    common\
    windows\
    vendor\lean-ctx\3.9.15\lean-ctx.exe
  share\npm\
  logs\<service-mcp>.log

%LOCALAPPDATA%\HarrState\pre-harr\
%USERPROFILE%\.config\harr\
  mcp\*.env
  secrets\*
%USERPROFILE%\.config\lean-ctx\config.toml

%USERPROFILE%\.codex\
  config.toml
  AGENTS.md
  skills\{harr,lean-ctx}\

%USERPROFILE%\.config\opencode\
  opencode.jsonc
  AGENTS.md
  skills\{harr,lean-ctx}\
```

The Windows installer adds `%LOCALAPPDATA%\Harr\bin` to the **user** `PATH`. Registry entries with `lifecycle = service` are mapped to non-elevated per-user logon Scheduled Tasks; Linux maps the same entries to instances of `harr-mcp@.service`.



## Commands

```text
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
harr mcp logs gitlab

harr secret status
harr secret set gitlab
harr secret unset gitlab

harr uninstall
```

`harr mcp list` includes both on-demand and service entries. Lifecycle commands apply only to registry entries with `lifecycle = service`; on-demand stdio MCPs are spawned by LeanCTX when called.

The Linux installer enables every registry service MCP through the generic `systemd --user` template but does not start/restart them unless `--start` is supplied. The Windows installer registers their per-user logon tasks and starts/restarts them only when `-Start` is supplied.



## MCP and tool infrastructure

### MCP registry

`common/mcp/registry.json` is the extension point for Harr-managed MCPs. The common manager generates the downstream LeanCTX server blocks, npm package set, local env files, component status and secret-memento wiring from this registry.

Supported registry patterns are intentionally small:

```text
transport:  stdio | http
lifecycle:  on-demand | service
runtime:    npm package | command already available in PATH
secret:     LeanCTX secret_env | secret_headers
```

Platform adapters implement only what differs by OS: executable paths, process/service lifecycle and rollback ownership. This keeps an MCP declaration shared instead of repeating it in every installer.


### Codex MCP registration

Codex uses `${CODEX_HOME:-~/.codex}/config.toml` on Linux. On Windows it uses `%CODEX_HOME%` when explicitly set and otherwise `%USERPROFILE%\.codex\config.toml`.

Harr owns only the `lean-ctx` MCP registration. Its command is an absolute launcher path:

```text
Linux:   ~/.local/bin/lean-ctx
Windows: %LOCALAPPDATA%\Harr\bin\lean-ctx.cmd
```

The absolute launcher path is intentional: desktop/IDE hosts do not have to inherit Harr's bin directory in `PATH`.

Harr also sets `default_tools_approval_mode = "auto"` on this trusted local LeanCTX MCP entry, avoiding per-call approval prompts for Harr's compact `ctx_*` surface. The shared Codex writer restores that setting after the official `codex mcp add` writer if necessary.

When a `codex` CLI is available, Harr uses the official MCP writer. If the host does not expose a `codex` CLI, the shared `common/hosts/codex-config.py` uses a narrow TOML fallback that rewrites only the `mcp_servers.lean-ctx` table and validates the complete resulting file with Python `tomllib`.

All unrelated Codex settings and MCPs remain in place. The entire pre-Harr `config.toml` is part of the clean rollback snapshot.

OpenCode uses the shared `common/hosts/opencode-config.py`; its global config is `~/.config/opencode/opencode.jsonc` on Linux and `%USERPROFILE%\.config\opencode\opencode.jsonc` on Windows unless `XDG_CONFIG_HOME` is explicitly set. Harr removes only retired/Harr-owned workflow pieces and preserves unrelated providers, plugins, MCPs and agents.



### CodeGraph project binding

CodeGraph is declared as an on-demand stdio MCP in the common registry. The generated LeanCTX entry uses the generic runner, which starts the pinned CodeGraph runtime with `serve --mcp` while preserving the agent/LeanCTX working directory. CodeGraph therefore resolves the project-local `.codegraph` index without a machine-global project root.

The separate `codegraph` launcher remains installed for manual commands such as project initialization and status. If the wrong project is resolved, fix the host/LeanCTX cwd rather than adding per-project Harr configuration.



### GitLab

GitLab is declared as an HTTP service MCP in the common registry and exposed to LeanCTX at:

```text
http://127.0.0.1:3334/mcp
```

Its lifecycle adapter is platform-specific:

```text
Linux:   systemd --user instance: harr-mcp@gitlab.service
Windows: per-user Scheduled Task
```

Harr exposes the full GitLab tool catalog behind LeanCTX:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

The PAT is stored only locally under the Harr config root; the Harr LeanCTX wrapper supplies it through registry-defined LeanCTX secret-memento handling.

Linux path:

```text
~/.config/harr/secrets/gitlab-pat
```

Windows path:

```text
%USERPROFILE%\.config\harr\secrets\gitlab-pat
```

```text
harr secret set gitlab
harr secret status
harr secret unset gitlab
```



### Git

Git is intentionally **not** a Harr MCP component. Use exact `git ...` commands through LeanCTX `ctx_shell` for local repository state/history/branches as well as remote `fetch`/`pull`/`push` operations. GitLab MCP is reserved for GitLab API data such as merge requests, pipelines, jobs, issues and project/server metadata.



## Compact usage rules

The source of truth is one small platform-independent template:

```text
common/policy/tool-routing.template.md
```

Host adapters provide only host-specific tool ids/behavior:

```text
common/hosts/codex.env
common/hosts/opencode.env
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

```text
harr agents apply
harr agents status
```



## Diagnostic skills

`harr` and `lean-ctx` skills are diagnostic/reference material, not the normal routing prompt. Their descriptions explicitly discourage loading them for ordinary repository work.

Shared sources:

```text
common/skills/{harr,lean-ctx}/
```

They are installed globally for both Codex and OpenCode. Other skill directories are untouched.



## Token-economy benchmark

The reproducible A/B record is in [benchmarks/token-economy](benchmarks/token-economy/README.md).
It counts saved payloads with `tiktoken` 0.8.0 and the `o200k_base` encoding;
these are comparable payload counts, not provider billing telemetry or cached-token usage.

| Measurement | Native/direct | Harr/LeanCTX | Difference |
| --- | ---: | ---: | ---: |
| Persistent MCP tool catalog | 39,873 tokens / 216 tools | 1,328 tokens / 6 core tools | 38,545 fewer / 96.7% |
| Exact installer source read | 1,934 | 2,501 | 567 more / 29.3% |
| Installer symbol search | 490 | 271 | 219 fewer / 44.7% |
| Broad audit final prose | 3,089 | 3,443 | 354 more / 11.5% |

The large context saving comes from the small LeanCTX gateway surface, while
individual calls can legitimately be larger when the gateway preserves source
and adds evidence. The broad audit used a warm CodeGraph index and differs in
language and response structure, so its final-prose delta is not attributable
solely to Harr. The saved prompts, raw counts, reproduction command, and
methodological limitations are in the benchmark directory.
