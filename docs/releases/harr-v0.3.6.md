# Harr 0.3.6

Harr 0.3.6 updates the bundled and installer-pinned LeanCTX to `harr-v3.11.0-unified.6@aeffa81f7242`, built from the merge of LeanCTX PR #17. The release workflow verifies the published archive SHA-256 and the embedded Harr build identity before packaging.

LeanCTX `unified.6` makes `ctx_shell` reject an explicit working directory outside the registered Harr Workspace without executing the command or silently registering a new root. It also carries the completed Workspace/worktree hardening, Windows canonical-root fixes, queued progress delivery fix, vulnerable dependency updates, strict ZIP-entry validation, and the associated regression coverage.

Harr's Codex orchestration remains **opt-in and disabled by default**. When enabled, Asa is now one persistent architect for the root conversation. The same Asa handles automatic material-architecture decisions and explicit user dialogue routed through the Luna root. Every Asa invocation remains evidence-first: root owns root-scope discovery, Worker/Ein-owned evidence crosses as a compact handoff, Asa does not broaden into repository discovery, and later calls carry only verified evidence deltas learned after the initial full-history fork. The contract requires stock Multi-Agent V2 and explicitly avoids a lossy V1 fallback.

The persistent Asa lifecycle uses a stable child identity, reuses an existing legacy Asa when one is already present, waits for actual child completion before treating a request as answered, and preserves separate request modes for architecture decisions, user dialogue, and explicit deep analysis.

Named Ein execution is now specified as a root-owned MCP executor transport rather than a Codex agent. The same Ein session retains ownership across escalation and correction, material design escalations route back through root and the same persistent Asa, and terminal handoffs include bridge-generated workspace provenance so root can distinguish verified workspace state from executor-reported claims. Failed/cancelled/time-limited runs explicitly preserve the possibility of partial edits.

The release retains the existing harness controls: orchestration stays independently enable/disable-able, sequential implementation remains in the Luna root, native workers are reserved for genuinely independent parallel scopes, and Harr does not modify Codex core.
