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
