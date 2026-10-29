# Harr icon on the existing managed LeanCTX

The original root `harr.png` is copied without image changes to `common/mcp/assets/harr.png` in the installed Linux, macOS and Windows runtime. Its SHA256 is `0a601b2145d1bdbc9e987cb1da61663ce543e610e3d082ae5a1d1169ceaa007e`.

`common/mcp/manager.py::exec_leanctx` resolves this path relative to its installed module and passes `HARR_MCP_ICON_PATH` to the existing MCP launch. LeanCTX's `rust/src/server/server_handler.rs` uses one implementation helper for both `get_info` and explicit `initialize`. It reads at most 2 MiB, checks the PNG signature, encodes a data URI and returns it through `serverInfo.icons`. An absent or invalid sidecar preserves normal startup. Tool names, schemas, routing and the existing server registration are unchanged. Repeating a one-megabyte image in each `tools/list` entry is avoided.

In the inspected Codex source snapshot `60adfa8513f77c27826f0c5b770e7a7d4eca538e`, `codex-rs/codex-mcp/src/rmcp_client.rs` preserves received implementation icons, `codex-rs/protocol/src/mcp.rs` includes server/tool icon metadata, and `codex-rs/app-server-protocol/schema/typescript/v2/McpServerStatus.ts` transports the server information and tool catalog.

The available `codex-desktop` checkout contains the Rust CLI/app-server tree, not the complete chat frontend. Its generic call item carries server/tool identity, which could allow a renderer to look up icons in the catalog. The exact frontend icon-selection component could not be established. Protocol support alone therefore does not confirm visible branding beside chat calls.

The installed release supplies the metadata for visual verification in the normal Desktop client. If its renderer ignores these fields, the minimal client change is to resolve the selected tool's icon, then server icon, from the existing MCP status catalog, retaining the generic fallback. No extra LeanCTX connection is required. No Desktop fork or installed ASAR modification is included; ordinary client updates may change rendering support without affecting Harr's standard metadata.

Checks cover the original asset hash, installer copy paths, manager environment handoff, optional/invalid metadata, initialize serialization, named executor policy, and the single managed LeanCTX registration. Release acceptance also runs the real gateway lifecycle regressions. Visual display remains a separate user check after refreshing the client connection.
