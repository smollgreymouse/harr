# Harr 0.3.10

Harr 0.3.10 expands the host and project orchestration surface while keeping the existing LeanCTX gateway model intact.

ZCode is now a first-class host with native-first routing, persistent Asa saved-workflow support, and optional Z.ai service MCPs for Web Search, Web Reader, and Zread behind LeanCTX. The clean install/rollback contract covers the ZCode policy and configuration paths across supported platforms.

Project-scoped MCP configuration now supports repository-owned overlays and adapter definitions that are merged into the effective LeanCTX gateway for the active workspace. Harr preserves provider metadata and verifies the official GitLab MCP path with a Bearer-token profile. The Harr skill documentation also exposes the project MCP customization workflow.

Workspace lifecycle management gains a safe prune path with locking and contract coverage so stale workspace entries can be removed without racing other workspace operations.

Codex Asa now defaults to `gpt-6.2-sol` at `xhigh` reasoning effort. Existing explicit Asa model settings remain configurable, and the Asa skill itself stays model-agnostic.

This release also carries the package provenance fixes added after 0.3.9, including recorded bundled LeanCTX provenance in the Harr package manifest. The release CI rebuilds and tests the native scheduler, verifies the pinned LeanCTX binary and MCP tool surface, and produces the Harr Debian/tar packages plus checksums.
