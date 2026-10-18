# LeanCTX workspace baseline: isolated first run (2026-10-14)

**Status: partial empirical baseline, NOT Phase 0 complete. No product code modified.**

## Environment and isolation

- Actual installed vendor binary: LeanCTX **3.11.0** (Harr build `harr-v3.11.0-progress.2@5f1cffb7b66c`), invoked **directly**, not through Harr's working MCP wrapper.
- Used `bubblewrap` (`--die-with-parent --unshare-net`) with read-only system binaries/libraries, no mounted production HOME, project directories or Codex/Harr registry; mounted a new, temporary fixture with synthetic `repo-a`, `repo-b`, `repo-outside`.
- Separate HOME, `LEAN_CTX_DATA_DIR`, XDG config/data/cache, TMPDIR. MCP stdio server launched inside a container with `cwd=/fixture/repo-a`. Client used `initialize` → `notifications/initialized` → `tools/list` → `tools/call` with actual JSON-RPC messages.
- No working MCP daemon/CTUN endpoint was called/restarted or reconfigured, no working project path visible to test process. Test fixtures reside in `mktemp` directories and contain only synthetic marker files. The test uses a binary read-only bind mount.

## Initial findings

| Sandbox env | `ctx_tree(path=/fixture/repo-b)` | `ctx_search(query=marker_only_b,path=/fixture/repo-b)` |
|---|---|---|
| Neither `ALLOW_PATH` nor `EXTRA_ROOTS` | **Denied**: `path escapes project root` | **Denied**: `path escapes project root` |
| `LEAN_CTX_ALLOW_PATH=/fixture/repo-b` | **Allowed**: lists `unique-b.txt` | `ERR: source path is outside the request authority` (not successful search) |
| `LEAN_CTX_EXTRA_ROOTS=/fixture/repo-b` | **Allowed**: lists `unique-b.txt` | `ERR: source path is outside the request authority` (not successful search) |

Interpretation: baseline `ctx_tree` PathJail behavior and acceptance of both environment overrides are empirically established. The search error may be due to a separate request authority or tool argument handling; **we do not yet know its root cause**. Do not infer that `allow_paths` and `extra_roots` have equivalent index/search behavior.

## Reproduce safely

```bash
LEANCTX_TEST_BIN=/absolute/path/to/real/lean-ctx python3 tests/workspace-baseline/probe.py default
LEANCTX_TEST_BIN=/absolute/path/to/real/lean-ctx python3 tests/workspace-baseline/probe.py allow
LEANCTX_TEST_BIN=/absolute/path/to/real/lean-ctx python3 tests/workspace-baseline/probe.py extra
```

**Safety requirements:** binary must be an actual ELF executable, not the installed Harr wrapper; this is a research harness rather than a production smoke test. The runner creates fresh fixtures, uses bubblewrap to hide the host HOME and unshares networking. Examine the bwrap command before adapting to another OS. Never use real repositories or mount live data roots into this container. Test fixture outputs are retained for inspection.

## Before implementation

1. Debug `ctx_search` request authority vs PathJail and compare explicit path with default multi-root search and `ctx_read`, semantic search and index scope.
2. Complete `read_only_roots`, `linkedProjects`, `roots/list`, session persist/reload, concurrent sessions, symlink/traversal and live-config-reload tests.
3. Add machine-enforced guard assertions for isolation and verify reproducibility over repeated runs.
4. Record baseline expectations and actual outputs; **only after the Phase 0 gate** design/implement the LeanCTX live-session workspace API.

## Root cause confirmed in LeanCTX source (2026-10-14)

**This is not a single PathJail failure. There are TWO independent authorization boundaries.**

1. `rust/src/core/path_resolve.rs::resolve_tool_path_with_roots` calls `pathjail::jail_path_with_roots` using `project_root` plus trusted `extra_roots`; global `LEAN_CTX_ALLOW_PATH` is also accepted by PathJail. Consequently, the actual MCP `ctx_tree` succeeded on `repo-b` under both env overrides.
2. `rust/src/server/call_tool/guarded.rs` starts a request-local `REQUEST_PROJECT` scope from `session.project_root` and binds it after `resolve_roots_once()`.
3. `rust/src/tools/ctx_semantic_search/scope.rs::resolve_search_root` canonicalizes the requested search directory and rejects it unless it `starts_with(REQUEST_PROJECT)`, returning **`source path is outside the request authority`**. It does not consult authorized `extra_roots` here.
4. Existing test `rust/src/tools/ctx_semantic_search/tests.rs::request_authority_still_rejects_another_projects_path` asserts this behavior. Thus it is deliberate defense-in-depth, not a transient cache error. Our multi-root design must extend this policy *explicitly*, preserving rejection of all unapproved sibling projects.

**Design consequence:** Do not remove the `REQUEST_PROJECT` scope or fall back to unbound search authority. Introduce a per-request, immutable `SourceAuthority { primary, authorized_search_roots }` (or equivalent), derived from the **trusted, session-scoped** effective workspace snapshot. In `resolve_search_root` select the specific canonical authorized root containing the target path and maintain subdirectory filtering; `allow_paths` alone should *not* become search authority just because PathJail allows reading it. Treat `read_only_roots` according to explicit indexing policy, never as writable. Any search/index/cache scope must be keyed or filtered to the authorized root set. The current single-project authority should remain intact for non-workspace calls.

**Required pre-change tests:** actual MCP `ctx_tree`, `ctx_read`, `ctx_search` and semantic search over A/B; `allow_paths` alone vs `extra_roots`; unauthorized C; nested directory and symlink escape; intentionally conflicting read-only; two sessions with different roots on the same server; removing B while index is warm. Add focused Rust tests around authority selection and the existing `request_authority_still_rejects_another_projects_path` to prove rejected foreign roots remain rejected. No production server modification while establishing this test matrix.
