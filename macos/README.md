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

## GitLab Git transport

When GitLab is enabled and its Harr secret is configured, Harr can publish Git branches without SSH keys. For an MR source branch use:

```text
harr gitlab publish [remote]
```

This command takes the source name from the current local branch, never from its upstream, and performs a real Git-over-HTTPS push using the stored GitLab PAT through `GIT_ASKPASS`. It pushes `HEAD:refs/heads/<current-local-branch>`, verifies the remote SHA equals local `HEAD`, then sets upstream to the same-named remote branch. A stale upstream such as `origin/master` therefore cannot redirect MR publication to `master`.

For custom push options/refspecs use the lower-level:

```text
harr gitlab push [git-push-options] [remote] [refspec...]
```

For remote reads from an isolated agent host, use:

```text
harr gitlab fetch [remote] [refspec...]
```

All three commands use the Harr HTTPS/PAT transport. They neither rewrite the repository remote URL nor write global Git URL rewrites, and they do not require an SSH attempt first.

## Kubernetes / kubectl bridge

Kubernetes is not an MCP component. Harr uses the real kubectl through `ctx_shell` and supplies a Harr-owned portable kubeconfig so sandboxed/isolated hosts do not need access to the user's original `~/.kube/config`.

From a normal terminal where kubectl already works, run once:

```text
harr kube configure
```

Harr captures `kubectl config view --raw --flatten -o json` into:

```text
~/.config/harr/kubernetes/config
```

with private permissions and verifies the candidate config against the current cluster before replacing the previous snapshot. Then all agent-side Kubernetes work uses normal kubectl syntax after the Harr prefix:

```text
harr kubectl get pods -A
harr kubectl logs POD -n NAMESPACE --tail=100
harr kubectl apply -f manifest.yaml
harr kubectl rollout status deployment/NAME -n NAMESPACE
harr kubectl delete pod POD -n NAMESPACE
```

`harr kubectl` always passes the managed `--kubeconfig`; callers cannot override it. Refresh the private snapshot after changing the normal kubeconfig with `harr kube sync`, and inspect it without printing credentials with `harr kube status`.

If the current kubeconfig context uses a `user.exec` credential helper, `harr kube configure` refuses it by default because a flattened file alone is not portable. `--allow-exec` is an explicit opt-in only when that helper and its credential chain are reachable from every Harr host.

The Kubernetes snapshot lives under Harr's config root and is therefore included in clean rollback ownership.

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
