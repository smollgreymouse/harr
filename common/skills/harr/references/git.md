---
# Host Git transport

Harr's host Git bridge makes remote Git inside an isolated agent behave like Git in the user's terminal. The sandbox client sends only the working directory and Git argument vector to a loopback-only authenticated service. The service runs the real `git` process in the user session, where the normal SSH agent, SSH configuration, known-hosts files, Git configuration, and credential helpers are available.

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

## GitLab merge-request boundary

Git uses the user's terminal SSH agent or credential helper. The stored GitLab PAT authenticates GitLab MCP API calls only.

Before creating an MR:

1. Read the current named local branch with `git symbolic-ref --quiet --short HEAD`; reject detached HEAD and source=target.
2. Read local `HEAD` with `git rev-parse HEAD`.
3. Push with `harr git push --set-upstream <remote> HEAD:refs/heads/<current-branch>`.
4. Read the exact remote ref with `harr git ls-remote <remote> refs/heads/<current-branch>` and require its SHA to equal local `HEAD`.
5. Verify the current branch tracks the same-named remote branch.
6. Create and verify the MR through GitLab MCP.

Never use an implicit push, GitLab `create_branch`, `create_or_update_file`, `push_files`, or repository-file mirroring to upload a local commit.

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
