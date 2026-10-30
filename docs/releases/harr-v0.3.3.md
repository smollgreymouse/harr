# Harr 0.3.3

Harr 0.3.3 is a focused Codex memory-routing hotfix on top of Harr 0.3.2. It keeps the pinned LeanCTX build `harr-v3.11.0-unified.4@afc9715d6d5a`.

Codex-owned memory under `$CODEX_HOME/memories/` or `~/.codex/memories/` is now explicitly treated as host memory outside Harr workspace authority. Memory lookup no longer routes through LeanCTX, CodeGraph-first, or workspace read/search rules.

When additional memory evidence is required, the generated Codex policy permits only bounded host-native reads: `rg -n -m 20` against the specific memory file followed by `sed -n START,ENDp` for the identified range. Python one-liners, `Path.read_text`, shell scripts, and broad workspace-style fallback reads remain disallowed.

The exception is narrowly scoped to Codex memory. Workspace code, configuration, and documentation continue to use Harr LeanCTX routing and the existing PathJail rules.

Regression coverage in `tests/clean-harness.sh` verifies the generated Codex policy contains the memory exception, keeps workspace routing intact, and forbids Python-based bypasses.
