# Harr 0.3.5

Harr 0.3.5 packages the current post-0.3.4 master fixes together with the new economical Codex orchestration layer from PR #47.

The Codex orchestration feature is **opt-in and disabled by default**. When disabled, Harr does not install the `$asa` skill or `asa-architect` role, does not inject worker/Asa orchestration routing into Codex policy, and does not add the Asa skill path to LeanCTX. Enable it explicitly with `harr agents orchestration enable`; disable it again with `harr agents orchestration disable`.

When enabled, sequential implementation remains in the root; native workers are reserved for genuinely independent parallel scopes. Unresolved material architecture decisions route through the configurable `asa-architect` role, while the root remains the sole agent router. A worker that escalates a material decision retains ownership of its scope and resumes after the decision instead of being replaced.

The release also retains the current master improvements after 0.3.4, including Codex Ein completion notifications, package-upgrade runtime consistency, status read-only behavior, Codex memory routing, and Windows Ein transport portability fixes.

Named Ein executors remain explicit delegation targets. Their shared workflow skill is now `$ein`; legacy Harr-managed `$einherjar-worker` skill installations are migrated away without enabling orchestration.

LeanCTX remains pinned to `harr-v3.11.0-unified.4@afc9715d6d5a`.
