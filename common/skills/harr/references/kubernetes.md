# Kubernetes through Harr

Kubernetes is intentionally **not** a Harr MCP component. Harr keeps the permanent agent surface small and routes Kubernetes through the real `kubectl` using LeanCTX `ctx_shell`.

## Runtime route

```text
agent -> LeanCTX ctx_shell -> harr kubectl ... -> real kubectl -> Kubernetes API
```

Do not use a Kubernetes MCP for normal Harr-managed Kubernetes work. Do not use bare `kubectl` from an agent host: the host may not be able to see the user's original kubeconfig even when kubectl works in a normal terminal.

## Initial setup

Run this from a normal user terminal where `kubectl` already works:

```text
harr kube configure
```

Harr runs the installed kubectl equivalent of:

```text
kubectl config view --raw --flatten -o json
```

and stores the result privately under the Harr config root:

```text
Linux/macOS: ~/.config/harr/kubernetes/config
Windows:     %USERPROFILE%\.config\harr\kubernetes\config
```

The managed config is mode `0600` where the platform supports POSIX permissions. The original kubeconfig is never modified.

`--flatten` makes certificate/key file references self-contained. `--raw` includes credential material, so the Harr-managed config must be treated as secret state and must never be printed or committed.

By default configure also performs a bounded live `/version` request with the candidate managed config before replacing the previous snapshot. Use `--no-check` only when live verification is deliberately unavailable.

Useful setup options:

```text
harr kube configure --source PATHLIST
harr kube configure --kubectl /absolute/path/to/kubectl
harr kube configure --allow-exec
harr kube configure --no-check
```

## Exec credential helpers

Kubeconfig may contain `user.exec`, for example an AWS/GCP/Azure/OIDC helper. A flattened file does not make that external executable portable.

Harr inspects the **current context** during configure. If it uses an exec credential helper, configure fails by default instead of claiming the snapshot is portable. Use `--allow-exec` only when the helper executable and its own credential chain are known to be available to every Harr host that will run kubectl.

Other contexts may remain in the snapshot. If an agent later selects a context whose user uses `exec`, `harr kubectl` refuses it unless the snapshot was configured with `--allow-exec`.

## Running kubectl

Use normal kubectl syntax after the Harr prefix:

```text
harr kubectl get pods -n my-namespace
harr kubectl get deploy my-app -o yaml
harr kubectl logs pod-name --tail=100
harr kubectl diff -f manifest.yaml
harr kubectl apply -f manifest.yaml
harr kubectl rollout status deployment/my-app -n my-namespace
harr kubectl delete pod pod-name -n my-namespace
harr kubectl exec -it pod-name -- sh
```

Harr invokes the stored absolute kubectl path with an explicit `--kubeconfig <Harr-managed-config>` and also sets `KUBECONFIG` to that same file. Passing another `--kubeconfig` through `harr kubectl` is rejected; change the managed source with `configure`/`sync` instead.

This is the real kubectl, so Kubernetes behavior is not limited by an MCP tool catalog: deletions, patch/apply, exec, logs, port-forward, rollout, drain/cordon, binary data and future kubectl operations keep their native semantics.

## Sync and status

`configure` records the original kubeconfig path list and kubectl executable. After the user's normal kubeconfig changes, refresh the Harr copy from a terminal that can still read the source:

```text
harr kube sync
```

Inspect the managed route without printing credentials:

```text
harr kube status
```

Status reports the kubectl path, managed config path, current context/cluster/server, whether auth is portable or exec-helper based, and a bounded cluster reachability check. Use `harr kube status --no-check` for local metadata only.

## Routing discipline

For cluster investigation prefer focused commands over broad context-heavy dumps:

```text
harr kubectl get pods -n NAME -l app=NAME
harr kubectl logs POD -n NAME --tail=100
harr kubectl get RESOURCE NAME -n NAME -o yaml
```

Use `-A`, large YAML/JSON dumps, or unbounded logs only when they are genuinely required. LeanCTX can compact shell output, but avoiding unnecessary output is cheaper than compressing it later.

## Rollback

Harr Kubernetes state participates in clean ownership. On Windows the `harr\kubernetes` directory is an explicit rollback item; on Linux/macOS it is contained in the Harr config-root snapshot. `harr uninstall` therefore restores/removes the Harr Kubernetes snapshot consistently with the rest of the global harness.
