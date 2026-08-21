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
      | Harr-managed route
      v
LeanCTX 3.9.15                         required
      |
      +-- stdio -----------> CodeGraph 1.5.0       required
      |                     inherits LeanCTX cwd
      |
      +-- HTTP :3334 -----> GitLab MCP 2.1.48     optional
      |
      +-- stdio -----------> Grafana MCP           optional
      |                     uvx mcp-grafana
      |
      +-- future MCPs -----> common registry       required/optional metadata

Unrelated third-party MCPs/skills may coexist beside this stack.
```

LeanCTX and CodeGraph are the fixed Harr baseline. Every other Harr MCP is selectable. A fresh interactive install starts optional MCPs unchecked; the saved choice is reused by later updates.

Direct Harr-managed specialized MCP registrations are not part of the normal host profile; they stay behind LeanCTX.

Platform-independent Harr assets have one source of truth under `common/`. `common/mcp/registry.json` is the **full MCP catalog** and declares transport, lifecycle, runtime/package, required/optional status, local env template, secret-memento routing, labels/descriptions and optional skill references. Linux, macOS and Windows consume that same catalog; their platform directories contain only installation/lifecycle/path glue.

The user choice is stored separately from the catalog:

```text
~/.config/harr/mcp-selection.json    # Windows: %USERPROFILE%\.config\harr\...
~/.config/harr/mcp-registry.json     # generated effective registry
```

The effective registry is the single source for the active LeanCTX gateway, runtime packages, secrets/status, service lifecycle, global routing policy and installed Harr skill/reference set. Disabling an MCP preserves its existing env/secret files so it can be re-enabled without re-entering configuration.



## Quickstart

### Linux

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean --start
```

### macOS

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean --start
```

### Windows

```powershell
git clone https://github.com/smollgreymouse/harr.git
cd harr
.\install.ps1 -Clean -Start
```

On the first interactive install all three platforms show the same selector:

```text
Harr components

  [x] LeanCTX      required  compact MCP gateway
  [x] CodeGraph    required  cross-file code structure and impact analysis
> [ ] GitLab       optional  GitLab API, merge requests, pipelines and issues
  [ ] Grafana      optional  Grafana dashboards and datasources

Up/Down move   Space toggle   Enter apply   Esc cancel
```

LeanCTX and CodeGraph cannot be deselected.

For a completely silent **full** install:

```bash
# Linux / macOS
./install.sh --clean --all --start
```

```powershell
# Windows
.\install.ps1 -Clean -All -Start
```

For a deterministic required-only install:

```bash
# Linux / macOS
./install.sh --clean --mcp none
```

```powershell
# Windows
.\install.ps1 -Clean -Mcp none
```

For an exact optional set, list only the optional MCP names; required components are added automatically:

```bash
# Linux / macOS
./install.sh --clean --mcp gitlab,grafana
```

```powershell
# Windows
.\install.ps1 -Clean -Mcp gitlab,grafana
```

If local PowerShell policy blocks scripts, use a process-local bypass rather than changing the machine policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Clean -Start
```

Configure secrets only for MCPs you enabled:

```text
harr secret set gitlab
harr secret set grafana
```

Grafana also requires `uvx` in `PATH`; Harr uses it on demand and does not globally install `mcp-grafana`.

Check the whole harness:

```text
harr status
```

Typical required-only routing after restarting/reopening Codex or OpenCode:

```text
Codex / OpenCode -> LeanCTX -> CodeGraph
```

With optional MCPs selected they appear behind the same LeanCTX gateway.

For later Harr updates, the saved MCP choice is reused without prompting:

```bash
# Linux / macOS
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

Change the selection later with:

```text
harr mcp configure
```

Rollback the entire global Harr takeover:

```text
harr uninstall
```

If a foreground test instance of a selected service MCP is already using its configured endpoint, stop it before the first start.



## Installation and lifecycle

### First install

Linux:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean
```

macOS:

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

The clean flag is required for the first takeover. Before writing global state or the MCP selection, Harr snapshots the existing global harness. `--clean` / `-Clean` initializes or preserves Harr's rollback ownership snapshot; it does **not** reset an existing Harr MCP selection or other Harr configuration.

Linux/macOS snapshot:

```text
~/.local/share/harr-state/pre-harr/
```

Windows snapshot:

```text
%LOCALAPPDATA%\HarrState\pre-harr\
```

The Windows snapshot also records the pre-Harr user `PATH`, MCP selection/effective-registry paths and scheduled-task names that the full MCP catalog may own. When a later Harr version adds a new managed path or service MCP, the original snapshot is extended for that new ownership target **before** Harr modifies it. Existing snapshot entries are never replaced.

Fresh interactive install defaults to the required baseline. If stdin/stdout is not a TTY, Harr keeps that required-only default instead of failing. Use `--all`/`-All` or `--mcp`/`-Mcp` for deterministic automation.

An installation made before MCP selection existed has no saved selection. On its first update to the selection-aware Harr, the migration default is **all**, preserving the MCPs that older Harr versions installed unconditionally. After that, normal updates reuse the saved choice silently. Newly introduced optional MCPs remain disabled until selected; newly introduced required components are added automatically.

Useful modes:

```bash
# Linux / macOS
./install.sh --clean --start
./install.sh --clean --all --start
./install.sh --clean --mcp none
./install.sh --configure-mcp
./install.sh --harr-only
```

```powershell
# Windows
.\install.ps1 -Clean -Start
.\install.ps1 -Clean -All -Start
.\install.ps1 -Clean -Mcp none
.\install.ps1 -ConfigureMcp
.\install.ps1 -HarrOnly
```

The installers are user-level; do not run the Linux/macOS installer with `sudo` and do not require an elevated Windows shell.

`--start` / `-Start` starts or restarts only the **enabled service MCPs**. On-demand MCPs are spawned through LeanCTX when called.



### What clean takeover owns

Harr owns and regenerates:

- global Codex `AGENTS.md`, Harr/LeanCTX diagnostic skills, and the Harr-owned `mcp_servers.lean-ctx` entry in `config.toml`;
- global OpenCode `AGENTS.md`, Harr/LeanCTX diagnostic skills, and the active global OpenCode harness config;
- Harr LeanCTX binary/wrapper/config;
- Harr CodeGraph convenience launcher and private runtime package;
- the saved MCP selection and generated effective registry;
- registry-defined MCP lifecycle/config/secret handling;
- Harr-private runtime/state directories.

Harr does **not** touch project-level `AGENTS.md`, `.opencode`, skills, CodeGraph indexes, or other repository files.

The shared sources for platform-independent parts are:

```text
common/
  hosts/
  leanctx/
  mcp/
    registry.json      # full catalog / extension point
    manager.py         # runtime/config rendering
    selector.py        # shared terminal selector + effective registry
    assets.py          # MCP-aware policy/skill rendering
  policy/
  shell/
  skills/
```

An ordinary new MCP is added to the registry plus any shared env/docs/policy material it needs. Platform installers are not edited unless the MCP genuinely requires platform-specific behavior.


### Rollback / uninstall

```text
harr uninstall
```

or from the repository:

```bash
# Linux / macOS
./uninstall.sh
```

```powershell
# Windows
.\uninstall.ps1
```

Before rollback Harr saves the current Harr state under:

```text
Linux/macOS: ~/.local/share/harr-uninstall-backups/<timestamp>/
Windows:     %LOCALAPPDATA%\HarrUninstallBackups\<timestamp>\
```

Then it restores the exact pre-Harr global snapshot, removes paths Harr created when they did not previously exist, disables/removes catalog-owned platform lifecycle resources, and leaves every project untouched.



### Installed layout

Linux:

```text
~/.local/bin/
  harr
  lean-ctx
  codegraph
  harr-mcp-run

~/.local/libexec/harr/
  common/
  cli/
  leanctx/
  state/
  vendor/lean-ctx/3.9.15/lean-ctx

~/.local/share/harr/npm/
~/.local/share/harr-state/pre-harr/
~/.config/harr/
  mcp-selection.json
  mcp-registry.json
  runtime.env
  mcp/*.env
  secrets/*
~/.config/lean-ctx/config.toml
~/.config/systemd/user/harr-mcp@.service

${CODEX_HOME:-~/.codex}/
  config.toml
  AGENTS.md
  skills/{harr,lean-ctx}/

${XDG_CONFIG_HOME:-~/.config}/opencode/
  opencode.jsonc
  AGENTS.md
  skills/{harr,lean-ctx}/
```

macOS:

```text
~/.local/bin/
  harr
  lean-ctx
  codegraph
  harr-mcp-run

~/.local/libexec/harr/
  common/
  cli/
  leanctx/
  state/
  vendor/lean-ctx/3.9.15/lean-ctx

~/.config/harr/
  mcp-selection.json
  mcp-registry.json
  runtime.env
  mcp/*.env
  secrets/*
~/.config/lean-ctx/config.toml
~/Library/LaunchAgents/com.harr.mcp.<name>.plist
~/Library/Logs/Harr/<name>.{out,err}.log
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
  mcp-selection.json
  mcp-registry.json
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

The Windows installer adds `%LOCALAPPDATA%\Harr\bin` to the **user** `PATH`. Enabled registry entries with `lifecycle = service` map to non-elevated per-user logon Scheduled Tasks; Linux maps them to `harr-mcp@<name>.service`; macOS maps them to per-user LaunchAgents. Disabled service MCP lifecycle resources are stopped/removed from the active Harr configuration.



## Commands

```text
harr status
harr hosts status
harr agents status
harr leanctx status

harr install all
harr install leanctx
harr install mcp

harr mcp available
harr mcp list
harr mcp configure
harr mcp configure none
harr mcp configure all
harr mcp configure gitlab,grafana

harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab

harr secret status
harr secret set gitlab
harr secret set grafana
harr secret unset gitlab
harr secret unset grafana

harr uninstall
```

`harr mcp available` shows the full catalog and whether each entry is required/optional and enabled/disabled. `harr mcp list` lists the currently enabled downstream MCPs. `harr mcp configure` opens the same cross-platform checklist used by first install; its optional argument applies a non-interactive exact set.

Lifecycle commands apply only to **enabled** registry entries with `lifecycle = service`; on-demand stdio MCPs such as CodeGraph and an enabled Grafana are spawned by LeanCTX when called.

Changing the selection reapplies the effective registry, selected runtime package set, LeanCTX gateway, lifecycle registration, global policy and Harr diagnostic skill. Existing env/secret files for disabled MCPs are deliberately preserved.



## MCP and tool infrastructure

### MCP registry

`common/mcp/registry.json` is the full extension-point catalog for Harr-managed MCPs. The shared selector writes the chosen subset to the generated effective registry. The common manager then generates downstream LeanCTX server blocks, npm package set, local env files, component status and secret-memento wiring from **that selected subset**.

Useful registry metadata is intentionally small:

```text
required:   true | false
label:      short selector label
description: selector/help description
transport:  stdio | http
lifecycle:  on-demand | service
runtime:    npm package | command already available in PATH
secret:     LeanCTX secret_env | secret_headers
skill_reference: optional Harr diagnostic reference owned by that MCP
```

Platform adapters implement only what differs by OS: executable paths, process/service lifecycle and rollback ownership. This keeps an MCP declaration shared instead of repeating it in every installer.

A new ordinary optional MCP therefore appears automatically in the selector after updating Harr and stays disabled until chosen. A required MCP is automatically included and cannot be toggled off.


### Codex MCP registration

Codex uses `${CODEX_HOME:-~/.codex}/config.toml` on Linux/macOS. On Windows it uses `%CODEX_HOME%` when explicitly set and otherwise `%USERPROFILE%\.codex\config.toml`.

Harr owns only the `lean-ctx` MCP registration. Its command is an absolute launcher path:

```text
Linux/macOS: ~/.local/bin/lean-ctx
Windows:     %LOCALAPPDATA%\Harr\bin\lean-ctx.cmd
```

The absolute launcher path is intentional: desktop/IDE hosts do not have to inherit Harr's bin directory in `PATH`.

Harr keeps the server default at `default_tools_approval_mode = "auto"`, but explicitly sets `approval_mode = "approve"` for Harr's normal trusted investigation surface: `ctx_read`, `ctx_search`, `ctx_glob`, `ctx_shell` and `ctx_tools`. `ctx_call` remains on `auto` as the uncommon-capability escape hatch. The shared Codex writer restores these settings after the official `codex mcp add` writer if necessary.

When a `codex` CLI is available, Harr uses the official MCP writer. If the host does not expose a `codex` CLI, the shared `common/hosts/codex-config.py` uses a narrow TOML fallback that rewrites only the `mcp_servers.lean-ctx` table and validates the complete resulting file with Python `tomllib`.

All unrelated Codex settings and MCPs remain in place. The entire pre-Harr `config.toml` is part of the clean rollback snapshot.

OpenCode uses the shared `common/hosts/opencode-config.py`; its global config is `${XDG_CONFIG_HOME:-~/.config}/opencode/opencode.jsonc` on Linux/macOS and `%USERPROFILE%\.config\opencode\opencode.jsonc` on Windows unless `XDG_CONFIG_HOME` is explicitly set. Harr removes only retired/Harr-owned workflow pieces and preserves unrelated providers, plugins, MCPs and agents.



### CodeGraph project binding

CodeGraph is the required downstream MCP. It is declared as an on-demand stdio MCP in the common registry. The generated LeanCTX entry uses the generic runner, which starts the pinned CodeGraph runtime with `serve --mcp` while preserving the agent/LeanCTX working directory. CodeGraph therefore resolves the project-local `.codegraph` index without a machine-global project root.

The separate `codegraph` launcher remains installed for manual commands such as project initialization and status. If the wrong project is resolved, fix the host/LeanCTX cwd rather than adding per-project Harr configuration.



### GitLab

GitLab is **optional**. Enable it during install or later with:

```text
harr mcp configure gitlab
```

If other optional MCPs are already enabled, include them in the exact set as well, or use the interactive `harr mcp configure` checklist.

GitLab is declared as an HTTP service MCP in the common registry and exposed to LeanCTX at:

```text
http://127.0.0.1:3334/mcp
```

Its lifecycle adapter is platform-specific:

```text
Linux:   systemd --user instance: harr-mcp@gitlab.service
macOS:   ~/Library/LaunchAgents/com.harr.mcp.gitlab.plist
Windows: per-user Scheduled Task
```

Harr exposes the full GitLab tool catalog behind LeanCTX:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

LeanCTX gateway discovery is intentionally compact but not single-result: Harr uses `gateway.top_n = 3`. Discovery is ranked, so absence from one broad result is not proof that a GitLab capability is unavailable; write operations use verb-specific discovery such as `create GitLab merge request` -> `gitlab::create_merge_request`, with one refresh/retry before declaring an expected tool missing.

MR creation is treated as a combined Git + GitLab workflow. Harr policy expects the agent to derive the project/source branch from the current repository, prepare the local commit, discover MR/reviewer tools up front, publish the branch with ordinary `git push` through `ctx_shell`, and then create/verify the MR through GitLab MCP. A Git transport/authentication failure alone is not treated as proof that MR creation is impossible: when the local diff can be represented exactly through GitLab repository APIs, the documented fallback is to create the remote branch from the intended target, mirror the actual local diff (prefer a batched/single-commit operation such as `gitlab::push_files` when available), verify the remote branch diff, and only then create the MR. This fallback may produce different remote commit SHA(s) and must say so. Browser/curl/manual-token workarounds are not used while the enabled GitLab MCP can perform the operation.

Git commit author, GitLab MR author, assignee and reviewer are distinct. The MR author is the authenticated GitLab identity; requested assignees/reviewers are resolved to GitLab user IDs and verified on the resulting MR rather than assumed from a name.

The PAT is stored only locally under the Harr config root; the Harr LeanCTX wrapper supplies it through registry-defined LeanCTX secret-memento handling while GitLab is enabled.

```text
harr secret set gitlab
harr secret status
harr secret unset gitlab
```

Disabling GitLab removes it from the gateway, agent policy/skill and active service lifecycle, but preserves its local env/secret files.



### Grafana

Grafana is **optional** and declared as an on-demand stdio MCP. When enabled, the generated LeanCTX route is equivalent to:

```text
LeanCTX -> harr-mcp-run grafana -> uvx mcp-grafana
```

`uvx` must be available in `PATH` only when Grafana is selected/used. Harr creates the non-secret local config from `common/mcp/grafana.env.example`:

```text
GRAFANA_URL=http://localhost:3000
```

Edit the installed `mcp/grafana.env` for your self-hosted Grafana URL. Store the service-account token separately:

```text
harr secret set grafana
harr secret status
```

The registry maps that secret to `GRAFANA_SERVICE_ACCOUNT_TOKEN` through LeanCTX secret-memento handling while Grafana is enabled. The token must not be placed in `grafana.env`, LeanCTX configuration, or the repository. Harr does not pass `--disable-write`.

For dashboard edits, prefer the compact patch-first flow:

```text
search_dashboards
  -> get_dashboard_summary
  -> targeted property/panel-query reads
  -> update_dashboard
```

Fetch a complete dashboard definition only when the targeted tools are insufficient.



### Git

Git is intentionally **not** a Harr MCP component. Use exact `git ...` commands through LeanCTX `ctx_shell` for local repository state/history/branches as well as remote `fetch`/`pull`/`push` operations. If GitLab MCP is enabled, it handles GitLab API state and actions such as merge requests, pipelines, jobs, issues, users and project/server metadata; repository-file API operations are reserved for explicit/fallback workflows such as faithfully mirroring a local diff when ordinary Git transport is unavailable.



## Compact usage rules

The source of truth is one small platform-independent template:

```text
common/policy/tool-routing.template.md
```

Host adapters provide only host-specific tool ids/behavior:

```text
Codex:
  CTX_READ=ctx_read
  CTX_SHELL=ctx_shell
  CTX_SEARCH=ctx_search
  CTX_GLOB=ctx_glob
  CTX_TOOLS=ctx_tools
  CTX_CALL=ctx_call

OpenCode:
  CTX_READ=lean-ctx_ctx_read
  CTX_SHELL=lean-ctx_ctx_shell
  CTX_SEARCH=lean-ctx_ctx_search
  CTX_GLOB=lean-ctx_ctx_glob
  CTX_TOOLS=lean-ctx_ctx_tools
  CTX_CALL=lean-ctx_ctx_call
```

The compact global rules enforce:

- CodeGraph-first structural investigation;
- exact Git through `ctx_shell`;
- selected GitLab/Grafana operations through `ctx_tools`;
- verb-specific downstream tool discovery before declaring a write capability unavailable;
- native host editing;
- no duplicated direct/gateway MCP investigation;
- no project-level Harr configuration.

Disabled optional MCPs are removed from the generated policy, so an agent is not instructed to use a component the user did not select.



## Skills

Harr installs the same two diagnostic/operational skills globally for Codex and OpenCode:

```text
harr
lean-ctx
```

The Harr skill is rendered from the selected MCP set. Optional MCP-specific command blocks and reference files are present only while that MCP is enabled. Disabling GitLab or Grafana therefore removes its instructions from the installed Harr skill without deleting the user's local env/secret data.

The skills explain runtime topology, ownership, rollback, MCP selection and compact routing. They are not duplicated per platform except for platform-specific command/path details.



## Token-economy benchmark

The benchmark below is intentionally kept stable as a historical measurement of the compact LeanCTX/CodeGraph route versus direct MCP schema exposure. Selection-aware Harr keeps the same architectural goal: large specialized schemas stay behind LeanCTX and only the compact `ctx_*` surface remains permanent.

| Scenario | Direct tools | Direct tokens | Gateway tools | Gateway tokens |
| --- | ---: | ---: | ---: | ---: |
| Baseline host + CodeGraph | 32 | 6542 | 6 | 1342 |
| Baseline host + CodeGraph + GitLab | 59 | 14937 | 6 | 1342 |

Measured savings for the larger GitLab stack: **13,595 tokens** of permanent tool-schema context per request, before counting any further optional MCPs.
