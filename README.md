# Harr

Harr is a small local harness supervisor for long-lived MCP servers.

The name is both an Odin reference and a phonetic joke on “harness”.

## Current services

- `gitlab` — `@zereight/mcp-gitlab` exposed as Streamable HTTP on `127.0.0.1:3334/mcp`.

Harr deliberately does **not** store the GitLab PAT. The GitLab MCP server runs with `REMOTE_AUTHORIZATION=true`; the MCP client/gateway supplies the token per request (for example LeanCTX via `Private-Token`).

Harr also does not intentionally trim the GitLab MCP tool surface. The defaults are `GITLAB_PERMISSION_MODE=full` and `GITLAB_TOOLSETS=all`, so `tools/list` exposes every enabled server category and read/create/update/delete capabilities. Effective authorization is still bounded by the GitLab token supplied by the client. If a stricter server-side policy is desired, set `modify` (hide/reject delete operations) or `readonly` in `~/.config/harr/mcp/gitlab.env`; `GITLAB_TOOLSETS` can also be narrowed to selected categories.

## Install

Linux user-level installation:

```bash
./install.sh
```

The installer:

- installs `harr` to `~/.local/bin/harr`;
- installs runtime helpers to `~/.local/libexec/harr`;
- installs user units to `~/.config/systemd/user`;
- creates `~/.config/harr/mcp/gitlab.env` on first install;
- detects the absolute path to `mcp-gitlab` / `zereight-mcp-gitlab`;
- preserves existing MCP env files on upgrades;
- reloads the user systemd manager and enables the GitLab unit for future sessions.

It does not start the service automatically, so an already-running foreground MCP server cannot collide with the managed port. Stop the foreground process first, then run:

```bash
harr mcp start gitlab
```

Use `./install.sh --start` to start/restart managed services during installation.

Make sure `~/.local/bin` is in `PATH`.

## MCP orchestration

```bash
harr mcp list
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp enable gitlab
harr mcp disable gitlab
harr mcp status gitlab
harr mcp logs gitlab
harr mcp logs gitlab -f
```

`all` is accepted by lifecycle commands:

```bash
harr mcp start all
harr mcp restart all
harr mcp stop all
```

Overall status:

```bash
harr status
# same as:
harr mcp status
```

## GitLab endpoint

Default runtime configuration:

```text
HOST=127.0.0.1
PORT=3334
STREAMABLE_HTTP=true
REMOTE_AUTHORIZATION=true
GITLAB_API_URL=https://gitlab.sca.ad-tech.ru/api/v4
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

LeanCTX gateway entry:

```toml
[[gateway.servers]]
name = "gitlab"
transport = "http"
enabled = true
url = "http://127.0.0.1:3334/mcp"

[gateway.servers.headers]
Private-Token = "<PAT>"
```

Prefer LeanCTX secret headers instead of committing a real PAT to its configuration.

## Layout

```text
install.sh
linux/
  install.sh
  harr
  files/
    harr-cli/
      common.sh
      help.sh
      mcp.sh
    mcp/
      gitlab-run
      gitlab.env.example
  systemd/
    harr-mcp-gitlab.service
```

The CLI discovers Harr-managed MCP units by the `harr-mcp-*.service` naming convention, so adding another server later does not require rewriting the lifecycle commands.
