# Direct Git MCP in Harr

A direct Git MCP is the preferred route for repository-state and Git transport operations when Harr exposes one to the agent host.

## Use it for

- status and working-tree state;
- branches and checkout/switch operations;
- local history and commits;
- remotes;
- fetch/pull/push;
- other Git-native operations.

Do not send these operations through GitLab MCP merely because the repository is hosted in GitLab. GitLab MCP answers GitLab API questions; Git MCP operates the repository and Git protocol.

## Interaction with code investigation

Git MCP is not the first tool for understanding code structure. For a coding task:

```text
CodeGraph -> LeanCTX as needed -> native edit -> Git MCP as needed
```

Use Git history earlier only when the task specifically depends on why/when code changed, blame/history, branch state, or a remote change.
