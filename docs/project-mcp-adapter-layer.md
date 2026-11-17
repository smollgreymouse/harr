# Project-scoped MCP adapter layer

Status: verified contract (stage 4 of docs/project-mcp-adapters-execution-plan.md)

This revision replaces the earlier canonical-adapter proposal. The verified
LeanCTX gateway contract (stage 1) makes a normalizing adapter layer unnecessary:
each provider instance already exposes its **native** tool surface under a
qualified name, with lazy launch and per-instance routing. A common semantic
API across providers is **explicitly not a goal of this layer**; a semantic
facade may exist later as a separate, clearly named layer on top.

Evidence for every runtime property referenced below:
`docs/mcp-adapter-gate-evidence.md` (stage 1),
`docs/mcp-adapter-provider-matrix.md` (stage 2), stage 3 notes in
`docs/mcp-adapter-gate-evidence.md` (secret store). Unverified properties are
marked **BLOCKER** and must not be presented as supported behavior.

## Problem

Harr has a global MCP catalog, a global selection, and one generated effective
registry:

```text
common/mcp/registry.json
        |
        v
~/.config/harr/mcp-selection.json
        |
        v
~/.config/harr/mcp-registry.json
        |
        v
LeanCTX gateway ([[gateway.servers]])
        |
        +-- codegraph, gitlab, grafana, kibana, jira, redash ...
```

That works while a logical integration has exactly one Harr-selected
implementation and one global credential. It breaks when a project needs a
second instance of the same vendor (e.g. GitLab official remote MCP next to the
Harr-managed zereight server), a project-specific endpoint, or its own MCP.

## Verified gateway contract (stage 1)

Measured on deployed LeanCTX `3.11.0-harr-unified.7` (`rust/src/core/mcp_catalog/`):

1. **Lazy launch.** A cold MCP session starts zero upstream processes; the plain
   `tools/list` surface is static (`ctx_*` tools only). Upstreams start only
   when the agent touches the gateway.
2. **Qualified native names.** The catalog namespaces each downstream tool as
   `<instance>::<tool>`; handles are collision-free deduplicated by the
   catalog. Names, descriptions and arguments pass through unmodified; the
   gateway never renames a native tool.
3. **Per-instance routing.** `ctx_tools call <instance>::<tool>` resolves the
   instance config, opens/uses exactly that instance's pooled session, and
   never falls back to another instance or credential. Unknown or disabled
   instance -> error. A downstream failure surfaces verbatim; calls are never
   auto-retried (non-idempotent tools).
4. **Discovery fan-out (accepted cost).** `ctx_tools find`/`list`/`refresh`
   build the catalog by connecting to every enabled instance once per TTL
   (default 300 s, single-flight). The project overlay therefore controls the
   enabled set; per-instance laziness is guaranteed on the direct-call path.
5. **Dynamic refresh.** TTL cache + `ctx_tools refresh` (`catalog::invalidate()`
   clears cache and session pool). Config is re-read per `ctx_tools` action, so
   enable/disable changes apply to live sessions on the next action; secret
   *values* are process-start env (`LEAN_CTX_SECRET_*`) and require a new
   session (documented limitation).
6. **Secret discipline.** Gateway config stores memento ids only;
   `resolve()` is fail-closed (missing memento -> instance unavailable, error
   surfaced); pool identity uses blake3 fingerprints (rotation changes the
   pool key); HTTP secret headers are marked sensitive; debug renders redact.

Known gaps (BLOCKER until closed, additive upstream work):
full `inputSchema`/`annotations` are not visible to the agent (compact
`params` summary only); `structuredContent`/images are flattened to text by
`result_to_text`; no downstream `tools/list_changed` propagation.

## Entities

### Provider definition (Harr-owned)

As today in `common/mcp/registry.json`: transport (`stdio` via the Harr runner,
or `http`), runtime, doctor probe, secret metadata (memento id, secret file,
target env/header). Projects never define runtimes or executable commands.

### Provider instance

A named, addressable deployment of a provider definition:

```text
name        unique across the effective registry ("gitlab", "gitlab-official")
provider    Harr provider definition id ("gitlab")
config      non-secret parameters (endpoint, toolsets) — Harr definition or
            user-local profile, never repository-supplied for known providers
profile     credential binding (see below)
source      global-selection | project-overlay | project-extension
```

The instance name is the gateway `[[gateway.servers]]` name and the
`<instance>::` qualifier. Harr validates uniqueness; two instances of one
vendor keep their distinct native surfaces side by side (verified: same-vendor
instances never share a pool session; the pool is keyed by resolved transport).

### Native tool surface

Whatever the instance's `tools/list` actually returns, visible as
`<instance>::<tool>`. Tools missing from one provider stay visible only on the
provider that has them (stage 2: zereight exposes 216 annotated tools; the
official GitLab remote surface is a BLOCKER pending one-time interactive OAuth
— PAT as Bearer/PRIVATE-TOKEN is rejected by `/api/v4/mcp`).

### Credential profile (user-local)

A binding record — no secret bytes:

```text
~/.config/harr/mcp-profiles/<profile-id>.json
{
  "schema": 1,
  "id": "gitlab-official/prod",
  "provider": "gitlab",
  "kind": "http",
  "endpoint": "https://gitlab.example.com/api/v4/mcp",
  "secret": { "file": "gitlab-official-pat", "memento_id": "mcp/gitlab/official" },
  "state": "enabled",
  "bound_projects": ["<project-key>"]
}
```

Properties (stage 3): stable id; separate secret reference; explicit binding
to provider instance/account and one approved endpoint; shared use across
projects only via explicit `bound_projects` entries; rotation = overwrite of
the referenced secret value (atomic tmp+rename), reference unchanged;
`disable` blocks new calls (no export, resolve fail-closed); provider-side
revocation is a separate operation outside Harr; logs carry safe ids and
redacted reasons only.

### Project overlay (committed, untrusted)

`.harr/mcp.json` in the project — the nearest ancestor wins:

```json
{
  "schema": 1,
  "instances": {
    "gitlab-official": {
      "provider": "gitlab-official",
      "profile": "gitlab-official/prod"
    },
    "gitlab": { "enabled": false }
  },
  "extensions": {
    "company-search": { "transport": "http", "url": "https://mcp.example.com/search" }
  }
}
```

Validation is fail-closed. Allowed: select instances of Harr-defined providers;
enable/disable any instance (overlay semantics below); bind a profile by id;
declare `http` extensions after trust. Forbidden: raw secrets or secret paths,
arbitrary commands/args/env, shell fragments, endpoint override for
profile-bound instances (the endpoint comes from the profile), unbound
references to existing user secrets.

Overlay precedence (unchanged from the previous revision):

- global disabled + no project entry -> disabled;
- global disabled + project enabled -> enabled for that project;
- global enabled + project disabled -> disabled for that project;
- global enabled + project selects another instance -> that instance.

## Runtime

The Harr LeanCTX wrapper already launches one gateway process per agent
session and preserves cwd. `exec-leanctx` extends that startup path:

```text
resolve nearest .harr/mcp.json from cwd
        |
        +-- none --------------------> global config as today (byte-identical
        |                              behavior; existing setups keep working)
        |
        +-- overlay present ----------> trust check (digest + user-local approval)
            untrusted ----------------> fail closed: project overlay ignored,
                                        safe ids reported, global defaults only
            trusted ------------------> effective registry =
                                          global selection + overlay instances
                                          + trusted extensions
                                        render session config to
                                          ~/.config/harr/mcp-sessions/<cache-key>/
                                          (LEAN_CTX_CONFIG_DIR override)
                                        export LEAN_CTX_SECRET_* only for secret
                                          ids referenced by the rendered config
```

Cache key = hash(project root, registry digest, overlay digest, profile states,
trust revision). Any instance-config or credential-binding change produces a
new key: new sessions deterministically pick up the change (invalidation by
construction), running sessions honor enable/disable on the next `ctx_tools`
action, and secret-value rotation requires a new session (both documented).

The global generated config keeps its current meaning; `harr leanctx apply` is
unchanged. `run_server` strips `LEAN_CTX_SECRET_*` from child environments so
the real upstream process receives only its own wired credential (defense in
depth on top of the gateway's per-wiring `secret_env`/`secret_headers`).

## Trust model

Project MCP configuration is repository-controlled input — executable
capability configuration even without shell script (endpoints, process
launches).

1. Resolve the nearest project manifest; compute a digest of the effective
   project MCP configuration; look up a matching approval in user-local state
   (`~/.config/harr/projects/<project-key>/trust.json`); digest change -> untrusted
   until explicitly approved. Trust never lives in the repository.
2. HTTP endpoints: HTTPS required (plain HTTP only for explicit loopback
   exceptions). Profile-bound instances pin the endpoint; the overlay cannot
   move a credential to a new endpoint because the endpoint travels with the
   profile, not with the repository. Redirects: the pinned endpoint is the
   origin; a redirect must not become a credential carrier — BLOCKER: verify
   the gateway's streamable-HTTP client behavior on cross-origin redirects
   before enabling profile-bound HTTP instances against redirecting servers.
3. Stdio: known providers run only through the Harr runner
   (`harr-mcp-run <name>`) — repository input never becomes a command line.
   Project-owned stdio extensions are out of scope for v1 (they are arbitrary
   code execution; a later schema may allow pinned packages behind explicit
   trust).
4. Credentials flow only to the instance they are bound to: gateway
   `secret_env`/`secret_headers` resolve per server wiring (verified), export
   is scoped to rendered instances (new), child env is sanitized (new), and
   the overlay cannot reference a secret that is not bound through a profile
   the user approved for this project.

## Failure semantics

Fail closed, never fall back:

```text
gitlab-official: authentication required; run: harr mcp auth gitlab-official
gamma: missing secret memento 'mcp/test/missing' for 'GAMMA_TOKEN'
```

A project-selected provider failing does not reroute to the global provider or
another credential — an explicit no-binding means global default, an explicit
binding means exactly that binding (verified in stage 1/2: no retry, no
fallback, verbatim errors, session eviction on broken transport).

## Diagnostics and commands

```text
harr mcp resolve [NAME]          # nearest overlay, effective instances, source
harr mcp project status|trust|revoke
harr mcp profile list|set|disable|enable   # user-local credential bindings
harr secret set|unset|status     # secret values (rotation), unchanged UX
```

Diagnostics never contact or authenticate to providers and never print secret
material.

## Explicitly out of scope for this layer

- A common semantic API across providers (no canonical tool mapping, no
  renames, no argument/result transforms). If a facade is ever needed it will
  be a separate, clearly named layer above native surfaces.
- Per-tool routing across instances (reserved for a later schema; whole-instance
  selection first).
- Project-owned stdio extensions (arbitrary code execution).
- OAuth acquisition UX for the official GitLab remote MCP — BLOCKER: needs the
  interactive browser flow (`lean-ctx addon auth`); headless PAT auth is
  rejected by the endpoint (stage 2).

## Implementation phases

1. Overlay resolution + validation + trust state (fail-closed, no runtime yet).
2. Session effective registry + per-session gateway render + scoped secret
   export + child env sanitization.
3. Profile store + binding validation + atomic rotation.
4. Diagnostics commands + acceptance tests (stage 6 of the execution plan).

## Tests required (stage 6)

1. Two instances of one vendor enabled together keep distinct tool sets.
2. Different providers keep distinct schemas/results; a missing tool is not
   masked by a stub.
3. Cold start starts no upstream; discovery starts only the enabled set; a
   direct call reaches exactly the addressed instance (same session reuse).
4. Overlay with unknown instance, name conflict, inline secret, or unapproved
   endpoint is rejected.
5. A credential from profile A never reaches instance B — including 401/403,
   timeout, or same-domain cases.
6. Rotation and disable invalidate the session config (new cache key) and
   leave no secrets in logs, diagnostics, or serialized overlays.
7. No project overlay: global configurations keep working unchanged.
