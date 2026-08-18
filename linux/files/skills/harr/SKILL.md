---
name: harr
description: Primary tool-routing and orchestration policy for repository work on a Harr-managed machine. Use first to decide which MCP/tool to call, route preference, fallback order, and when to load component references; also covers Harr stack diagnostics.
---
<!-- harr-managed-skill-v1 -->

# Harr — harness routing policy

Harr owns not only installation/lifecycle, but also the **interaction contract between tools**. For repository work, this skill is the source of truth for tool selection and ordering.

Do not infer routing from an individual component skill. Component documentation explains that component; Harr decides **what comes first, which route is primary, and what is only a fallback**.

## Routing table

| Intent | Primary | Fallback / next step |
|---|---|---|
| Understand symbols, references, callers, architecture, dependencies, blast radius | **CodeGraph first** | CodeGraph through alternate Harr route; then LeanCTX only for missing exact text/context |
| Read a known file/range, exact text search, file discovery, repository shell/test command | **LeanCTX** | native host tool only if LeanCTX is unavailable/inapplicable |
| GitLab MR/pipeline/job/issue/project/server state | **GitLab MCP** via normal Harr route | direct GitLab route only when configured/needed as fallback or diagnosis |
| Git status, branches, checkout, history, remotes, fetch/pull/push/commits | **direct Git MCP** | native Git only if the MCP route is unavailable and policy permits it |
| Edit files | **native host editor** | do not route edits through LeanCTX in the Harr profile |
| Harness install/version/service/secret/config repair | **Harr CLI** | read `references/operations.md` |

## Prime rule: CodeGraph first

For a normal code-understanding or implementation task, start with CodeGraph before broad repository reads/searches.

Typical sequence:

```text
CodeGraph
  -> identify relevant symbols/files/relationships
LeanCTX
  -> read/search only what CodeGraph did not already provide
native editor
  -> edit
Git MCP
  -> repository state/history/network operations when needed
```

Do **not** immediately repeat CodeGraph output through LeanCTX. Source text returned by CodeGraph counts as already read.

Skip CodeGraph when the task is inherently an exact lookup with no graph reasoning value, e.g. "read this known config file" or "find this exact string".

## Routes are not separate truths

Harr may expose one logical MCP capability through multiple routes, for example CodeGraph directly and CodeGraph through the LeanCTX gateway.

Treat those as **primary/fallback transports to the same capability**. Do not call both for the same question unless the primary route failed or you are diagnosing routing.

For CodeGraph, prefer the **direct MCP route when Harr has registered it in the host**; use CodeGraph through LeanCTX as the compatibility/fallback route. Both remain CodeGraph-first relative to generic LeanCTX repository search/read.

For GitLab, the normal route is currently through the LeanCTX gateway to Harr's long-lived HTTP GitLab MCP service; a direct GitLab registration may exist as a diagnostic/alternate route.

## Cross-tool workflows

Choose the source closest to the question, then move into code analysis only when needed:

- Pipeline/MR failure: GitLab MCP -> CodeGraph -> LeanCTX exact reads -> edit -> Git MCP.
- Unknown code behavior: CodeGraph -> LeanCTX exact reads -> edit -> Git MCP.
- Exact config/text question: LeanCTX directly.
- Why/when a change happened: Git MCP history/blame first; CodeGraph only if structural impact must then be understood.

## Progressive disclosure

Read only the reference needed for the current task:

- CodeGraph behavior, direct vs gateway, project binding: `references/codegraph.md`
- LeanCTX surface/gateway semantics: `references/leanctx.md`
- GitLab routing/auth/scope: `references/gitlab.md`
- Git repository operations: `references/git-mcp.md`
- Harr install/status/services/secrets/repair: `references/operations.md`

Do not load all references by default.

## Current managed topology

```text
agent host
   |
   +-- direct MCPs managed/registered by Harr (e.g. CodeGraph, Git MCP as added)
   |
   +-- LeanCTX 3.9.15
          |
          +-- stdio -> CodeGraph fallback/compat route
          |
          +-- HTTP -> GitLab MCP :3334 -> GitLab API
```

The inventory may grow. New MCPs belong in Harr's routing policy and references rather than being explained ad hoc in unrelated component skills.
