---
name: harr
description: Harr installation and diagnostics only: managed component versions, MCP services, agent policy, Git/Kubernetes transports, secrets, and repair. Do not load for normal repository investigation; the compact Harr routing block in global AGENTS.md already defines tool order.
---
<!-- harr-managed-skill-v1 -->

# Harr operations

Use this skill only when installing, checking, or repairing the harness.

```text
harr status
harr install all
harr agents status
harr agents apply
harr leanctx status
harr leanctx apply
harr git <git-arguments>  # Linux host-Git bridge
harr git -C /absolute/repository/path <git-arguments>
harr kube configure
harr kube sync
harr kube status
harr kubectl <kubectl args...>
harr mcp available
harr mcp configure
harr mcp list
<!-- harr-mcp:gitlab:start -->
harr secret set gitlab
harr gitlab fetch [remote] [refspec...]
harr gitlab publish [remote]
harr gitlab push [git-push-options] [remote] [refspec...]
harr mcp status gitlab
harr mcp logs gitlab
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
harr secret set grafana
<!-- harr-mcp:grafana:end -->
```

LeanCTX and CodeGraph are the required Harr baseline. Optional MCPs are selected globally with `harr mcp configure`; generated policy, skills, gateway, runtime and service lifecycle follow that selection.

Kubernetes is intentionally not an MCP component. `harr kube configure` captures the user's working kubectl configuration into Harr-owned private state, and `harr kubectl ...` executes the real kubectl with that managed config so isolated agent hosts do not need direct access to the original kubeconfig. Load `references/kubernetes.md` only for Kubernetes bridge setup/diagnostics.

## Host Git transport (Linux)

Use ordinary `git ...` through `ctx_shell` for local work such as `status`, `diff`, `log`, `branch`, `add`, `commit`, and configuration inspection.

Use `harr git ...` through `ctx_shell` for every command that can contact a remote and should authenticate like the user's terminal. Harr delegates the entire Git command to a loopback-only user service outside the sandbox. The host process uses the user's normal SSH agent, SSH configuration, known-hosts handling, Git configuration, and credential helpers. It does not require project policy, an `IdentityFile`, a PAT, a remote rewrite, or `core.sshCommand`.

```text
harr git pull
harr git fetch origin
harr git push origin HEAD
harr git ls-remote origin
harr git submodule update --init --recursive
harr git lfs pull
```

The service preserves the caller's working directory. If LeanCTX cannot use the target repository as `ctx_shell` cwd, invoke Harr from an allowed cwd and identify the repository explicitly:

```text
harr git -C /absolute/repository/path pull
harr git -C /absolute/repository/path push origin HEAD
```

Do not try bare network `git` first, manually select an SSH key, expose an agent socket to the sandbox, or fall back to browser authentication. Check `harr status` when diagnosing transport: an SSH-backed operation expects `host-git-service ready (ssh-agent: available)`. If it is unavailable, report that exact condition; `references/git.md` contains repair details. Treat the command as successful only when it exits zero.

When GitLab is enabled, `harr gitlab fetch`, `harr gitlab publish`, and `harr gitlab push` are the separate HTTPS/PAT route. Keep it for users who chose PAT authentication and for the branch-safe MR workflow. `harr gitlab publish` uses the current local branch name, pushes `HEAD` to the same-named remote branch, verifies the remote SHA, and normalizes upstream to that branch. `harr gitlab push` is the lower-level command for custom push options/refspecs. Use `harr git` for a GitLab remote only when the user wants normal terminal authentication. Never silently switch identities or credential routes.

Harr owns managed versions/configuration. Do not independently run upstream LeanCTX setup/update, CodeGraph upgrades, or global installs of Harr-managed MCP packages.

Load only the needed file under `references/` for component-specific diagnostics; never load all references by default.
