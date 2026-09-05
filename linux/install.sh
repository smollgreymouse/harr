#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMMON_DIR="$(cd -- "${SOURCE_DIR}/../common" && pwd)"
readonly FILES_DIR="${SOURCE_DIR}/files"
readonly SYSTEMD_SOURCE_DIR="${SOURCE_DIR}/systemd"
readonly BIN_DIR="${HOME}/.local/bin"
readonly LIBEXEC_DIR="${HOME}/.local/libexec/harr"
readonly COMMON_LIB_DIR="${LIBEXEC_DIR}/common"
readonly CLI_LIB_DIR="${LIBEXEC_DIR}/cli"
readonly MCP_LIB_DIR="${LIBEXEC_DIR}/mcp"
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
readonly SYSTEMD_USER_DIR="${CONFIG_HOME}/systemd/user"
readonly MCP_MANAGER="${COMMON_LIB_DIR}/mcp/manager.py"
readonly MCP_UNIT_TEMPLATE="harr-mcp@.service"
readonly GIT_HOST_UNIT="harr-git-host.service"
readonly LEGACY_GITLAB_UNIT="harr-mcp-gitlab.service"
readonly LEGACY_CODEGRAPH_UNIT="harr-mcp-codegraph.service"
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
  cat <<'EOF_HELP'
Harr Linux installer

Usage:
  ./install.sh --clean [--start]
  ./install.sh --clean --all [--start]
  ./install.sh --clean --mcp gitlab,grafana [--start]
  ./install.sh [--start] [--harr-only] [--configure-mcp]

LeanCTX and CodeGraph are always installed. On the first interactive install,
optional MCPs are chosen from a checklist. The choice is saved globally and
normal updates reuse it without prompting.

Options:
  --clean          Required for the first install.
  --all            Non-interactive full install: enable every optional MCP.
  --mcp SPEC       Non-interactive optional set: none|all|name1,name2.
  --configure-mcp  Show the checklist even when a saved choice exists.
  --start          Start/restart enabled service MCPs after installation.
  --harr-only      Update Harr/global policy/config/skills without stack downloads.
  -h, --help       Show this help.
EOF_HELP
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
    bash "$state_source" snapshot >/dev/null
    return
  fi
  first_install=1
  ((clean_takeover)) || die 'first Harr installation requires --clean; Harr will not merge itself into an existing global harness'
  bash "$state_source" snapshot
}

select_mcp_set() {
  local default=required
  [[ -r "$MCP_SELECTOR" && -r "$MCP_CATALOG" ]] || die 'Harr MCP selector/catalog is missing'
  install -d -m 0700 "$HARR_CONFIG_DIR"
  if (( ! first_install )) && [[ ! -r "$MCP_SELECTION" ]]; then default=all; fi
  local selector_args=(--catalog "$MCP_CATALOG" --selection "$MCP_SELECTION" --effective "$MCP_EFFECTIVE" --default "$default")
  if ((mcp_explicit)); then
    selector_args+=(--spec "$mcp_spec")
  elif ((configure_mcp || first_install)); then
    selector_args+=(--configure)
  fi
  python3 "$MCP_SELECTOR" "${selector_args[@]}"
}

install_runtime_files() {
  install -d -m 0755 "$BIN_DIR" "$LIBEXEC_DIR" "$CLI_LIB_DIR" "$MCP_LIB_DIR" "$LEANCTX_LIB_DIR" "$STATE_LIB_DIR" "$MCP_CONFIG_DIR" "$SYSTEMD_USER_DIR"
  install -d -m 0700 "$SECRETS_DIR"
  rm -rf -- "$COMMON_LIB_DIR"
  cp -a "${COMMON_DIR}" "$COMMON_LIB_DIR"
  find "$COMMON_LIB_DIR" -type d -exec chmod 0755 {} +
  find "$COMMON_LIB_DIR" -type f -exec chmod 0644 {} +
  chmod 0755 "$MCP_MANAGER" "${COMMON_LIB_DIR}/mcp/selector.py" "${COMMON_LIB_DIR}/mcp/assets.py"
  chmod 0755 "${COMMON_LIB_DIR}/git_host/git_host.py"
  install -m 0755 "${SOURCE_DIR}/harr" "${BIN_DIR}/harr"
  install -m 0755 "${FILES_DIR}/mcp/harr-mcp-run" "${BIN_DIR}/harr-mcp-run"
  install -m 0755 "${FILES_DIR}/mcp/codegraph-cli" "${BIN_DIR}/codegraph"
  local f
  for f in common help components mcp uninstall; do install -m 0644 "${FILES_DIR}/harr-cli/${f}.sh" "${CLI_LIB_DIR}/${f}.sh"; done
  install -m 0755 "${FILES_DIR}/state/harr-state" "${STATE_LIB_DIR}/harr-state"
  install -m 0755 "${FILES_DIR}/leanctx/lean-ctx-wrapper" "${LEANCTX_LIB_DIR}/lean-ctx-wrapper"
  install -m 0644 "${SYSTEMD_SOURCE_DIR}/${MCP_UNIT_TEMPLATE}" "${SYSTEMD_USER_DIR}/${MCP_UNIT_TEMPLATE}"
  install -m 0644 "${SYSTEMD_SOURCE_DIR}/${GIT_HOST_UNIT}" "${SYSTEMD_USER_DIR}/${GIT_HOST_UNIT}"
  python3 "${COMMON_LIB_DIR}/git_host/git_host.py" init --secret-file "${SECRETS_DIR}/git-host-capability"
}

install_mcp_configs() { python3 "$MCP_MANAGER" --registry "$MCP_EFFECTIVE" install-configs --config-dir "$MCP_CONFIG_DIR"; }

remove_legacy_services() {
  local unit path
  for unit in "$LEGACY_GITLAB_UNIT" "$LEGACY_CODEGRAPH_UNIT"; do
    path="${SYSTEMD_USER_DIR}/${unit}"
    if [[ -e "$path" ]]; then systemctl --user disable --now "$unit" >/dev/null 2>&1 || true; rm -f -- "$path"; fi
  done
  rm -f -- "${MCP_CONFIG_DIR}/codegraph.env"
}

configure_systemd() {
  command -v systemctl >/dev/null 2>&1 || die 'systemctl not found'
  remove_legacy_services
  if [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK}" ]]; then
    systemctl --user import-environment SSH_AUTH_SOCK
  fi
  systemctl --user daemon-reload
  systemctl --user enable "$GIT_HOST_UNIT" >/dev/null
  systemctl --user restart "$GIT_HOST_UNIT"
  ((harr_only)) && return
  local name active
  active="$(python3 "$MCP_MANAGER" --registry "$MCP_EFFECTIVE" names --lifecycle service)"
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if printf '%s\n' "$active" | grep -Fxq -- "$name"; then
      systemctl --user enable "harr-mcp@${name}.service" >/dev/null
    else
      systemctl --user disable --now "harr-mcp@${name}.service" >/dev/null 2>&1 || true
    fi
  done < <(python3 "$MCP_MANAGER" --registry "$MCP_CATALOG" names --lifecycle service)
}

main() {
  [[ "$EUID" -ne 0 ]] || die 'run Harr installer as your normal user, without sudo'
  parse_arguments "$@"
  command -v python3 >/dev/null 2>&1 || die 'python3 is required for Harr host configuration management'
  prepare_clean_ownership
  select_mcp_set
  install_runtime_files
  install_mcp_configs
  configure_systemd

  if ((!harr_only)); then
    "${BIN_DIR}/harr" install all
  else
    "${BIN_DIR}/harr" hosts apply
    "${BIN_DIR}/harr" agents apply all
    "${BIN_DIR}/harr" leanctx apply
  fi
  if ((start_now)); then "${BIN_DIR}/harr" mcp restart all; fi

  printf '\nHarr installed in clean global-harness mode for Linux.\n'
  printf 'LeanCTX + CodeGraph are required; optional MCPs follow %s.\n' "$MCP_SELECTION"
  printf 'Change them later with: harr mcp configure\n'
  printf 'Project-level configs/files were not touched.\n'
  if (( ! start_now )); then printf 'Enabled service MCPs were not started/restarted. Start with: harr mcp start all\n'; fi
  printf 'Check with: harr status\nRollback with: harr uninstall\n'
  if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then printf 'Note: add %s to PATH.\n' "$BIN_DIR"; fi
}

main "$@"
