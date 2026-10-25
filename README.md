<img src="harr.png" alt="Harr — Norse raven mascot" width="160" align="left">

# Harr

> *Herblindi ok Hár.*
>
> **Harr er reiði Hárs.**
>
> — *Grímnismál 46* / with apologies to the skalds

<br clear="all">

A global harness for token-efficient MCP infrastructure.

## Named Ein CLI workers (PR #39)

Harr manages any number of **user-named Ein MCP instances**. Every instance has a
fixed adapter (`gigacode`, `opencode`, `codex`, or a custom command-template)
with its own runtime state and configuration. Each publishes the **same**
`<mcp-name>::ein` tool and shared `$einherjar-worker` skill, preserving the
legacy GigaCode action and argument schema. The GigaCode adapter reuses its
established bridge for startup confirmation, lifecycle and Desktop progress.

At first interactive `harr setup`, choose **Configure named Ein workers**,
or manage them later:

```bash
harr ein configure
harr ein add --id opencode-builder --adapter opencode
harr ein add --id opencode-reviewer --adapter opencode
harr ein add --id gigacode --adapter gigacode
harr ein list
harr ein edit opencode-reviewer --display-name "Review worker"
harr ein test opencode-builder       # checks executable availability, no model calls
harr ein apply                       # publish gateway, skill/policy, named Desktop panels
```

`gigacode::ein`, `opencode-builder::ein` and `opencode-reviewer::ein`
are **distinct MCP servers**, not aliases to one global backend selector.
MCP names are entered explicitly at creation time and checked for collisions.
Use `harr ein disable NAME`, `enable NAME` or `remove NAME` to manage instances.

For an arbitrary CLI, use
`harr ein add --id NAME --adapter custom --definition-file custom.json`;
its `start`/`resume` commands must be JSON argv arrays (no shell expansion).
Optional `--executable PATH` overrides a built-in executable and
`--secret-env ENV=SECRET_FILE` references a file in Harr's private `secrets/`
directory without putting its contents into the instances config.
Configurations live under `~/.config/harr/einherjar/instances.json`.

The old static GigaCode MCP remains selectable until an instance named
`gigacode` is configured, at which point it is replaced by `gigacode::ein`.
All named instances share **one read-only Codex Desktop MCP App**,
`harr-ein-ui::show_ein_live`. The call supplies the user-chosen MCP instance
name and an existing Ein session UUID (it never launches a new model run), keeps `poll_ein_ui` and
`list_ein_ui` app-only, and uses per-instance session/history files. It also delivers a concise terminal `ui/message` once per running session, with the final handoff status and diagnostics; it does not send the raw JSON envelope into chat. This direct
MCP registration is distinct from the LeanCTX execution gateway.

No running global Harr or Codex installation is modified by this source PR.
See `docs/EINHERJAR_NAMED_INSTANCES_DESIGN.md` for migration and validation.

## Design

Harr is not merged into another global harness. On first installation it takes **clean ownership of its global layer**, after saving an exact rollback snapshot. Project-level configuration is deliberately out of scope.

Harr-managed specialized MCPs stay behind LeanCTX so their large schemas do not live permanently in the agent context. Unrelated third-party MCPs and skills may coexist globally.

```text
Codex / OpenCode
      |
      | Harr-managed route
      v
LeanCTX 3.11.0 Harr workspace build       required
      |
      +-- stdio -----------> CodeGraph 1.5.0       required
      |                     inherits LeanCTX cwd
      |
      +-- stdio -----------> GitLab MCP 2.1.48     optional
      |                     on-demand stdio
      |
      +-- stdio -----------> Grafana MCP           optional
      |                     on-demand uvx mcp-grafana
      |
      +-- stdio -----------> Kibana MCP            optional
      |                     read-only kibana-agent via Console proxy
      |
      +-- stdio -----------> GigaCode Executor     optional
      |                     bundled Harr bridge -> external gigacode CLI
      |
      +-- stdio on demand --> Jira MCP -> Jira REST API
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

Harr also owns LeanCTX Workspace state per project. For a Git checkout, the nearest `.git` root is the primary Workspace root; outside Git, the current directory is used. Persistent stores live under `~/.config/harr/workspaces/` and are selected automatically when Harr launches LeanCTX as MCP. Harr enables strict Workspace authority for those MCP launches; ordinary LeanCTX CLI commands such as `lean-ctx config validate` are not forced into Workspace mode.

Additional roots can be changed live without restarting Codex or the LeanCTX MCP process:

```bash
harr workspace show
harr workspace add ../shared-assets
harr workspace remove ../shared-assets
harr workspace sync /absolute/current/project /absolute/other/session-root
harr workspace list
```

`harr workspace sync PATH...` is an add-only helper for agent sessions: it canonicalizes the supplied working folders, skips the primary root, existing roots and duplicate inputs, and adds only the missing roots. On Linux, Harr installs the same `$harr-workspace` skill and direct `harr-workspace` control MCP for both Codex and OpenCode, so you can ask either client to "sync/add your working folders to Harr". The skill uses only workspace/root paths already known to that session; it does not scan `$HOME` or guess sibling repositories.

The CLI and the already-running MCP share the same revisioned Workspace store, so a successful add becomes visible to the next MCP request and a remove revokes access on the next request.

Codex Desktop also gets a direct **Harr Workspace** MCP App. Ask Codex to open/show the Harr Workspace panel (model-visible tool: `show_harr_workspace`). The panel shows the primary root, revision and additional roots, and performs Add/Remove/Refresh through app-only tools with revision/CAS protection. The current MVP accepts a path manually; it does not fake a filesystem picker, and adding a LeanCTX root does not grant Codex new OS/sandbox permissions. The CLI remains the fallback when MCP Apps are unavailable.



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

### Debian package or portable archive

Linux releases include both `harr_<version>_<arch>.deb` and
`harr-<version>-linux-<arch>.tar.gz`.
The Harr GitHub Actions release workflow downloads the pinned LeanCTX build from
`smollgreymouse/lean-ctx`, verifies its release SHA-256 and embedded Harr build ID,
and bundles the verified Linux binary into both packages. Packaged setup uses this
local binary without fetching LeanCTX again; source-checkout setup can still
download the pinned release. Harr releases therefore wait for the corresponding
LeanCTX release to be published first. The Debian package installs the Harr
files and provides the `harr` CLI; it does not change global user configuration
during `apt install`.

After installing the package, run the initial user setup as the normal user:

```bash
harr setup --clean
```

The first interactive setup offers the optional MCP checklist. For automation,
use `harr setup --clean --all`, `harr setup --clean --mcp none`, or
`harr setup --clean --mcp gitlab,grafana,kibana,gigacode,einherjar`. The selection is saved and can be
changed later with `harr mcp configure`.

After a later Debian package upgrade, run `harr setup` to apply the new Harr
files/runtime while reusing the saved MCP selection. Package-mode setup keeps
`~/.local/bin/harr` as a shim to `/usr/bin/harr`, so future package upgrades
do not leave a stale user-level CLI ahead of the packaged command in `PATH`.
If migrating from an older source-based Harr that already has a standalone
`~/.local/bin/harr`, use `/usr/bin/harr setup` once after installing the new
Debian package; subsequent runs can use plain `harr setup`.

On the first interactive setup all three platforms show the same selector:

```text
Harr components

  [x] LeanCTX      required  compact MCP gateway
  [x] CodeGraph    required  cross-file code structure and impact analysis
> [ ] GitLab       optional  GitLab API, merge requests, pipelines and issues
  [ ] Grafana      optional  Grafana dashboards and datasources
  [ ] Jira         optional  Jira Server/Data Center issues and JQL via local REST MCP
  [ ] Kibana       optional  read-only logs/search through Kibana
  [ ] GigaCode     optional  persistent external executor for planner-to-builder delegation
  [ ] Einherjar     optional  generic external CLI-agent worker (GigaCode/OpenCode/Codex/custom)

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
./install.sh --clean --mcp gitlab,grafana,kibana,gigacode,einherjar
```

```powershell
# Windows
.\install.ps1 -Clean -Mcp gitlab,grafana,kibana,gigacode,einherjar
```

If local PowerShell policy blocks scripts, use a process-local bypass rather than changing the machine policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Clean -Start
```

Configure secrets only for MCPs you enabled:

```text
harr secret set gitlab
harr secret set grafana
harr secret set kibana
harr secret set jira
```

Grafana also requires `uvx` in `PATH`; Harr uses it on demand and does not globally install `mcp-grafana`.

Kibana also uses uvx; Harr pins the smollgreymouse/kibana-agent fork to a commit that supports API-key auth and the MCP v1 SDK.

GigaCode is an executor bridge, not a bundled model/runtime. Enabling it installs Harr's MCP bridge and routing policy; the external `gigacode` CLI must already be installed, authenticated and available in `PATH`. Harr keeps the bridge behind LeanCTX and loads its single-tool schema only when delegation is needed. The bridge treats GigaCode as a black box: Harr does not configure, inspect or depend on GigaCode's own tools or MCP servers. The saved MCP selection is reused by later source/package upgrades, so a selected GigaCode executor remains selected across reinstall/update runs; change the set with `harr mcp configure`.

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

### First setup / source install

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
  vendor/lean-ctx/3.11.0-harr-progress.1/lean-ctx

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
  vendor/lean-ctx/3.11.0-harr-progress.1/lean-ctx

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
    vendor\lean-ctx\3.11.0-harr-progress.1\lean-ctx.exe
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
harr workspace show
harr workspace list
harr workspace add PATH
harr workspace remove PATH

harr install all
harr install leanctx
harr install mcp

harr mcp available
harr mcp list
harr mcp configure
harr mcp configure none
harr mcp configure all
harr mcp configure gitlab,grafana,kibana,gigacode   # replace the whole optional set
harr mcp add gigacode                        # preserve other selected MCPs
harr mcp add gitlab,grafana
harr mcp remove grafana
harr mcp remove all                          # keep required MCPs only

harr secret status
harr secret set gitlab
harr secret set grafana
harr secret set kibana
harr secret set jira
harr secret unset gitlab
harr secret unset grafana
harr secret unset kibana

harr git <git-arguments>
harr git -C /absolute/repository/path <git-arguments>

harr uninstall
```

`harr mcp available` shows the full catalog and whether each entry is required/optional and enabled/disabled. `harr mcp list` lists the currently enabled downstream MCPs. `harr mcp add`/`remove` incrementally mutate the saved optional set while preserving every other choice. `harr mcp configure` opens the same cross-platform checklist used by first install; its optional argument replaces the complete optional set non-interactively.

Lifecycle commands apply only to **enabled** registry entries with `lifecycle = service`; on-demand stdio MCPs such as CodeGraph are spawned by LeanCTX when called.

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
runtime:    npm package | bundled Python bridge | command already available in PATH
secret:     env for local services | LeanCTX secret_env | secret_headers
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
harr mcp add gitlab
```

For incremental changes prefer `harr mcp add gitlab` and `harr mcp remove gitlab`; these preserve every other selected optional MCP. Use `harr mcp configure` only when you want the interactive checklist or to replace the complete optional set explicitly.

GitLab is declared as an on-demand stdio MCP in the common registry and spawned by LeanCTX through the generic runner:

```text
LeanCTX -> harr-mcp-run gitlab -> zereight-mcp-gitlab
```

Harr exposes the full GitLab tool catalog behind LeanCTX:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

LeanCTX gateway discovery is intentionally compact but not single-result: Harr uses `gateway.top_n = 3`. Discovery is ranked, so absence from one broad result is not proof that a GitLab capability is unavailable. When a workflow defines an expected downstream tool, Harr discovers it by its exact bare name, for example `create_merge_request` -> `gitlab::create_merge_request`; otherwise it uses a verb-and-object query. A related result is not a substitute for the expected tool. Harr refreshes and repeats the same query once before declaring an expected tool missing.

MR creation is treated as a combined Git + GitLab workflow. Git owns the repository and remote refs; GitLab MCP owns the MR API object. The MR source branch is the **current named local branch**, never its configured upstream. Publish it with ordinary Git through the host service and an explicit destination:

```text
harr git push --set-upstream <remote> HEAD:refs/heads/<current-local-branch>
harr git ls-remote <remote> refs/heads/<current-local-branch>
```

Read local `HEAD` before the push and require the exact remote ref SHA returned by `ls-remote` to match it. Verify that upstream is `<remote>/<current-local-branch>`. The explicit refspec prevents a stale feature-branch upstream such as `origin/master` from redirecting publication to protected `master` or determining the MR `source_branch`.

After publication, discover and call `gitlab::create_merge_request` with `source_branch=<current-local-branch>` and the separately determined target branch, then verify it through `gitlab::get_merge_request`. Never substitute `update_merge_request` for creation. GitLab repository-file APIs such as `create_branch`, `create_or_update_file`, and `push_files` create server-side refs or API commits; they must never mirror the local diff or replace Git transport.

Git commit author, GitLab MR author, assignee and reviewer are distinct. The MR author is the authenticated GitLab identity; requested assignees/reviewers are resolved to GitLab user IDs and verified on the resulting MR rather than assumed from a name.

The PAT is stored only locally under the Harr config root; the Harr LeanCTX wrapper supplies it through registry-defined secret-memento handling while GitLab is enabled. Host Git never reads or injects this PAT.

```text
harr secret set gitlab
harr secret status
harr secret unset gitlab
```

Disabling GitLab removes it from the gateway and agent policy/skill, but preserves its local env/secret files.



### Grafana

Grafana is **optional** and declared as an on-demand stdio MCP in the common registry. When enabled, the generated LeanCTX route is equivalent to:

```text
LeanCTX -> harr-mcp-run grafana -> uvx --offline mcp-grafana --transport stdio
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

The registry maps that secret to `GRAFANA_SERVICE_ACCOUNT_TOKEN` for the local Grafana MCP while Grafana is enabled. The token must not be placed in `grafana.env`, LeanCTX configuration, or the repository. Harr does not pass `--disable-write`.

For dashboard edits, prefer the compact patch-first flow:

```text
search_dashboards
  -> get_dashboard_summary
  -> targeted property/panel-query reads
  -> update_dashboard
```

Fetch a complete dashboard definition only when the targeted tools are insufficient.



### Kibana

Kibana is optional and provides read-only Elasticsearch investigation through an already reachable Kibana instance.

Route: LeanCTX -> harr-mcp-run kibana -> pinned smollgreymouse/kibana-agent fork -> Kibana /api/console/proxy -> Elasticsearch.

This is intended for environments where Kibana is reachable but Elasticsearch itself is private. Harr pins smollgreymouse/kibana-agent at commit 2998352c4c360d10d8d1dfc114dc7d26217d537c. The fork adds KIBANA_API_KEY authentication and constrains the Python MCP SDK to the v1 API used by kibana-agent.

Enable it with:

    harr mcp add kibana
    harr install mcp

Configure ~/.config/harr/mcp/kibana.env:

    KIBANA_URL=https://kibana.example.com

Store the API key separately:

    harr secret set kibana
harr secret set jira
    harr secret status

Harr injects the key as KIBANA_API_KEY only into the MCP process. The fork sends it to Kibana as Authorization: ApiKey and does not persist it in a kibana-agent profile.

The MCP exposes targeted read-only tools including search_logs, count_documents, get_histogram, get_context, get_mapping, list_fields, list_aliases, list_data_views, tail_logs, raw_es_query, and get_discover_url. Exact Kibana Data View names/IDs are resolved to their underlying Elasticsearch title patterns before querying. Prefer targeted tools and keep index patterns, time windows, fields, and result sizes narrow. raw_es_query remains constrained by kibana-agent's read-only request guard.

See common/skills/harr/references/kibana.md for pinned-runtime and routing details.



### Einherjar generic CLI worker

Einherjar is an **optional, backend-neutral** external worker bridge. Enable it with:

```text
harr mcp add einherjar
harr install mcp
```

It appears behind LeanCTX as one downstream tool:

```text
einherjar::worker
```

The single schema carries `action=start|resume|status|messages|wait|cancel|backends`. The planner owns architecture and the execution contract; Einherjar owns detached process/session lifecycle and maps the Harr session to the selected CLI's private session. Built-in adapters are `gigacode`, `opencode`, and `codex`; the configured default is used unless `start` explicitly names a backend.

Harr does not own agent-provider authentication. Each CLI must already be installed/authenticated in its normal way; provider tokens are not stored in Einherjar config. `action=backends` reports only safe capability/discovery information.

Configuration lives at `~/.config/harr/einherjar.json` (or the Harr/XDG config root). Example:

```json
{
  "schema": 1,
  "default_backend": "gigacode",
  "backends": {
    "my-agent": {
      "adapter": "command-template",
      "start": ["my-agent", "run", "--prompt-file", "{prompt_file}"],
      "resume": ["my-agent", "resume", "{session_id}", "--prompt-file", "{prompt_file}"],
      "session_id": {"source": "stdout-json", "keys": ["session_id", "sessionId"]},
      "events": {"mode": "jsonl"}
    }
  }
}
```

Command-template commands are argv arrays, never shell strings. Supported placeholders are `{prompt}`, `{prompt_file}`, `{session_id}`, and `{workspace}`; prompt transport may also use `"stdin": true`. More complex CLIs should get a dedicated adapter rather than leaking vendor behavior into the core.

The stable adapter specification is [`docs/EINHERJAR_BRIDGE_CONTRACT.md`](docs/EINHERJAR_BRIDGE_CONTRACT.md). It defines the core↔adapter boundary, capabilities, session identity, start/resume/cancel semantics, event normalization, final handoff rules, conformance tests, and the checklist for wrapping another agent CLI.

The older `gigacode::gigacode` MCP remains available and unchanged for compatibility. Enabling Einherjar does not automatically enable or replace that legacy route.

### GigaCode executor

GigaCode is **optional** and exposed behind LeanCTX as one downstream tool:

```text
gigacode::gigacode
```

That one schema carries `action=start|resume|status|messages|wait|cancel`; enabling GigaCode does not add separate permanent executor tools to the parent model. When GigaCode is selected, Harr also installs the `$gigacode-executor` skill for Codex/OpenCode. Harr adds only its own managed global skill directories to LeanCTX `allow_paths`, so PathJail remains enabled while those skills can be read from projects outside the home config tree. A normal delegated flow is:

```text
parent: architecture + execution contract
  -> ctx_tools(... gigacode::gigacode, action=start ...)
  -> RUNNING + session_id
  -> independent planner work OR one MCP-local wait (no delegated-source reads/review/test loops)
  -> DONE + criterion evidence + final diff/scope self-review
  -> parent contract acceptance
```

Harr ships only the bridge. The external `gigacode` CLI must already be installed and authenticated. The bridge deliberately treats it as a black box: it does not configure, inspect, or depend on GigaCode's own tool names, shell implementation, editor, extensions, or MCP servers.

Normal RUNNING status is intentionally compact and does not expose GigaCode event history, internal logs, model text, or tool traces. `status` remains nonblocking; `wait` blocks inside the bridge for up to 1500 seconds so the parent model does not spend turns polling. With Harr's progress-aware LeanCTX fork, request-scoped GigaCode chat-display assistant text is forwarded for client UI display while the terminal tool result stays compact. Thought/reasoning parts, tool/runtime records, and the final structured Harr handoff are excluded from that chat stream. Explicit `messages` calls fetch the same chat-display text with a revision cursor, but because that is a normal MCP result it enters the parent tool context and is not used for automatic monitoring. Before a worker handoff is accepted as `DONE`, the bridge requires criterion-by-criterion PASS evidence, no unresolved blockers, and a successful final diff/scope self-review. Missing evidence is returned to the same GigaCode session with `resume`; the expensive parent does not repeat the executor's code reading and test loop by default.

The bridge keeps a persistent GigaCode session, performs a bounded startup handshake, and runs execution detached. Hard timeout defaults to unlimited; cancellation is explicit unless the caller supplies a positive `timeout_sec`. One `wait` call is bounded to 1500 seconds; Harr configures the LeanCTX downstream timeout to 1800 seconds and Codex/OpenCode host-side LeanCTX timeouts to 1900 seconds so the blocking wait completes without forcing model-level polling.

The saved Harr MCP selection controls whether the GigaCode route, routing policy, reference material, and `$gigacode-executor` skill exist. Normal later setup/update runs reuse that selection; use `harr mcp add/remove` for incremental changes or `harr mcp configure` for full replacement.

### Jira (Server/Data Center, local MCP)

Jira is optional. Harr launches [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) as a local stdio MCP behind LeanCTX and connects to the configured Jira REST API. The Jira server does **not** need its own MCP plugin or Atlassian Cloud support; Docker is not required.

1. Enable Jira through `harr mcp configure` (preserving other selected MCPs).
2. Run `harr install mcp` to prepare the `uvx` runtime.
3. Set `JIRA_URL=https://jira.company.example` in the Harr config root's `mcp/jira.env`.
4. Run `harr secret set jira` to securely store a Jira Server/Data Center Personal Access Token.
5. Restart the agent session to discover the `jira::*` tools via LeanCTX.

This default preset uses `JIRA_PERSONAL_TOKEN`; it requires a Jira version supporting personal access tokens. Older installations without PAT support require a separately tested authentication integration. For Jira Cloud, use the Cloud username/API-token method rather than this Server/DC preset. See `common/skills/harr/references/jira.md`.

### Git

Git is intentionally **not** a Harr MCP component. Use exact `git ...` commands through LeanCTX `ctx_shell` for ordinary local repository state/history/branches. Use `harr git <git-arguments>` for network operations. The command sends the current working directory and Git arguments to a loopback-only Harr user service, which executes the real Git process outside the agent sandbox with the service's terminal-session environment. Repository remotes, local Git configuration and SSH key selection remain unchanged.

On Linux the required `harr-git-host.service` is installed and started automatically. On macOS the equivalent `com.harr.git-host` LaunchAgent is installed and loaded. A private capability authenticates loopback requests; it never contains an SSH key. Harr passes the current terminal's valid `SSH_AUTH_SOCK` to the user service, and `harr status` reports whether that agent remains available.

Windows host Git is not claimed yet. Its current HTTPS/PAT compatibility transport remains platform-local until the real agent sandbox experiments in `docs/windows-git-host-handoff.md` are completed.

When GitLab is enabled, its stored PAT authenticates GitLab MCP API operations such as MRs, pipelines, jobs, issues and users through `ctx_tools`. It is not injected into Git. Git and `harr git` exclusively own commits, branches, remotes, fetch/push and remote-ref verification.



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

The permanent policy always keeps the core token-saving rules:

- MCP for investigation; native host editor for edits;
- cross-file structure/flow/relationships/dependencies/architecture/impact -> **CodeGraph first**;
- CodeGraph calls sequentially; returned source counts as already read;
- missing exact evidence -> narrow LeanCTX read/search/glob/shell;
- ordinary local Git operations -> exact `git ...` commands through `ctx_shell`; Git network operations -> `harr git ...`; GitLab server/API objects -> `gitlab::*` through `ctx_tools`;
- known, non-editing uncommon LeanCTX capabilities -> `ctx_call`; never use it to discover edit/patch tools;
- no broad repository inventory after CodeGraph;
- no duplicate gateway/direct investigation;
- build/test only on explicit request.

Optional routing lines are generated only for the selected MCP set. For example, GitLab API routing does not exist when GitLab is disabled, Grafana dashboard guidance does not exist when Grafana is disabled, Kibana investigation guidance does not exist when Kibana is disabled, the GigaCode planner/executor contract is absent unless the GigaCode MCP is selected, and Einherjar routing is absent unless the Einherjar MCP is selected.

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

They are installed globally for both Codex and OpenCode. The installed Harr skill is rendered against the same effective MCP registry as the global policy: optional command blocks and component reference files are omitted when that MCP is disabled. Other third-party skill directories are untouched.



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
