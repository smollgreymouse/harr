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

Kubernetes is not an MCP component. Harr uses the real kubectl through `ctx_shell` and supplies a Harr-owned portable kubeconfig so sandboxed/isolated hosts do not need access to the user's original `%USERPROFILE%\.kube\config`.

From a normal PowerShell/terminal where kubectl already works, run once:

```text
harr kube configure
```

Harr captures `kubectl config view --raw --flatten -o json` into:

```text
%USERPROFILE%\.config\harr\kubernetes\config
```

and verifies the candidate config against the current cluster before replacing the previous snapshot. Then all agent-side Kubernetes work uses normal kubectl syntax after the Harr prefix:

```text
harr kubectl get pods -A
harr kubectl logs POD -n NAMESPACE --tail=100
harr kubectl apply -f manifest.yaml
harr kubectl rollout status deployment/NAME -n NAMESPACE
harr kubectl delete pod POD -n NAMESPACE
```

`harr kubectl` always passes the managed `--kubeconfig`; callers cannot override it. Refresh the private snapshot after changing the normal kubeconfig with `harr kube sync`, and inspect it without printing credentials with `harr kube status`.

If the current kubeconfig context uses a `user.exec` credential helper, `harr kube configure` refuses it by default because a flattened file alone is not portable. `--allow-exec` is an explicit opt-in only when that helper and its credential chain are reachable from every Harr host.

The Windows rollback snapshot explicitly owns `%USERPROFILE%\.config\harr\kubernetes`, so an existing pre-Harr directory is restored exactly and a Harr-created one is removed by `harr uninstall`.

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

The Windows clean snapshot also owns the saved selection/effective-registry paths, Harr Kubernetes state, and catalog-defined Scheduled Task names, so rollback restores the exact pre-Harr state.
