# Harr 0.3.11

Harr 0.3.11 lets global OpenCode and ZCode sessions start LeanCTX without a project directory. The default `auto` authority mode starts rootless when no explicit project root is supplied, so startup does not trust a host's global working directory. File and path tools remain unavailable until LeanCTX is restarted or reconnected with an explicit primary project root.

The Harr Workspace control plane can register folders explicitly supplied by the user, including multiple worktrees from the same repository. Workspace owner notes warn when another task has claimed a checkout and require the user's confirmation before transferring that note.

Harr pins LeanCTX 3.11.0 Harr build 8, which provides immutable rootless/workspace authority modes, capability validation, multi-root access, and the low-memory incremental Cargo build helper. The release workflow verifies the pinned LeanCTX binary and MCP tool surface before building Harr packages and checksums.
