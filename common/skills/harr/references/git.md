---
# Host Git transport

Harr's Linux host Git bridge makes remote Git inside an isolated agent behave like Git in the user's terminal. The sandbox client sends only the working directory and Git argument vector to a loopback-only authenticated service. The service runs the real `git` process in the user session, where the normal SSH agent, SSH configuration, known-hosts files, Git configuration, and credential helpers are available.

No project-specific key policy is needed. Do not configure an `IdentityFile` in Harr, copy private keys into the sandbox, expose the real agent socket, rewrite repository remotes, or set `core.sshCommand`.

## Command selection

Use ordinary local Git through `ctx_shell`:

```text
git status --short --branch
git diff --check
git log -n 10 --oneline
git add <paths...>
git commit -m <message>
```

Use host Git for commands that can contact a remote and should inherit terminal authentication:

```text
harr git clone git@github.com:owner/repository.git
harr git fetch origin
harr git pull --ff-only
harr git push origin HEAD
harr git ls-remote origin
harr git remote update
harr git submodule update --init --recursive
harr git lfs pull
```

The bridge preserves cwd. If the target repository is outside the active LeanCTX project root, keep `ctx_shell` in an allowed directory and use Git's global `-C` option:

```text
harr git -C /absolute/repository/path fetch origin
harr git -C /absolute/repository/path push origin HEAD
```

Arguments after `harr git` are passed directly to Git. Do not add a `--` before normal Git options.

## GitLab identity choice

`harr git` and `harr gitlab ...` are intentionally different authentication routes:

- `harr git ...` uses the user's terminal SSH agent or credential helper.
- `harr gitlab fetch/publish/push` uses Harr's stored GitLab PAT over HTTPS.
- GitLab MR source publication uses `harr gitlab publish` because it also enforces the current-branch refspec and verifies the remote SHA.

Preserve the route chosen by the user or required by the workflow. Never silently fall back from one identity to the other.

## Diagnostics

Run:

```text
harr status
```

Healthy SSH-backed output contains:

```text
host-git-service   ready (ssh-agent: available)
```

Interpret failures precisely:

- `service unavailable`: the loopback host service is not reachable. Repair/reinstall Harr from the user's normal terminal with `harr install all`.
- `ssh-agent: unavailable`: the service is running but its user-session environment has no usable `SSH_AUTH_SOCK`. Start/unlock the user's normal SSH agent, then re-run Harr installation from that terminal so the service manager imports the environment.
- Git exits nonzero with an SSH or credential error while the service is healthy: diagnose the same remote, SSH config, key loading, account access, or host-key issue as in the user's terminal. Do not bypass it by injecting a different credential.

Never report a remote operation as successful unless `harr git` exits zero. A push still requires the same explicit user authorization as any other remote write.
