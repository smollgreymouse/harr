# Harr 0.3.8

Harr 0.3.8 fixes Workspace checkout identity verification and updates the bundled and installer-pinned LeanCTX to **`harr-v3.11.0-unified.7@4fe3b6b884ee`**.

LeanCTX unified.7 introduces Workspace metadata schema v2: old schema-v1 checkout-generation metadata is rejected during normal reads and is rebuilt only through explicit Workspace reconciliation from the currently registered live roots. Unknown future schemas and corrupt metadata remain fail-closed. Harr now verifies checkout generation using the same stable Git administrative marker semantics as LeanCTX for both primary repositories and linked worktrees.

This release preserves the package-upgrade self-repair path introduced in 0.3.7, so package-managed Harr refreshes its LeanCTX runtime and launchers without requiring manual sidecar edits. Asa/Ein orchestration remains opt-in and disabled by default.

The complete CI release is intended to publish Linux, macOS and Windows artifacts once GitHub Actions account limits permit hosted workflows again. The initially published Linux package is built locally with the same pinned LeanCTX release and single-job build constraints.
