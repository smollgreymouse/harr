# Windows host Git bridge handoff

## Goal

Make `harr git <git-arguments>` execute Git outside the Windows agent sandbox with the same authentication behavior as Git in the user's normal terminal. Do not add repository-specific key policy, copy credentials into the sandbox, or introduce Harr-specific Git verbs such as `publish`.

This document is a handoff, not evidence that the Windows bridge is feasible. Implementation must wait for tests in a real supported Windows agent sandbox.

## Contract to preserve

- Arguments after `harr git` are passed to real Git unchanged.
- The caller's repository working directory is preserved; `harr git -C <absolute-path> ...` also works.
- Git chooses SSH keys, SSH config, host keys, credential helpers, and HTTPS credentials exactly as it does in the user's terminal.
- The sandbox receives neither private keys nor a reusable GitLab PAT.
- Requests are accepted only from the same local user and authenticated with a Harr-owned capability.
- Stdout, stderr, exit status, timeout, and interruption behavior remain faithful enough for an agent to determine success or failure.
- Harr does not rewrite remotes or global/local Git configuration.

## Required sandbox experiments

Run these on the actual Codex/OpenCode Windows sandbox before selecting a transport:

1. Confirm whether a sandbox process can reach a user process on `127.0.0.1` and record firewall prompts/policy.
2. Confirm whether Windows named pipes are reachable across the sandbox boundary; specifically test the user's OpenSSH agent pipe when present.
3. Start a minimal broker from the normal interactive user session and verify that it can access a repository path also visible to the sandbox.
4. Verify paths with spaces, non-ASCII characters, drive letters, UNC paths, and `git -C`.
5. Verify that the host process sees the same `HOME`/`USERPROFILE`, `.ssh/config`, `known_hosts`, Git config, OpenSSH agent, and Git Credential Manager behavior as terminal Git.
6. Verify non-interactive behavior when a credential helper or SSH asks for UI/input. The broker must fail clearly rather than hang or expose a prompt to another session.
7. Verify exact stdout/stderr bytes and exit codes for success, authentication failure, missing repository, timeout, and cancellation.
8. Verify concurrent read operations and serialize or reject unsafe overlapping writes to the same repository if necessary.
9. Verify loopback authentication, capability ACLs, request-size bounds, cwd validation, executable selection, and rejection of another local user/session.
10. Run real read-only smoke tests against both SSH and HTTPS remotes:

```text
harr git -C C:\path\to\repo ls-remote origin
harr git -C C:\path\to\repo fetch --dry-run origin
harr git -C C:\path\to\repo push --dry-run origin HEAD
```

Do not perform a real push until the user explicitly authorizes that remote write.

## Candidate lifecycle

Prefer a persistent per-user process, not a machine service running as SYSTEM. Evaluate a Scheduled Task started at user logon versus a user-session background process managed by Harr. The selected mechanism must preserve the interactive user's authentication environment and support exact install, status, restart, uninstall, snapshot, and rollback behavior.

Reuse the Linux loopback HTTP protocol only if experiment 1 confirms it is reliable and the same-user boundary can be enforced. Do not assume Windows named-pipe forwarding is safer or available until experiment 2 proves it.

## GitLab migration dependency

Until this handoff is completed, do not claim that Windows can replace the legacy Harr GitLab HTTPS/PAT Git transport with terminal-authenticated `harr git`.

After the bridge passes the experiments, Windows follows the same responsibility split as Linux/macOS:

- Git repository and remote-ref operations: `git` locally, `harr git` for network access.
- GitLab server objects and workflows: GitLab MCP through `ctx_tools`.
- GitLab PAT: MCP API authentication only; never an implicit fallback for Git transport.

## Acceptance test for GitLab MR preparation

Given a named local feature branch with a deliberately stale upstream pointing at the target branch:

1. Read the current branch with local Git and reject detached HEAD.
2. Push with `harr git push --set-upstream <remote> HEAD:refs/heads/<current-branch>`.
3. Read local `HEAD` and the exact remote branch SHA through `harr git ls-remote` and require equality.
4. Verify upstream now names the same remote feature branch.
5. Only then create the MR through `gitlab::create_merge_request` and verify it through the GitLab MCP.

This test must prove that no implicit push can target the stale upstream branch.
