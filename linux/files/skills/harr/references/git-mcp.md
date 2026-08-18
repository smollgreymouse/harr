# Git MCP in Harr

Git MCP is the specialized route for local repository-state and Git history/branch operations.

## Normal route

Use `git-mcp` **through the LeanCTX gateway** so its tool catalog stays hidden behind `ctx_tools` until needed.

Harr installs the official `mcp-server-git` package. The Harr launcher inherits LeanCTX cwd, resolves the repository root with `git rev-parse --show-toplevel`, changes to that root, and launches the server restricted with `--repository <root>`. No project-level Harr config is required.

Use `repo_path="."` in normal Git MCP calls.

Use Git MCP for status/working-tree state, diffs, branches/checkout, history/show, staging and commits.

The official reference Git MCP does not expose remote transport tools such as fetch/pull/push. For those operations, use one exact `git fetch`, `git pull`, or `git push` command through LeanCTX `ctx_shell` from the current repository. `git` is in LeanCTX's default shell allowlist; this remains behind LeanCTX rather than adding a direct Git tool surface.

A direct Git MCP registration is only a diagnostic bypass when the gateway route is broken.

Do not use GitLab MCP for local Git operations merely because the repository is hosted in GitLab: GitLab MCP answers GitLab API questions; Git MCP operates local repository state/history; `ctx_shell` handles Git remote transport that the reference MCP does not expose.

For a normal coding task:

```text
CodeGraph -> missing LeanCTX reads -> native edit -> Git MCP as needed
                                      -> ctx_shell git fetch/pull/push when needed
```

Use Git history earlier only when the task specifically depends on why/when code changed, blame/history, branch state or a remote change.
