# Harr 0.2.9

This release combines the completed runtime features on master, including Redash, named Einherjar executors, worker lifecycle and panel reliability, and the updated LeanCTX gateway.

Einherjar replaces the standalone GigaCode MCP. Each explicitly configured instance exposes `<instance-name>::ein`; GigaCode remains an internal backend alongside the other adapters. Multiple named instances remain supported. All generated policies and the shared worker skill require a direct user instruction before delegation, including when only one instance is configured.

If no named instances exist yet, configure them with `harr ein configure`. Harr does not automatically create or select an executor. A migrated GigaCode instance named `gigacode` retains the legacy session cache; other existing named instances retain their own namespaces.

The LeanCTX update includes connection coalescing, session liveness detection, cancellation-safe in-flight accounting, watchdog and orphan cleanup fixes, and fixture corrections. It preserves the existing managed connection and tools.

The original Harr raven is installed as a portable sidecar and advertised through standard MCP `serverInfo.icons` by the main managed LeanCTX. No duplicate server or branding-only MCP App is created. Metadata transport is covered by automated checks; whether the icon appears beside ordinary tool calls depends on the Desktop renderer and still requires visual verification. See [the implementation and compatibility notes](https://github.com/smollgreymouse/harr/blob/harr-v0.2.9/docs/harr-mcp-icon.md).

Debian and portable Linux packages include the pinned LeanCTX binary. `SHA256SUMS` covers the downloadable packages. Install Harr, then run `harr setup --harr-only` as the normal user to refresh the managed runtime and host instructions while retaining the saved MCP selection and named instances.
