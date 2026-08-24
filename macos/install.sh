#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMMON_DIR="$(cd -- "${SOURCE_DIR}/../common" && pwd)"
readonly FILES_DIR="${SOURCE_DIR}/files"
readonly BIN_DIR="${HOME}/.local/bin"
readonly LIBEXEC_DIR="${HOME}/.local/libexec/harr"
readonly COMMON_LIB_DIR="${LIBEXEC_DIR}/common"
readonly CLI_LIB_DIR="${LIBEXEC_DIR}/cli"
readonly LEANCTX_LIB_DIR="${LIBEXEC_DIR}/leanctx"
readonly STATE_LIB_DIR="${LIBEXEC_DIR}/state"
readonly CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
readonly HARR_CONFIG_DIR="${CONFIG_HOME}/harr"
readonly MCP_CONFIG_DIR="${HARR_CONFIG_DIR}/mcp"
readonly MCP_SELECTION="${HARR_CONFIG_DIR}/mcp-selection.json"
readonly MCP_EFFECTIVE="${HARR_CONFIG_DIR}/mcp-registry.json"
readonly MCP_CATALOG="${COMMON_DIR}/mcp/registry.json"
readonly MCP_SELECTOR="${COMMON_DIR}/mcp/selector.py"
readonly SECRETS_DIR="${HARR_CONFIG_DIR}/secrets"
readonly LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
readonly LOG_DIR="${HOME}/Library/Logs/Harr"
readonly MCP_MANAGER="${COMMON_LIB_DIR}/mcp/manager.py"
readonly SOURCE_MANAGER="${COMMON_DIR}/mcp/manager.py"
readonly CLEAN_STATE_MARKER="${HOME}/.local/share/harr/state/pre-harr/complete"

start_now=0
harr_only=0
clean_takeover=0
configure_mcp=0
mcp_spec=''
mcp_explicit=0
first_install=0

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

show_help() {
  cat <<'EOF'
Harr macOS installer

Usage:
  ./install.sh --clean [--start]
  ./install.sh --clean --all [--start]
  ./install.sh --clean --mcp gitlab,grafana [--start]
  ./install.sh [--start] [--harr-only] [--configure-mcp]

LeanCTX and CodeGraph are always installed. On the first interactive install,
optional MCPs are chosen from a checklist. Normal updates reuse the saved choice.

Options:
  --clean          Required for the first install; saves exact rollback state.
  --all            Non-interactive full install: enable every optional MCP.
  --mcp SPEC       Non-interactive optional set: none|all|name1,name2.
  --configure-mcp  Show the checklist even when a saved choice exists.
  --start          Load/restart enabled service MCPs after installation.
  --harr-only      Update Harr/global policy/config/skills without stack downloads.
  -h, --help       Show this help.
EOF
}

parse_arguments() {
  while (($#)); do
    case "$1" in
      --clean) clean_takeover=1 ;;
      --start) start_now=1 ;;
      --harr-only) harr_only=1 ;;
      --all) mcp_spec=all; mcp_explicit=1 ;;
      --mcp) shift; (($#)) || die '--mcp requires none|all|name1,name2'; mcp_spec="$1"; mcp_explicit=1 ;;
      --configure-mcp) configure_mcp=1 ;;
      -h|--help) show_help; exit 0 ;;
      *) die "unknown option: $1 (see ./install.sh --help)" ;;
    esac
    shift
  done
  if ((mcp_explicit && configure_mcp)); then
    die '--all/--mcp cannot be combined with --configure-mcp'
  fi
}

prepare_clean_ownership() {
  local state_source="${FILES_DIR}/state/harr-state"
  [[ -r "$state_source" ]] || die "missing Harr state helper: $state_source"
  if [[ -f "$CLEAN_STATE_MARKER" ]]; then
    ((clean_takeover)) && printf 'Clean ownership already initialized; preserving original pre-Harr snapshot.\n'
    HARR_MCP_MANAGER="$SOURCE_MANAGER" bash "$state_source" snapshot >/dev/null
    return
  fi
  first_install=1
  ((clean_takeover)) || die 'first Harr installation requires --clean; Harr will not merge itself into an existing global harness'
  HARR_MCP_MANAGER="$SOURCE_MANAGER" bash "$state_source" snapshot
}

select_mcp_set() {
  local default=required
  install -d -m 0700 "$HARR_CONFIG_DIR"
  if (( ! first_install )) && [[ ! -r "$MCP_SELECTION" ]]; then default=all; fi
  local selector_args=(--catalog "$MCP_CATALOG" --selection "$MCP_SELECTION" --effective "$MCP_EFFECTIVE" --default "$default")
  if ((mcp_explicit)); then selector_args+=(--spec "$mcp_spec");
  elif ((configure_mcp || first_install)); then selector_args+=(--configure); fi
  python3 "$MCP_SELECTOR" "${selector_args[@]}"
}

install_runtime_files() {
  install -d -m 0755 "$BIN_DIR" "$LIBEXEC_DIR" "$CLI_LIB_DIR" "$LEANCTX_LIB_DIR" "$STATE_LIB_DIR" "$MCP_CONFIG_DIR" "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
  install -d -m 0700 "$SECRETS_DIR"
  rm -rf -- "$COMMON_LIB_DIR"
  cp -a "${COMMON_DIR}" "$COMMON_LIB_DIR"
  find "$COMMON_LIB_DIR" -type d -exec chmod 0755 {} +
  find "$COMMON_LIB_DIR" -type f -exec chmod 0644 {} +
  chmod 0755 "$MCP_MANAGER" "${COMMON_LIB_DIR}/mcp/selector.py" "${COMMON_LIB_DIR}/mcp/assets.py"
  install -m 0755 "${SOURCE_DIR}/harr" "${BIN_DIR}/harr"
  install -m 0755 "${FILES_DIR}/mcp/harr-mcp-run" "${BIN_DIR}/harr-mcp-run"
  install -m 0755 "${FILES_DIR}/mcp/codegraph-cli" "${BIN_DIR}/codegraph"
  local f
  for f in common help components mcp uninstall; do install -m 0644 "${FILES_DIR}/harr-cli/${f}.sh" "${CLI_LIB_DIR}/${f}.sh"; done
  install -m 0755 "${FILES_DIR}/state/harr-state" "${STATE_LIB_DIR}/harr-state"
  install -m 0755 "${FILES_DIR}/leanctx/lean-ctx-wrapper" "${LEANCTX_LIB_DIR}/lean-ctx-wrapper"
}

write_baseline_runtime_env() {
  local python_bin
  python_bin="$(command -v python3)"
  install -d -m 0700 "$HARR_CONFIG_DIR"
  cat >"${HARR_CONFIG_DIR}/runtime.env" <<EOF
# Managed by Harr. Regenerated by Harr component installation.
HARR_PYTHON_BIN=${python_bin}
HARR_NPM_BIN_DIR=${HOME}/.local/share/harr/npm/node_modules/.bin
EOF
  chmod 0600 "${HARR_CONFIG_DIR}/runtime.env"
}

install_mcp_configs() { python3 "$MCP_MANAGER" --registry "$MCP_EFFECTIVE" install-configs --config-dir "$MCP_CONFIG_DIR"; }

write_launch_agent() {
  local name="$1" label plist runner out err
  label="com.harr.mcp.${name}"; plist="${LAUNCH_AGENTS_DIR}/${label}.plist"; runner="${BIN_DIR}/harr-mcp-run"
  out="${LOG_DIR}/${name}.out.log"; err="${LOG_DIR}/${name}.err.log"
  python3 - "$plist" "$label" "$runner" "$name" "$out" "$err" <<'PY'
import plistlib, sys
path, label, runner, name, out, err = sys.argv[1:]
data = {"Label": label, "ProgramArguments": [runner, name], "RunAtLoad": True, "KeepAlive": True, "ProcessType": "Background", "StandardOutPath": out, "StandardErrorPath": err}
with open(path, "wb") as f: plistlib.dump(data, f, sort_keys=False)
PY
  chmod 0644 "$plist"
}

configure_launchd() {
  ((harr_only)) && return
  local name active label
  active="$(python3 "$MCP_MANAGER" --registry "$MCP_EFFECTIVE" names --lifecycle service)"
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    label="com.harr.mcp.${name}"
    if printf '%s\n' "$active" | grep -Fxq -- "$name"; then
      write_launch_agent "$name"
    else
      launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
      rm -f -- "${LAUNCH_AGENTS_DIR}/${label}.plist"
    fi
  done < <(python3 "$MCP_MANAGER" --registry "$MCP_CATALOG" names --lifecycle service)
}

main() {
  [[ "$(uname -s)" == Darwin ]] || die 'macos/install.sh must run on macOS'
  [[ "$EUID" -ne 0 ]] || die 'run Harr installer as your normal user, without sudo'
  parse_arguments "$@"
  command -v python3 >/dev/null 2>&1 || die 'python3 is required for Harr host configuration management'
  command -v launchctl >/dev/null 2>&1 || die 'launchctl not found'
  prepare_clean_ownership
  select_mcp_set
  install_runtime_files
  write_baseline_runtime_env
  install_mcp_configs
  configure_launchd

  if ((!harr_only)); then
    "${BIN_DIR}/harr" install all
  else
    "${BIN_DIR}/harr" hosts apply
    "${BIN_DIR}/harr" agents apply all
    "${BIN_DIR}/harr" leanctx apply
  fi
  if ((start_now)); then "${BIN_DIR}/harr" mcp restart all; fi

  printf '\nHarr installed in clean global-harness mode for macOS.\n'
  printf 'LeanCTX + CodeGraph are required; optional MCPs follow %s.\n' "$MCP_SELECTION"
  printf 'Change them later with: harr mcp configure\n'
  printf 'Project-level configs/files were not touched.\n'
  if (( ! start_now )); then printf 'Enabled LaunchAgents were not loaded now. Start with: harr mcp start all\n'; fi
  printf 'Check with: harr status\nRollback with: harr uninstall\n'
  if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then printf 'Note: add %s to PATH.\n' "$BIN_DIR"; fi
}

main "$@"
