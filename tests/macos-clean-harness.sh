#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export HARR_TEST_ROOT="$ROOT"
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
cat >"${TMP}/bin/uname" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == -s || $# -eq 0 ]]; then printf 'Darwin\n'; else /usr/bin/uname "$@"; fi
EOF
chmod 0755 "${TMP}/bin/launchctl" "${TMP}/bin/uname"
export PATH="${TMP}/bin:${PATH}"

printf 'OLD CODEX POLICY\n' >"${CODEX_HOME}/AGENTS.md"
cat >"${CODEX_HOME}/config.toml" <<'EOF'
model = "keep-model"
[mcp_servers.external-mcp]
url = "https://example.invalid/codex-mcp"
enabled = true

EOF
cat >>"${CODEX_HOME}/config.toml" <<EOF

[mcp_servers.harr-gigacode-app]
command = "/old/python"
args = ["${HOME}/.local/libexec/harr/common/mcp/gigacode_app/server.py"]
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

# Create mock retired LaunchAgent plists to verify cleanup.
mkdir -p "${HOME}/Library/LaunchAgents"
for label in com.harr.mcp.gitlab com.harr.mcp.grafana; do
  cat >"${HOME}/Library/LaunchAgents/${label}.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>${label}</string></dict></plist>
PLIST
done

cp "${CODEX_HOME}/AGENTS.md" "${TMP}/codex-agents.before"
cp "${CODEX_HOME}/config.toml" "${TMP}/codex-config.before"
cp "${XDG_CONFIG_HOME}/opencode/AGENTS.md" "${TMP}/opencode-agents.before"
cp "${XDG_CONFIG_HOME}/opencode/opencode.jsonc" "${TMP}/opencode-config.before"
cp "${XDG_CONFIG_HOME}/lean-ctx/config.toml" "${TMP}/leanctx.before"

bash "${ROOT}/macos/install.sh" --clean --harr-only --mcp none

grep -q 'codegraph::codegraph_explore' "${CODEX_HOME}/AGENTS.md"
grep -q 'through `ctx_shell`' "${CODEX_HOME}/AGENTS.md"
! grep -q 'GitLab MR/pipeline' "${CODEX_HOME}/AGENTS.md"
! grep -q 'Grafana dashboard work' "${CODEX_HOME}/AGENTS.md"
grep -q 'lean-ctx_ctx_tools' "${XDG_CONFIG_HOME}/opencode/AGENTS.md"
grep -q '^# Managed by Harr\.$' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
grep -q 'brew' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
grep -q 'name = "codegraph"' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
! grep -q 'name = "gitlab"' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
! grep -q 'name = "grafana"' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
! grep -q 'name = "kibana"' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"
[[ ! -e "${XDG_CONFIG_HOME}/opencode/skills/harr/references/gitlab.md" ]]
[[ ! -e "${XDG_CONFIG_HOME}/opencode/skills/harr/references/grafana.md" ]]
[[ ! -e "${XDG_CONFIG_HOME}/opencode/skills/harr/references/kibana.md" ]]
[[ ! -e "${XDG_CONFIG_HOME}/opencode/skills/gigacode-executor" ]]
[[ ! -e "${CODEX_HOME}/skills/gigacode-executor" ]]
[[ ! -e "${XDG_CONFIG_HOME}/opencode/skills/einherjar-worker" ]]
[[ ! -e "${CODEX_HOME}/skills/einherjar-worker" ]]
[[ ! -e "${HOME}/.local/libexec/harr/common/mcp/gigacode_app" ]]
cmp -s "${ROOT}/harr.png" "${HOME}/.local/libexec/harr/common/mcp/assets/harr.png"
! grep -q '^\[mcp_servers\.harr-gigacode-app\]$' "${CODEX_HOME}/config.toml"
! grep -q '^\[mcp_servers\.harr-ein-ui\]$' "${CODEX_HOME}/config.toml"
[[ ! -e "${CODEX_HOME}/skills/harr-workspace" ]]
[[ ! -e "${XDG_CONFIG_HOME}/opencode/skills/harr-workspace" ]]
! grep -q '\$gigacode-executor' "${CODEX_HOME}/AGENTS.md"
# Retired LaunchAgent plists must be removed.
for label in com.harr.mcp.gitlab com.harr.mcp.grafana; do
  if [[ -f "${HOME}/Library/LaunchAgents/${label}.plist" ]]; then
    printf 'FAIL: retired plist left behind: %s\n' "${label}" >&2
    exit 1
  fi
done
[[ -f "${HOME}/Library/LaunchAgents/com.harr.git-host.plist" ]]
[[ -x "${HOME}/.local/libexec/harr/common/git_host/git_host.py" ]]
[[ -s "${XDG_CONFIG_HOME}/harr/secrets/git-host-capability" ]]
python3 -c 'import os, stat, sys; assert stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o600' "${XDG_CONFIG_HOME}/harr/secrets/git-host-capability"
grep -q 'harr git <git-arguments>' "${HOME}/.local/bin/harr" "${HOME}/.local/libexec/harr/cli/help.sh"
grep -q 'HARR_LEANCTX_BUILD="3.11.0-harr-progress.1"' "${ROOT}/macos/files/harr-cli/components.sh"
grep -q 'HARR_LEANCTX_REPO="smollgreymouse/lean-ctx"' "${ROOT}/macos/files/harr-cli/components.sh"
grep -q '^call_timeout_secs = 1800$' "${XDG_CONFIG_HOME}/lean-ctx/config.toml"

python3 - <<'PY'
import json, os, plistlib, tomllib
from pathlib import Path
home = Path(os.environ['HOME'])
config = Path(os.environ['XDG_CONFIG_HOME'])
codex = tomllib.loads((Path(os.environ['CODEX_HOME']) / 'config.toml').read_text())
assert codex['model'] == 'keep-model'
assert codex['mcp_servers']['external-mcp']['url'] == 'https://example.invalid/codex-mcp'
assert codex['mcp_servers']['lean-ctx']['command'] == str(home / '.local/bin/lean-ctx')
assert codex['mcp_servers']['lean-ctx']['default_tools_approval_mode'] == 'auto'
assert codex['mcp_servers']['lean-ctx']['tool_timeout_sec'] == 1900
assert 'harr-workspace' not in codex['mcp_servers']
assert 'harr-workspace-app' not in codex['mcp_servers']
opencode = json.loads((config / 'opencode/opencode.jsonc').read_text())
assert opencode['mcp']['lean-ctx']['timeout'] == 1900000
assert 'harr-workspace' not in opencode['mcp']
lean = tomllib.loads((Path(os.environ['XDG_CONFIG_HOME']) / 'lean-ctx/config.toml').read_text())
assert lean['allow_paths'] == [
    str(Path(os.environ['CODEX_HOME']) / 'skills/harr'),
    str(Path(os.environ['CODEX_HOME']) / 'skills/lean-ctx'),
    str(Path(os.environ['CODEX_HOME']) / 'skills/einherjar-worker'),
    str(config / 'opencode/skills/harr'),
    str(config / 'opencode/skills/lean-ctx'),
    str(config / 'opencode/skills/einherjar-worker'),
]
selection = json.loads((config / 'harr/mcp-selection.json').read_text())
effective = json.loads((config / 'harr/mcp-registry.json').read_text())
assert selection['enabled'] == ['codegraph']
assert [item['name'] for item in effective['servers']] == ['codegraph']
catalog = json.loads((Path(os.environ['HARR_TEST_ROOT']) / 'common/mcp/registry.json').read_text())
assert not {'gigacode', 'einherjar'} & {item['name'] for item in catalog['servers']}
saved = config / 'einherjar/instances.json'
assert not saved.exists() or json.loads(saved.read_text())['instances'] == []
with (home / 'Library/LaunchAgents/com.harr.git-host.plist').open('rb') as f:
    git_host = plistlib.load(f)
assert git_host['Label'] == 'com.harr.git-host'
assert git_host['ProgramArguments'][1].endswith('/common/git_host/git_host.py')
assert git_host['ProgramArguments'][2:] == [
    'serve', '--secret-file', str(config / 'harr/secrets/git-host-capability')
]
PY

# Two explicitly named instances may use the same backend and get separate public names.
"${HOME}/.local/bin/harr" ein add --id giga-review --adapter gigacode
"${HOME}/.local/bin/harr" ein add --id giga-builder --adapter gigacode
"${HOME}/.local/bin/harr" ein apply
python3 - <<'PY'
import json, os, tomllib
from pathlib import Path
config = Path(os.environ['XDG_CONFIG_HOME']) / 'harr'
instances = json.loads((config / 'einherjar/instances.json').read_text())['instances']
assert [(item['id'], item['adapter']) for item in instances] == [
    ('giga-review', 'gigacode'), ('giga-builder', 'gigacode')]
effective = json.loads((config / 'mcp-registry.json').read_text())['servers']
by_name = {item['name']: item for item in effective}
assert by_name['giga-review']['ein_instance'] == 'giga-review'
assert by_name['giga-builder']['ein_instance'] == 'giga-builder'
assert not {'gigacode', 'einherjar'} & set(by_name)
lean = tomllib.loads((Path(os.environ['XDG_CONFIG_HOME']) / 'lean-ctx/config.toml').read_text())
gateway_names = {server['name'] for server in lean['gateway']['servers']}
assert {'giga-review', 'giga-builder'} <= gateway_names
assert 'gigacode' not in gateway_names and 'einherjar' not in gateway_names
codex = tomllib.loads((Path(os.environ['CODEX_HOME']) / 'config.toml').read_text())
assert set(codex['mcp_servers']) >= {'harr-ein-ui'}
assert 'harr-gigacode-app' not in codex['mcp_servers']
assert not (Path(os.environ['CODEX_HOME']) / 'skills/gigacode-executor').exists()
assert (Path(os.environ['CODEX_HOME']) / 'skills/einherjar-worker/SKILL.md').is_file()
PY

# A subsequent Harr refresh must preserve configured instance IDs.
bash "${ROOT}/macos/install.sh" --harr-only --mcp none
python3 - <<'PY'
import json, os
from pathlib import Path
config = Path(os.environ['XDG_CONFIG_HOME']) / 'harr/einherjar/instances.json'
assert [item['id'] for item in json.loads(config.read_text())['instances']] == ['giga-review', 'giga-builder']
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
[[ ! -e "${XDG_CONFIG_HOME}/harr/mcp-selection.json" ]]
[[ ! -e "${XDG_CONFIG_HOME}/harr/mcp-registry.json" ]]
[[ ! -e "${HOME}/.local/libexec/harr" ]]
[[ ! -e "${HOME}/Library/LaunchAgents/com.harr.git-host.plist" ]]
[[ ! -e "${HOME}/.local/share/harr-state" ]]
find "${HOME}/.local/share/harr-uninstall-backups" -mindepth 1 -maxdepth 1 -type d | grep -q .

printf 'macOS clean harness takeover/rollback: PASS\n'
