---
name: lean-ctx
description: LeanCTX-specific troubleshooting/reference on a Harr-managed machine: minimal ctx_* surface, gateway semantics, cwd/project binding, secret handling, and repair. Do not load for normal repository investigation; global Harr policy already defines tool order.
---
<!-- harr-managed-skill-v1 -->

# LeanCTX under Harr

Use this skill only for LeanCTX-specific behavior or failures. Normal tool routing is already injected into the host's global `AGENTS.md` by Harr.

Harr owns LeanCTX and currently pins the Harr progress-aware LeanCTX 3.11.0 build. Do not run upstream `lean-ctx setup`, `lean-ctx onboard`, or `lean-ctx update`.

Direct Harr profile:

- `ctx_read`
- `ctx_shell`
- `ctx_search`
- `ctx_glob`
- `ctx_tools`
- `ctx_call`

Use `ctx_call` only for a known, non-editing uncommon capability; do not use it to discover edit/patch tools. Editing stays native; `ctx_edit`/`ctx_patch` are disabled.

Investigation routing:

- For text/content lookup use `ctx_search`; for filenames use `ctx_glob`; then use `ctx_read` with a narrow range. Prefer these over shell equivalents such as `rg`, `grep`, `find`, `sed`, `cat`, `head`, or `tail`.
- Keep searches and reads bounded. When output is truncated, refine the query or read only the indicated lines instead of requesting the same large result again.
- Reserve `ctx_shell` for real CLI work such as Git, builds, tests, generators, project commands and Harr bridges. Avoid search/read pipelines through `ctx_shell` when native `ctx_*` tools fit.
- If shell output says LeanCTX blocked a command/segment before execution, report that as a policy rejection. Do not infer execution from trailing diagnostics, weaken shell security, or retry via another shell path. Treat exit 127 / `command not found` as a separate executable-availability problem only for commands that actually ran.

Git routing through `ctx_shell`:

- Local repository operations use one exact `git ...` command.
- Where `harr status` reports a ready host Git service, remote operations use one exact `harr git ...` command; do not attempt bare network Git first.
- Preserve repository cwd. If LeanCTX rejects that cwd because it belongs to another project root, use an allowed cwd and pass `harr git -C /absolute/repository/path ...`.
- GitLab MCP owns API objects such as merge requests, pipelines and users; Git/`harr git` own commits, branches, remotes and every fetch/push. Never mirror local commits through GitLab repository-file tools.
- Diagnose the host bridge with `harr status`; do not alter remotes, `IdentityFile`, `core.sshCommand`, or agent sockets to work around the sandbox.

Gateway facts:

- CodeGraph: stdio child `codegraph serve --mcp`; inherits LeanCTX cwd, so wrong project binding means diagnose cwd/root rather than creating per-project Harr config.
- GitLab: on-demand stdio child; PAT is restored by Harr's LeanCTX wrapper via secret-memento env and must never be printed.

Repair/diagnostics:

```bash
harr status
harr leanctx status
harr leanctx apply
harr install all
```
