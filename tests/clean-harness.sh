#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="${TMP}/home"
export XDG_CONFIG_HOME="${HOME}/.config"
export CODEX_HOME="${HOME}/.codex"
# Force the self-contained TOML fallback so CI tests the path used when a
# desktop/IDE Codex host does not expose the Codex CLI in PATH.
export HARR_CODEX_DISABLE_CLI=1
mkdir -p "${TMP}/bin"
printf '#!/usr/bin/env bash\nexit 0\n' >"${TMP}/bin/systemctl"
chmod 0755 "${TMP}/bin/systemctl"
export PATH="${TMP}/bin:${PATH}"
mkdir -p "$CODEX_HOME" "$XDG_CONFIG_HOME/opencode/commands" "$XDG_CONFIG_HOME/opencode/skills/external"

cat >"${CODEX_HOME}/AGENTS.md" <<'EOF'
OLD CODEX POLICY
EOF
cat >"${CODEX_HOME}/config.toml" <<'EOF'
model = "keep-model"

[mcp_servers.external-mcp]
url = "https://example.invalid/codex-mcp"
enabled = true

[mcp_servers.lean-ctx]
command = "old-lean-ctx"
enabled = false
EOF
cat >"${XDG_CONFIG_HOME}/opencode/AGENTS.md" <<'EOF'
OLD OPENCODE POLICY
EOF
cat >"${XDG_CONFIG_HOME}/opencode/opencode.jsonc" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["external-plugin", "opencode-mcp-triage"],
  "provider": {"external-provider": {"api": "keep"}},
  "tools": {"bash": false, "read": false, "external_tool": true},
  "permission": {"task": "allow", "bash": "deny", "external_perm": "allow"},
  "default_agent": "flow",
  "subagent_depth": 2,
  "agent": {
    "flow": {"description": "old workflow"},
    "wf-design": {"description": "old workflow"},
    "custom-agent": {"description": "keep"}
  },
  "mcp": {
    "codegraph": {"type": "local", "command": ["codegraph", "serve", "--mcp"], "enabled": true},
    "gitlab": {"type": "remote", "url": "http://127.0.0.1:9999/mcp"},
    "lean-ctx": {"type": "local", "command": ["old-lean-ctx"], "enabled": true},
    "external-mcp": {"type": "remote", "url": "https://example.invalid/mcp"}
  }
}
EOF
printf 'old quick command\n' >"${XDG_CONFIG_HOME}/opencode/commands/quick.md"
printf 'external command\n' >"${XDG_CONFIG_HOME}/opencode/commands/custom.md"
printf '# external skill\n' >"${XDG_CONFIG_HOME}/opencode/skills/external/SKILL.md"
mkdir -p "${XDG_CONFIG_HOME}/lean-ctx"
printf 'OLD LEANCTX CONFIG\n' >"${XDG_CONFIG_HOME}/lean-ctx/config.toml"

cp "${CODEX_HOME}/AGENTS.md" "${TMP}/codex-agents.before"
cp "${CODEX_HOME}/config.toml" "${TMP}/codex-config.before"
cp "${XDG_CONFIG_HOME}/opencode/AGENTS.md" "${TMP}/opencode-agents.before"
cp "${XDG_CONFIG_HOME}/opencode/opencode.jsonc" "${TMP}/opencode-config.before"
cp "${XDG_CONFIG_HOME}/lean-ctx/config.toml" "${TMP}/leanctx.before"
cp "${XDG_CONFIG_HOME}/opencode/commands/quick.md" "${TMP}/quick.before"

bash "${ROOT}/linux/files/state/harr-state" snapshot

"${ROOT}/linux/harr" agents apply all
"${ROOT}/linux/harr" hosts apply

# Harr owns the complete global AGENTS files; old policy must not survive.
! grep -q 'OLD CODEX POLICY' "${CODEX_HOME}/AGENTS.md"
! grep -q 'OLD OPENCODE POLICY' "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
grep -q 'codegraph::codegraph_explore' "${CODEX_HOME}/AGENTS.md"
grep -q '`ctx_tools`' "${CODEX_HOME}/AGENTS.md"
grep -q '`lean-ctx_ctx_tools`' "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
grep -q 'Do not use native read/grep/glob/bash' "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
grep -q 'Git repository state/history/branches/remotes/fetch/pull/push/commits' "${CODEX_HOME}/AGENTS.md"
grep -q 'through `ctx_shell`' "${CODEX_HOME}/AGENTS.md"
! grep -q 'git-mcp' "${CODEX_HOME}/AGENTS.md"

python3 - <<'PY'
import json, os, tomllib
from pathlib import Path

home = Path(os.environ['HOME'])

codex_path = Path(os.environ['CODEX_HOME']) / 'config.toml'
codex = tomllib.loads(codex_path.read_text())
assert codex['model'] == 'keep-model'
assert codex['mcp_servers']['external-mcp'] == {
    'url': 'https://example.invalid/codex-mcp',
    'enabled': True,
}
assert codex['mcp_servers']['lean-ctx'] == {
    'command': str(home / '.local' / 'bin' / 'lean-ctx'),
    'enabled': True,
    'default_tools_approval_mode': 'auto',
}

p = Path(os.environ['XDG_CONFIG_HOME']) / 'opencode' / 'opencode.jsonc'
cfg = json.loads(p.read_text())
assert cfg['provider']['external-provider']['api'] == 'keep'
assert 'external-plugin' in cfg['plugin']
assert 'opencode-mcp-triage' not in cfg['plugin']
assert 'flow' not in cfg.get('agent', {})
assert 'wf-design' not in cfg.get('agent', {})
assert cfg['agent']['custom-agent']['description'] == 'keep'
assert 'codegraph' not in cfg['mcp']
assert 'gitlab' not in cfg['mcp']
assert cfg['mcp']['external-mcp']['url'] == 'https://example.invalid/mcp'
assert cfg['mcp']['lean-ctx'] == {'type': 'local', 'command': ['lean-ctx'], 'enabled': True}
assert cfg['tools']['external_tool'] is True
assert 'bash' not in cfg['tools'] and 'read' not in cfg['tools']
assert cfg['permission']['external_perm'] == 'allow'
assert 'task' not in cfg['permission'] and 'bash' not in cfg['permission']
assert 'default_agent' not in cfg
assert 'subagent_depth' not in cfg
PY

# The official Codex writer replaces the MCP table. Harr must restore its
# approval setting after that writer removes it.
cat >"${TMP}/bin/codex" <<'EOF'
#!/usr/bin/env bash
sed -i '/^default_tools_approval_mode = /d' "${CODEX_HOME}/config.toml"
EOF
chmod 0755 "${TMP}/bin/codex"
HARR_CODEX_DISABLE_CLI=0 HARR_CODEX_CLI="${TMP}/bin/codex" \
  python3 "${ROOT}/linux/files/hosts/codex-config.py" apply
grep -q '^default_tools_approval_mode = "auto"$' "${CODEX_HOME}/config.toml"

[[ ! -e "${XDG_CONFIG_HOME}/opencode/commands/quick.md" ]]
[[ -f "${XDG_CONFIG_HOME}/opencode/commands/custom.md" ]]
[[ -f "${XDG_CONFIG_HOME}/opencode/skills/external/SKILL.md" ]]
[[ -f "${XDG_CONFIG_HOME}/opencode/skills/harr/SKILL.md" ]]
[[ -f "${XDG_CONFIG_HOME}/opencode/skills/lean-ctx/SKILL.md" ]]

"${ROOT}/linux/harr" agents status
"${ROOT}/linux/harr" hosts status

# A later --harr-only update must keep working after clean ownership exists.
"${ROOT}/linux/install.sh" --harr-only
grep -q 'through `ctx_shell`' "${CODEX_HOME}/AGENTS.md"
! grep -q 'git-mcp' "${CODEX_HOME}/AGENTS.md"

# Install only the rollback helper where the installed CLI expects it. This is
# intentionally after the pre-Harr snapshot.
mkdir -p "${HOME}/.local/libexec/harr/state"
install -m 0755 "${ROOT}/linux/files/state/harr-state" "${HOME}/.local/libexec/harr/state/harr-state"

"${ROOT}/linux/harr" uninstall

cmp -s "${TMP}/codex-agents.before" "${CODEX_HOME}/AGENTS.md"
cmp -s "${TMP}/codex-config.before" "${CODEX_HOME}/config.toml"
cmp -s "${TMP}/opencode-agents.before" "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
cmp -s "${TMP}/opencode-config.before" "${XDG_CONFIG_HOME}/opencode/opencode.jsonc"
cmp -s "${TMP}/leanctx.before" "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
cmp -s "${TMP}/quick.before" "${XDG_CONFIG_HOME}/opencode/commands/quick.md"
[[ -f "${XDG_CONFIG_HOME}/opencode/commands/custom.md" ]]
[[ -f "${XDG_CONFIG_HOME}/opencode/skills/external/SKILL.md" ]]
[[ ! -e "${HOME}/.local/share/harr-state" ]]
find "${HOME}/.local/share/harr-uninstall-backups" -mindepth 1 -maxdepth 1 -type d | grep -q .

printf 'clean harness takeover/rollback: PASS\n'
