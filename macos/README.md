# macOS

Harr supports macOS as a first-class user-level platform adapter.

Shared policy, host writers, skills, LeanCTX base configuration, MCP catalog and MCP selection logic remain under `../common`. The macOS layer contains only Darwin installation/runtime paths, LeanCTX asset selection, `launchd` lifecycle glue and rollback state handling.

## Install

Fresh interactive install:

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean --start
```

LeanCTX and CodeGraph are required. The first interactive install presents the shared Harr checklist for optional MCPs such as GitLab and Grafana.

Full install without prompts:

```bash
./install.sh --clean --all --start
```

Required-only install without prompts:

```bash
./install.sh --clean --mcp none
```

Exact optional set:

```bash
./install.sh --clean --mcp gitlab,grafana
```

Normal updates reuse the saved selection without prompting. Use `--configure-mcp` to show the checklist again during installation, or change it later with:

```text
harr mcp configure
harr mcp configure none
harr mcp configure all
harr mcp available
```

The first install requires `--clean` so Harr can snapshot the existing global Codex/OpenCode harness and any colliding LaunchAgents before taking ownership. Do not use `sudo`.

Requirements:

- macOS on Apple Silicon or x86_64;
- Python 3;
- Node.js 20-24 and npm for selected registry-managed npm MCP runtimes;
- standard `curl`, `tar`, `shasum`, and `launchctl` tools.

The same saved selection drives the LeanCTX gateway, runtime set, secrets/status, LaunchAgents, global AGENTS routing and installed Harr skill/reference set. Disabled MCP env/secret files are preserved.

## Lifecycle

Enabled registry entries with `lifecycle = service` are mapped to:

```text
~/Library/LaunchAgents/com.harr.mcp.<name>.plist
```

Disabled service MCP LaunchAgents are unloaded and removed from the active Harr configuration. Logs are written under:

```text
~/Library/Logs/Harr/
```

Useful commands:

```text
harr mcp list
harr mcp available
harr mcp start all
harr mcp status
harr mcp logs gitlab -f
```

On-demand stdio MCPs are spawned through LeanCTX and do not get LaunchAgents.

## Rollback

```text
harr uninstall
```

The snapshot records Harr-owned global files plus any pre-existing LaunchAgent plist/load/disabled state for labels in the full Harr MCP catalog. If a colliding LaunchAgent is already loaded but has no plist Harr can preserve, clean takeover refuses to proceed rather than promising an inexact rollback.
