# Harr 0.3.0

Harr 0.3.0 introduces **Harr Doctor**, a new top-level operational surface for proving and repairing the Harr-managed path end to end.

`harr doctor` validates installed provenance, the managed LeanCTX launcher and configuration, Codex/OpenCode host routing, secret presence without revealing values, selected runtime readiness, downstream MCP catalogs, a fresh isolated LeanCTX gateway, and registry-declared read-only health probes. Focused checks such as `harr doctor gitlab` are supported, together with `--local`, `--json`, `--verbose`, and `--strict`.

The initial repair surface is deliberately conservative. `harr doctor --repair --dry-run` exposes the plan without mutation. Harr 0.3.0 performs only deterministic Harr-owned R1 repairs with private snapshots, rollback, and post-repair verification. Credential mutation is never automatic. Targeted runtime reinstall (R2) and stale LeanCTX child refresh (R3) remain fail-closed as `BLOCKED` and are tracked explicitly in `docs/HARR_DOCTOR_DEFERRED.md`.

This release also adds install provenance under the managed Harr runtime so Doctor can distinguish package/source installation state from whichever source checkout happens to be open. Legacy 0.2.x installations without a provenance manifest are reported as WARN rather than FAIL until setup is run with the Doctor-enabled release.

The Harr skill now prefers Doctor for installation/runtime/MCP failures and explicitly forbids automatic repair unless the user has asked to repair, restore, fix, or recover the system.

The release retains the 0.2.9 named Ein architecture: standalone GigaCode is retired, named `<instance>::ein` workers remain opt-in, and delegation still requires a direct user instruction. The pinned LeanCTX build remains `harr-v3.11.0-unified.2@6d033320d263`.

Validation for this release includes Linux, macOS and Windows selftests, Doctor contract tests, clean takeover/rollback tests, MCP registry and selection tests, and a real read-only Doctor smoke on the current installation. That live smoke produced 48 PASS / 0 FAIL and successfully exercised GitLab `health_check`, Grafana `user_info`, Kibana `list_data_views`, Jira `jira_get_all_projects`, CodeGraph catalog discovery, and named Ein catalog routing.

Debian and portable Linux packages include the pinned LeanCTX binary. `SHA256SUMS` covers downloadable packages. After upgrading from 0.2.9, run `harr setup --harr-only` as the normal user to refresh the managed runtime and write the new install provenance manifest while preserving the saved MCP selection, secrets, and named Ein instances.
