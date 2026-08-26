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
harr kube configure
harr kube sync
harr kube status
harr kubectl <kubectl args...>
harr mcp available
harr mcp configure
harr mcp list
<!-- harr-mcp:gitlab:start -->
harr secret set gitlab
harr git fetch [remote] [refspec...]
harr git publish [remote]
harr git push [git-push-options] [remote] [refspec...]
harr mcp status gitlab
harr mcp logs gitlab
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
harr secret set grafana
<!-- harr-mcp:grafana:end -->
```

LeanCTX and CodeGraph are the required Harr baseline. Optional MCPs are selected globally with `harr mcp configure`; generated policy, skills, gateway, runtime and service lifecycle follow that selection.

Kubernetes is intentionally not an MCP component. `harr kube configure` captures the user's working kubectl configuration into Harr-owned private state, and `harr kubectl ...` executes the real kubectl with that managed config so isolated agent hosts do not need direct access to the original kubeconfig. Load `references/kubernetes.md` only for Kubernetes bridge setup/diagnostics.

When GitLab is enabled, `harr git fetch`, `harr git publish`, and `harr git push` use Harr's HTTPS/PAT transport. `harr git publish` is the branch-safe host-independent MR source publisher: it uses the current local branch name, pushes `HEAD` to the same-named remote branch, verifies the remote SHA, and normalizes upstream to that branch. `harr git push` is the lower-level command for custom push options/refspecs. These commands never require SSH credentials, change a repository remote URL, or write global Git URL rewrites.

Harr owns managed versions/configuration. Do not independently run upstream LeanCTX setup/update, CodeGraph upgrades, or global installs of Harr-managed MCP packages.

Load only the needed file under `references/` for component-specific diagnostics; never load all references by default.
