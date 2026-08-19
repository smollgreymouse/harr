#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="${TMP}/home"
export XDG_CONFIG_HOME="${HOME}/.config"
export CODEX_HOME="${HOME}/.codex"
export HARR_CODEX_DISABLE_CLI=1
mkdir -p "${TMP}/bin" "$CODEX_HOME" "$XDG_CONFIG_HOME/opencode/commands" "$XDG_CONFIG_HOME/opencode/skills/external" "$XDG_CONFIG_HOME/lean-ctx"

cat >"${TMP}/bin/launchctl" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  print) exit 1 ;;
  print-disabled) printf '{}\n'; exit 0 ;;
  bootstrap|bootout|enable|disable|kickstart) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod 0755 "${TMP}/bin/launchctl"
export PATH="${TMP}/bin:${PATH}"

printf 'OLD CODEX POLICY\n' >"${CODEX_HOME}/AGENTS.md"
cat >"${CODEX_HOME}/config.toml" <<'EOF'
model = "keep-model"
[mcp_servers.external-mcp]
url = "https://example.invalid/codex-mcp"
enabled = true
EOF
printf 'OLD OPENCODE POLICY\n' >"${XDG_CONFIG_HOME}/opencode/AGENTS.md"
cat >"${XDG_CONFIG_HOME}/opencode/opencode.jsonc" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {"external-provider": {"api": "keep"}},
  "mcp": {"external-mcp": {"type": "remote", "url": "https://example.invalid/mcp"}}
}
EOF
printf 'external command\n' >"${XDG_CONFIG_HOME}/opencode/commands/custom.md"
printf '# external skill\n' >"${XDG_CONFIG_HOME}/opencode/skills/external/SKILL.md"
printf 'OLD LEANCTX CONFIG\n' >"${XDG_CONFIG_HOME}/lean-ctx/config.toml"

cp "${CODEX_HOME}/AGENTS.md" "${TMP}/codex-agents.before"
cp "${CODEX_HOME}/config.toml" "${TMP}/codex-config.before"
cp "${XDG_CONFIG_HOME}/opencode/AGENTS.md" "${TMP}/opencode-agents.before"
cp "${XDG_CONFIG_HOME}/opencode/opencode.jsonc" "${TMP}/opencode-config.before"
cp "${XDG_CONFIG_HOME}/lean-ctx/config.toml" "${TMP}/leanctx.before"

bash "${ROOT}/macos/install.sh" --clean --harr-only

grep -q 'codegraph::codegraph_explore' "${CODEX_HOME}/AGENTS.md"
grep -q 'through `ctx_shell`' "${CODEX_HOME}/AGENTS.md"
grep -q 'lean-ctx_ctx_tools' "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
grep -q '^# Managed by Harr\.$' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
grep -q 'brew' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"

python3 - <<'PY'
import os, plistlib, tomllib
from pathlib import Path
home = Path(os.environ['HOME'])
codex = tomllib.loads((Path(os.environ['CODEX_HOME']) / 'config.toml').read_text())
assert codex['model'] == 'keep-model'
assert codex['mcp_servers']['external-mcp']['url'] == 'https://example.invalid/codex-mcp'
assert codex['mcp_servers']['lean-ctx']['command'] == str(home / '.local/bin/lean-ctx')
assert codex['mcp_servers']['lean-ctx']['default_tools_approval_mode'] == 'auto'
plist = home / 'Library/LaunchAgents/com.harr.mcp.gitlab.plist'
assert plist.is_file()
with plist.open('rb') as f:
    job = plistlib.load(f)
assert job['Label'] == 'com.harr.mcp.gitlab'
assert job['ProgramArguments'] == [str(home / '.local/bin/harr-mcp-run'), 'gitlab']
assert job['RunAtLoad'] is True and job['KeepAlive'] is True
PY

"${HOME}/.local/bin/harr" status >/dev/null
"${HOME}/.local/bin/harr" uninstall

cmp -s "${TMP}/codex-agents.before" "${CODEX_HOME}/AGENTS.md"
cmp -s "${TMP}/codex-config.before" "${CODEX_HOME}/config.toml"
cmp -s "${TMP}/opencode-agents.before" "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
cmp -s "${TMP}/opencode-config.before" "${XDG_CONFIG_HOME}/opencode/opencode.jsonc"
cmp -s "${TMP}/leanctx.before" "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
[[ -f "${XDG_CONFIG_HOME}/opencode/commands/custom.md" ]]
[[ -f "${XDG_CONFIG_HOME}/opencode/skills/external/SKILL.md" ]]
[[ ! -e "${HOME}/.local/libexec/harr" ]]
[[ ! -e "${HOME}/Library/LaunchAgents/com.harr.mcp.gitlab.plist" ]]
[[ ! -e "${HOME}/.local/share/harr-state" ]]
find "${HOME}/.local/share/harr-uninstall-backups" -mindepth 1 -maxdepth 1 -type d | grep -q .

printf 'macOS clean harness takeover/rollback: PASS\n'
