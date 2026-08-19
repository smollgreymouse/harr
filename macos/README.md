# macOS

Harr supports macOS as a first-class user-level platform adapter.

Shared policy, host writers, skills, LeanCTX base configuration and the downstream MCP registry remain under `../common`. The macOS layer contains only Darwin installation/runtime paths, LeanCTX asset selection, `launchd` lifecycle glue and rollback state handling.

## Install

```bash
git clone https://github.com/smollgreymouse/harr.git
cd harr
./install.sh --clean --start
```

The first install requires `--clean` so Harr can snapshot the existing global Codex/OpenCode harness and any colliding LaunchAgents before taking ownership. Do not use `sudo`.

Requirements:

- macOS on Apple Silicon or x86_64;
- Python 3;
- Node.js 20-24 and npm for registry-managed npm MCP runtimes;
- standard `curl`, `tar`, `shasum`, and `launchctl` tools.

Harr installs the pinned LeanCTX Darwin asset for the current architecture and uses the same `common/mcp/registry.json` as Linux and Windows.

## Lifecycle

Registry entries with `lifecycle = service` are mapped to:

```text
~/Library/LaunchAgents/com.harr.mcp.<name>.plist
```

Logs are written under:

```text
~/Library/Logs/Harr/
```

Useful commands:

```text
harr mcp list
harr mcp start all
harr mcp status
harr mcp logs gitlab -f
```

On-demand stdio MCPs are still spawned through LeanCTX and do not get LaunchAgents.

## Rollback

```text
harr uninstall
```

The snapshot records Harr-owned global files plus any pre-existing LaunchAgent plist/load/disabled state for labels Harr will own. If a colliding LaunchAgent is already loaded but has no plist Harr can preserve, clean takeover refuses to proceed rather than promising an inexact rollback.
