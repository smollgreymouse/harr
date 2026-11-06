# Harr 0.3.7

Harr 0.3.7 retains all the orchestration and root-owned Ein/Asa changes from 0.3.6, and updates the bundled and installer-pinned LeanCTX to **`harr-v3.11.0-unified.6@aeffa81f7242`** (LeanCTX PR #17, merged into main).

The LeanCTX update rejects an unregistered explicit `ctx_shell` working directory without executing a command or silently widening the Workspace; it supports an explicit Workspace recovery path. It also includes the hardened Git worktree identity checks, Linux/Windows path and lifecycle fixes, queued MCP progress delivery and dependency security updates verified by CI.

The pinned LeanCTX release ships binary archives for Linux x86_64/aarch64 (GNU and musl), Windows x86_64, and macOS Intel/Apple Silicon. The Harr release job verifies SHA256, the exact LeanCTX `--version` build ID and the real MCP stdio icon/tools acceptance before packaging.

Asa/Ein Codex orchestration **remains opt-in and disabled by default**. Harr does not install a second standalone CodeGraph/LeanCTX gateway or turn on agent features automatically.
