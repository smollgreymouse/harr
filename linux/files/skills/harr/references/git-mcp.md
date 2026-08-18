# Git MCP in Harr

Git MCP is the specialized route for repository-state and Git transport operations.

## Normal route

Use Git MCP **through the LeanCTX gateway** so its tool catalog stays hidden behind `ctx_tools` until needed.

Use it for status/working-tree state, branches and checkout/switch, history/commits, remotes, fetch/pull/push and other Git-native operations.

A direct Git MCP registration, if Harr provides one, is only a diagnostic bypass when the gateway route is broken.

Do not use GitLab MCP for local Git operations merely because the repository is hosted in GitLab: GitLab MCP answers GitLab API questions; Git MCP operates the repository/Git protocol.

For a normal coding task:

```text
CodeGraph -> missing LeanCTX reads -> native edit -> Git MCP as needed
```

Use Git history earlier only when the task specifically depends on why/when code changed, blame/history, branch state or a remote change.
