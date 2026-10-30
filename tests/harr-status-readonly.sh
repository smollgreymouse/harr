#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() {
  chmod -R u+w "$TMP" 2>/dev/null || true
  rm -rf -- "$TMP"
}
trap cleanup EXIT

export HOME="$TMP/home"
export XDG_CONFIG_HOME="$TMP/config"
mkdir -p "$HOME" "$XDG_CONFIG_HOME"

run_readonly_commands() {
  "$ROOT/linux/harr" status >/dev/null
  "$ROOT/linux/harr" mcp available >/dev/null
  "$ROOT/linux/harr" mcp list >/dev/null
  "$ROOT/linux/harr" mcp status >/dev/null
}

# A status/read command must not bootstrap Harr configuration as a side effect.
run_readonly_commands
[[ ! -e "$XDG_CONFIG_HOME/harr" ]] || {
  echo "read-only Harr commands created config state" >&2
  find "$XDG_CONFIG_HOME/harr" -maxdepth 2 -type f -print >&2 || true
  exit 1
}

# With an existing selection/effective registry, read-only commands must not
# rewrite either file. Making the directory non-writable catches hidden writes.
config="$XDG_CONFIG_HOME/harr"
mkdir -p "$config"
python3 "$ROOT/common/mcp/selector.py" \
  --catalog "$ROOT/common/mcp/registry.json" \
  --selection "$config/mcp-selection.json" \
  --effective "$config/mcp-registry.json" \
  --spec gitlab >/dev/null

before_selection="$(sha256sum "$config/mcp-selection.json")"
before_effective="$(sha256sum "$config/mcp-registry.json")"
chmod -R a-w "$config"
run_readonly_commands
chmod -R u+w "$config"

[[ "$(sha256sum "$config/mcp-selection.json")" == "$before_selection" ]]
[[ "$(sha256sum "$config/mcp-registry.json")" == "$before_effective" ]]

echo "Harr status/read-only MCP commands: PASS"
