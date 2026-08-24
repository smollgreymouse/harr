# Windows

Windows is a supported Harr platform layer. Installation is user-level PowerShell and targets the same Codex/OpenCode global harness contract as Linux and macOS. Platform-independent policy, skills, MCP selection/catalog and host config writers live under `../common`.

Use the repository root `install.ps1`; do not run this directory directly unless debugging the platform installer.

## Install

Fresh interactive install:

```powershell
git clone https://github.com/smollgreymouse/harr.git
cd harr
.\install.ps1 -Clean -Start
```

LeanCTX and CodeGraph are required. The first interactive install presents the shared Harr checklist for optional MCPs such as GitLab and Grafana.

Full install without prompts:

```powershell
.\install.ps1 -Clean -All -Start
```

Required-only install without prompts:

```powershell
.\install.ps1 -Clean -Mcp none
```

Exact optional set:

```powershell
.\install.ps1 -Clean -Mcp gitlab,grafana
```

Normal updates reuse the saved selection without prompting. Use `-ConfigureMcp` to show the checklist again during installation, or change it later with:

```text
harr mcp configure
harr mcp configure none
harr mcp configure all
harr mcp available
```

The same saved selection drives the LeanCTX gateway, npm/path runtime set, secrets/status, Scheduled Tasks, global AGENTS routing and installed Harr skill/reference set. Disabled MCP env/secret files are preserved.

## GitLab Git transport

When GitLab is enabled and its Harr secret is configured, Harr can publish Git branches without SSH keys. For an MR source branch use:

```text
harr git publish [remote]
```

This command takes the source name from the current local branch, never from its upstream, and performs a real Git-over-HTTPS push using the stored GitLab PAT through `GIT_ASKPASS`. It pushes `HEAD:refs/heads/<current-local-branch>`, verifies the remote SHA equals local `HEAD`, then sets upstream to the same-named remote branch. A stale upstream such as `origin/master` therefore cannot redirect MR publication to `master`.

For custom push options/refspecs use the lower-level:

```text
harr git push [git-push-options] [remote] [refspec...]
```

Neither command rewrites the repository remote URL or requires an SSH attempt first.

## Lifecycle

Enabled registry entries with `lifecycle = service` are mapped to non-elevated per-user Scheduled Tasks. Disabled service MCP tasks are stopped and unregistered from the active Harr configuration.

Useful commands:

```text
harr mcp list
harr mcp available
harr mcp start all
harr mcp status
harr mcp logs gitlab
```

## Rollback

```text
harr uninstall
```

The Windows clean snapshot also owns the saved selection/effective-registry paths and catalog-defined Scheduled Task names, so rollback restores the exact pre-Harr state.
