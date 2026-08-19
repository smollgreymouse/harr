# Common Harr sources

Platform-independent Harr assets live here: routing policy, host adapters/config writers, diagnostic skills, LeanCTX base configuration, and the MCP registry.

`common/mcp/registry.json` is the extension point for Harr-managed MCPs. It declares transport, lifecycle, runtime/package, local env template and secret-memento routing once. Linux and Windows consume the same registry; platform directories own only installation, process/service lifecycle, wrappers and paths.

Adding an ordinary MCP must not require editing every platform installer. Add its registry entry and shared env/docs/policy material; platform overrides are only for genuinely platform-specific behavior.
