# LeanCTX in Harr

LeanCTX is Harr's context/repository access layer and one gateway route for downstream MCPs.

## Direct surface

Harr intentionally advertises only:

- `ctx_read`
- `ctx_shell`
- `ctx_search`
- `ctx_glob`
- `ctx_tools`
- `ctx_call`

Do not assume other LeanCTX tools are directly exposed. Discover/invoke rarer capabilities through `ctx_call` rather than expanding the agent's permanent MCP surface.

Editing stays outside LeanCTX; use the host's native editor.

## Primary uses

Use LeanCTX directly for:

- reading known files or exact implementation regions;
- exact-text/repository search;
- file discovery;
- shell/test commands when repository shell access is needed;
- calling downstream gateway tools when that route is selected by Harr policy.

For structural code understanding, symbol relationships, architecture, or blast radius, Harr policy chooses CodeGraph first rather than broad LeanCTX search/read.

## Gateway

Current gateway responsibilities include:

- CodeGraph fallback/compatibility route over stdio;
- GitLab MCP over Streamable HTTP.

The gateway is not the universal preferred route for every MCP. Harr's top-level routing policy decides whether a direct MCP or gateway route is primary.

## Ownership

Harr owns the LeanCTX installation, pinned version, wrapper and config. Do not run upstream `lean-ctx setup`, `lean-ctx onboard`, or `lean-ctx update` on a Harr-managed machine.
