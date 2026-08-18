# Git MCP in Harr

Git MCP is the specialized route for repository-state and Git transport operations.

## Normal route

Use `git-mcp` **through the LeanCTX gateway** so its tool catalog stays hidden behind `ctx_tools` until needed.

Harr installs the official `mcp-server-git` package. The Harr launcher inherits LeanCTX cwd, resolves the repository root with `git rev-parse --show-toplevel`, changes to that root, and launches the server restricted with `--repository <root>`. No project-level Harr config is required.

Use `repo_path="."` in normal Git MCP calls.

Use Git MCP for status/working-tree state, branches and checkout/switch, history/commits, remotes, fetch/pull/push and other Git-native operations.

A direct Git MCP registration is only a diagnostic bypass when the gateway route is broken.

Do not use GitLab MCP for local Git operations merely because the repository is hosted in GitLab: GitLab MCP answers GitLab API questions; Git MCP operates the repository/Git protocol.

For a normal coding task:

```text
CodeGraph -> missing LeanCTX reads -> native edit -> Git MCP as needed
```

Use Git history earlier only when the task specifically depends on why/when code changed, blame/history, branch state or a remote change.
