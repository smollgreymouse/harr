# Project-scoped MCP customization

A project can customize its MCP surface with a committed overlay `.harr/mcp.json` plus user-local trust and credential profiles. The global Harr selection stays the default everywhere else; the overlay only changes sessions whose working directory is inside the project tree.

## Effective model

```text
Harr catalog (providers) + global selection
        + nearest trusted .harr/mcp.json
        + user-local profiles/trust state
        => per-session LeanCTX gateway config (~/.config/harr/mcp-sessions/<key>)
```

The nearest ancestor manifest wins. Sessions started outside the tree see the global selection. New sessions pick changes up deterministically; a live session honors enable/disable on its next `ctx_tools` action, and a rotated secret value needs a new session.

## Overlay manifest (committed, untrusted)

```json
{
  "schema": 1,
  "instances": {
    "gitlab-official": {"provider": "gitlab-official", "profile": "gitlab-official-prod"},
    "gitlab": {"enabled": false}
  },
  "extensions": {
    "company-search": {"transport": "http", "url": "https://mcp.example.com/search"}
  }
}
```

Semantics:

- global enabled + project disables -> disabled for that project;
- global enabled + project selects another instance -> that instance;
- global disabled + project enables (via a provider definition) -> enabled for that project;
- without a disable entry other instances stay visible: an instance and the global default can coexist side by side (two instances of one vendor keep separate tool surfaces and credentials).

Validation is fail-closed: only `schema`, `instances` (`provider`, `enabled`, `profile`) and `extensions` (`transport`, `url`) exist — secrets, commands, args, env and non-HTTPS endpoints are rejected by schema. Project instances select HTTP providers from the Harr `providers` catalog (v1: `gitlab-official`); stdio providers cannot be defined by a project. Extensions carry no credentials in v1.

## Trust

The manifest is repository-controlled input. Harr keeps a digest approval in user-local state:

```text
harr mcp project status
harr mcp project trust     # approve the current manifest digest
harr mcp project revoke
```

Any manifest change invalidates trust; an untrusted or invalid overlay is ignored (global defaults apply) and reported. Trust never lives in the repository.

## Credential profiles

Profiles bind a provider instance to one approved endpoint and one secret reference — no secret bytes:

```text
harr mcp profile list
harr mcp profile set gitlab-official-prod \
  --provider gitlab-official \
  --endpoint https://gitlab.example.com/api/v4/mcp \
  --secret-file gitlab-official-mcp-token \
  --memento-id mcp/gitlab/official
harr mcp profile {enable|disable|remove} gitlab-official-prod
```

The secret value lives in the Harr secret store (`harr secret set <name>`; rotation overwrites the value atomically, the profile reference stays). Profiles are bound to explicit projects; a disabled profile blocks new sessions fail-closed.

## Diagnostics and runtime

```text
harr mcp resolve [NAME]    # nearest manifest, effective instances, sources, secret ids
```

Diagnostics never contact providers and never print secret values. Calls go through `ctx_tools` as `<instance>::<tool>`; a failed instance is never silently replaced by another one.

## Boundaries

- Never put secrets, tokens, commands, args or env into `.harr/mcp.json` — the schema rejects them.
- Do not approve (`project trust`) a manifest whose origin you cannot account for; it is executable-capability configuration.
- Do not work around a failed project provider by switching credentials or instances by hand.
- Changes to instance config or profile state take effect through the session cache key; report `harr mcp resolve` output when asked why a project sees different tools.
