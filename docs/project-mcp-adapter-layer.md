# Project-scoped MCP adapter layer

Status: design proposal

## Problem

Harr currently has a global MCP catalog, a global selection, and one generated effective registry:

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
LeanCTX gateway
        |
        +-- codegraph
        +-- gitlab
        +-- grafana
        +-- ...
```

That works while a logical integration has one Harr-selected implementation. It breaks when a project wants to keep Harr but replace one integration with a project-specific implementation.

Concrete example: Harr can provide GitLab itself, while a project can use GitLab's official remote MCP. Those implementations may differ in transport, authentication, tool names, schemas, versions, and available tools.

Desired invariant:

> Harr policy addresses a stable logical MCP contract. Project configuration selects the provider behind that contract.

## Goals

1. Keep the agent-visible Harr namespace stable, for example `gitlab::*`.
2. Allow a project to override selected Harr MCP integrations without changing the global Harr installation.
3. Keep global Harr defaults when a project does not opt in.
4. Support providers with different MCP transports and tool schemas.
5. Keep project configuration safe to commit: no secrets or arbitrary executable commands.
6. Preserve cwd/project affinity so two agents in two repositories can use different providers concurrently.
7. Keep behavior host-independent across Codex and OpenCode.
8. Leave room for later per-tool routing without requiring it in v1.

## Proposed model

Introduce three concepts:

```text
logical adapter        provider implementation       project binding
---------------        -----------------------       ---------------
gitlab            -->  harr                     <-- global default
                  -->  official                 <-- project override
```

### Logical adapter

A logical adapter is the stable MCP contract exposed to LeanCTX and the agent.

For GitLab, the agent always sees:

```text
gitlab::<canonical-tool>
```

Global Harr policy refers only to that logical contract. It never asks the model to choose between multiple GitLab MCP servers.

### Provider

A provider is an implementation behind an adapter.

For GitLab:

```text
gitlab/harr
    current Harr-managed GitLab MCP

gitlab/official
    GitLab official remote MCP
    https://<gitlab-host>/api/v4/mcp
```

Provider definitions are Harr-owned and versioned with Harr. Projects may select and parameterize a provider, but cannot define arbitrary executable providers.

### Project binding

Proposed committed file:

```text
.harr/mcp.json
```

Example:

```json
{
  "schema": 1,
  "adapters": {
    "gitlab": {
      "enabled": true,
      "provider": "official",
      "url": "https://gitlab.example.com/api/v4/mcp"
    }
  }
}
```

A project can also explicitly disable an adapter inherited from the global profile:

```json
{
  "schema": 1,
  "adapters": {
    "gitlab": {
      "enabled": false
    }
  }
}
```

No project file means the global/default provider.

The nearest ancestor `.harr/mcp.json` wins, so starting an agent from a project subdirectory is deterministic.

## Runtime architecture

Do not rewrite global LeanCTX configuration per project.

Instead, make the public MCP entry an adapter process:

```text
Codex / OpenCode
       |
       v
    LeanCTX
       |
       v
 gitlab adapter                 cwd inherited from agent
       |
       +---- resolve nearest .harr/mcp.json
       |
       +---- no binding -------------> provider: harr
       |
       +---- project binding --------> provider: official
```

The adapter starts on demand and inherits cwd. Provider selection is therefore session/project-local and concurrent projects do not race on a global generated config.

## Registry model

The registry should distinguish a public adapter from internal provider backends.

Illustrative shape:

```json
{
  "name": "gitlab",
  "label": "GitLab",
  "required": false,
  "adapter": {
    "default_provider": "harr",
    "providers": {
      "harr": {
        "kind": "managed",
        "backend": "gitlab-harr"
      },
      "official": {
        "kind": "gitlab-official",
        "url_parameter": true
      }
    }
  }
}
```

The current implementation-specific GitLab server becomes an internal backend such as `gitlab-harr` and must not appear in LeanCTX discovery.

## Adapter contract

The adapter is:

- an MCP server toward LeanCTX;
- an MCP client toward the selected provider.

For v1 it only needs the tools surface Harr uses:

```text
initialize
tools/list
tools/call
```

Resources/prompts can be added later.

### Canonical tools

Provider implementations may differ. Each provider therefore has a Harr-owned mapping to a canonical tool contract.

Conceptually:

```text
canonical tool                 provider tool
--------------                 -------------
create_merge_request     --->  create_merge_request
get_merge_request        --->  get_merge_request
...
```

A mapping can be:

1. identity;
2. tool rename;
3. explicit argument/result transform.

Transforms are code owned by Harr, never code from the project repository.

This is the key reason to have an adapter layer instead of merely replacing a URL in the effective registry.

### Provider-specific tools

Initially expose only canonical tools.

Later, if useful, extra provider tools can be surfaced with an unmistakable name such as:

```text
gitlab::provider__<tool>
```

That avoids silently changing the stable contract.

## Official GitLab provider

GitLab's official MCP is a remote HTTP server at:

```text
https://<gitlab-host>/api/v4/mcp
```

It uses OAuth 2.0 Dynamic Client Registration. Harr should not implement generic OAuth itself in v1.

Recommended approach: the official provider uses a pinned Harr-owned OAuth-capable MCP client/bridge such as `mcp-remote`. Project config supplies only the non-secret endpoint.

A later explicit command can own auth UX:

```text
harr mcp auth gitlab
```

Authentication state stays local and is never committed into `.harr/mcp.json`.

## Security boundary

Project MCP configuration is repository-controlled input and must be treated as untrusted.

Allowed:

- select a provider from a Harr-owned allowlist;
- set documented non-secret provider parameters such as an HTTPS endpoint;
- select Harr-defined toolsets/profiles.

Forbidden:

- arbitrary commands or executable paths;
- arbitrary args;
- arbitrary environment injection;
- secrets or secret paths;
- arbitrary adapter code;
- shell fragments.

For the official GitLab provider, require HTTPS by default. A local-development exception, if needed, should be explicit rather than inferred.

## Configuration precedence

Recommended precedence:

```text
Harr adapter/provider catalog
        <
global Harr selection + provider defaults
        <
project .harr/mcp.json overlay
        <
explicit one-shot diagnostic override (future)
```

The project layer is a true overlay, not merely a provider selector. It can change `enabled`, `provider`, and provider-specific non-secret parameters. Omitted fields inherit from the lower layer.

Project configuration has higher precedence than the global Harr selection and may explicitly enable, disable, or replace an adapter for that project.

Therefore:

- globally disabled `gitlab` + no project binding -> disabled;
- globally disabled `gitlab` + project binding with `enabled: true` -> enabled for that project;
- globally enabled `gitlab` + project binding with `enabled: false` -> disabled for that project;
- globally enabled `gitlab` + project binding selecting another provider -> enabled with the project provider.

The global selection is the default profile, not a hard permission boundary. The project overlay is the final effective configuration for sessions rooted in that project.

## Project root resolution

At adapter startup:

1. begin at inherited cwd;
2. walk parent directories;
3. use the nearest `.harr/mcp.json`;
4. otherwise use the global default.

Do not use Git commands for this resolution. Harr already preserves cwd for downstream MCPs.

## Failure semantics

A configured project provider must fail closed.

Example:

```text
gitlab adapter: project provider "official"
gitlab adapter: endpoint https://gitlab.example.com/api/v4/mcp
gitlab adapter: authentication required; run: harr mcp auth gitlab
```

Never silently fall back from an explicitly configured project provider to the Harr provider. That could execute a write against the wrong GitLab identity or instance.

No project binding is different: it intentionally means use the global default.

## Diagnostics

Add project-aware resolution diagnostics:

```text
harr mcp resolve
harr mcp resolve gitlab
```

Example:

```text
project: /work/my-project
config:  /work/my-project/.harr/mcp.json

adapter     enabled   provider   source
gitlab      yes       official   project
grafana     yes       harr       global-default
```

Resolution diagnostics must not contact or authenticate to the remote provider.

`harr status` may include the resolved binding when run inside a project, clearly separated from global selection.

## Per-tool routing

Reserve the architecture for it, but do not implement it in v1.

Possible future form:

```json
{
  "schema": 2,
  "adapters": {
    "gitlab": {
      "provider": "harr",
      "routes": {
        "get_project": "official",
        "get_merge_request": "official"
      }
    }
  }
}
```

Reasons to start with whole-adapter replacement:

- write operations across identities or instances are dangerous;
- identifiers can differ between providers;
- schemas need canonicalization first;
- whole-adapter replacement solves the immediate project override problem.

Once the canonical contract is proven, per-tool routing becomes a routing-table extension instead of an architectural rewrite.

## Implementation phases

### Phase 1: project resolution

- parser/validator for `.harr/mcp.json`;
- nearest-project resolution;
- provider selection model;
- `harr mcp resolve`;
- tests for precedence, malformed config, security, and concurrent cwd roots.

No proxy runtime yet.

### Phase 2: adapter runtime

- small Harr-owned MCP server/client;
- public `gitlab` adapter namespace;
- current Harr provider behind it;
- identity/canonical mapping for GitLab tools;
- switch LeanCTX from direct backend to adapter.

Without project config, behavior must remain unchanged.

### Phase 3: official GitLab provider

- official provider type;
- pinned OAuth-capable transport;
- project endpoint parameter;
- explicit auth/status flow;
- canonical tool mapping;
- mock remote MCP integration tests.

### Phase 4: generalization

- generic adapter/provider interfaces;
- migrate Grafana, Elasticsearch, and future integrations only where multiple providers are useful;
- optional provider-specific passthrough tools;
- optional per-tool routing.

## Tests required

1. No project config preserves current GitLab behavior.
2. Project config selects a different provider only for that cwd tree.
3. Two simultaneous project roots can resolve different providers.
4. Child directory resolves nearest parent config.
5. Unknown provider/malformed config fails closed.
6. Project config cannot define command/env/secret.
7. Project config can enable a globally disabled adapter and disable a globally enabled adapter.
8. Provider failure never silently falls back.
9. Canonical tool mapping keeps the same agent-visible name.
10. Shared resolver behaves identically on Linux/macOS/Windows.

## Alternatives rejected

### Rewrite the effective registry per project

Not sufficient. It does not normalize provider tool contracts, and a single global generated registry cannot represent concurrent projects safely.

### Expose both providers and let the model choose

Not acceptable. It increases tool/context surface, makes routing probabilistic, and is especially unsafe for writes.

### Raw project-defined MCP server objects

Not acceptable. A cloned repository would become a source of arbitrary commands, env injection, and network endpoints outside Harr's ownership.

### Host-specific project MCP config

Not acceptable. It would fork behavior between Codex and OpenCode and undermine Harr as the common layer.

## Proposed first decision

Implement v1 around this invariant:

> One Harr logical MCP adapter name -> one selected provider per project/session.

For GitLab:

```text
agent sees: gitlab::*
default:    Harr-managed GitLab provider
override:   official GitLab remote provider
selection:  .harr/mcp.json
```

Do not mix providers per tool until the canonical GitLab contract and provider mapping are proven.
