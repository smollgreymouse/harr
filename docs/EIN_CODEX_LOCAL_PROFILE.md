# Named Codex backend: local profile configuration

The Einherjar `codex` backend is model- and provider-agnostic. Harr owns only the worker lifecycle and the standard MCP `ein` control interface. Vendor endpoints, model credentials, custom model catalogues and `model_providers` live exclusively in the local Codex profile (not in this repository).

## Configure a named worker

Create a dedicated directory outside the repository, e.g. `$HOME/.config/harr/codex-workers/worker-1`, containing a valid Codex `config.toml`. Set its `model`, `model_provider`, and `[model_providers.<provider_id>]` as appropriate to your locally available model proxy. If the provider requires a custom Codex model catalogue, set `model_catalog_json` in that local profile.

Register it with the Harr Ein setup CLI:

```sh
python3 common/mcp/ein_instances.py add \
  --id codex-worker-1 \
  --adapter codex \
  --codex-home "$HOME/.config/harr/codex-workers/worker-1"
```

The profile directory must already exist and contain `config.toml` when launching the MCP. The name is the chosen MCP server id. `--codex-home` is required for **named Codex instances**, and forbidden for other adapter types. It is an absolute path, never a credential string.

An optional `--executable /path/to/codex` selects the Codex binary. Without it the installed `codex` in PATH is used.

## Runtime behavior

- Harr's MCP manager provides the selected instance with an isolated `CODEX_HOME`, overriding any inherited parent `CODEX_HOME`; there is no silent fallback to the user's primary Codex account.
- The built-in Codex adapter launches `codex exec --json -` with the worker prompt on stdin, capturing the Codex thread id. `codex exec resume --json <thread-id> -` continues the same worker.
- Codex itself owns its sandbox, execution approvals, tools, and network/model traffic. No model-provider code or secrets are imported into Harr.
- Model proxies must be started separately and checked by the user. Harr will not start or manage a user-supplied proxy automatically.
- When an instance is changed to a non-Codex adapter, stale `codex_home` is removed from its instance record.
- Local instance registrations are stored at `$HARR_CONFIG_DIR/einherjar/instances.json` (normally `~/.config/harr/einherjar/instances.json`).

### Tests

```sh
python3 tests/einherjar-bridge.py
python3 tests/ein-named-instances.py
```

The named-instance tests check valid/invalid profile path configuration and exercise the MCP registration with a synthetic worker. No external model calls occur in these tests.
