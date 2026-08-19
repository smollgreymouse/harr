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
readonly SECRETS_DIR="${HARR_CONFIG_DIR}/secrets"
readonly SYSTEMD_USER_DIR="${CONFIG_HOME}/systemd/user"
readonly MCP_MANAGER="${COMMON_LIB_DIR}/mcp/manager.py"
readonly MCP_UNIT_TEMPLATE="harr-mcp@.service"
readonly LEGACY_GITLAB_UNIT="harr-mcp-gitlab.service"
readonly LEGACY_CODEGRAPH_UNIT="harr-mcp-codegraph.service"
readonly CLEAN_STATE_MARKER="${HOME}/.local/share/harr/state/pre-harr/complete"

start_now=0
harr_only=0
clean_takeover=0

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

show_help() {
  cat <<'EOF_HELP'
Harr installer

Usage:
  ./install.sh --clean [--start] [--harr-only]
  ./install.sh [--start] [--harr-only]

Harr owns its global harness layer after saving an exact rollback snapshot.
Project-level files are never touched. MCP definitions are platform-independent
and come from common/mcp/registry.json; the Linux layer only provides runtime,
path and systemd adapters.

Options:
  --clean      Required for the first install.
  --start      Start/restart all registry MCPs with lifecycle=service.
  --harr-only  Update Harr/global policy/config/skills without stack downloads.
  -h, --help   Show this help.

Rollback:
  harr uninstall
EOF_HELP
}

parse_arguments() {
  while (($#)); do
    case "$1" in
      --clean) clean_takeover=1 ;;
      --start) start_now=1 ;;
      --harr-only) harr_only=1 ;;
      -h|--help) show_help; exit 0 ;;
      *) die "unknown option: $1 (see ./install.sh --help)" ;;
    esac
    shift
  done
}

prepare_clean_ownership() {
  local state_source="${FILES_DIR}/state/harr-state"
  [[ -r "$state_source" ]] || die "missing Harr state helper: $state_source"
  if [[ -f "$CLEAN_STATE_MARKER" ]]; then
    ((clean_takeover)) && printf 'Clean ownership already initialized; preserving original pre-Harr snapshot.\n'
    bash "$state_source" snapshot >/dev/null
    return
  fi
  ((clean_takeover)) || die 'first Harr installation requires --clean; Harr will not merge itself into an existing global harness'
  bash "$state_source" snapshot
}

install_runtime_files() {
  install -d -m 0755 \
    "$BIN_DIR" "$LIBEXEC_DIR" "$CLI_LIB_DIR" "$MCP_LIB_DIR" "$LEANCTX_LIB_DIR" \
    "$STATE_LIB_DIR" "$MCP_CONFIG_DIR" "$SYSTEMD_USER_DIR"
  install -d -m 0700 "$SECRETS_DIR"

  rm -rf -- "$COMMON_LIB_DIR"
  cp -a "${COMMON_DIR}" "$COMMON_LIB_DIR"
  find "$COMMON_LIB_DIR" -type d -exec chmod 0755 {} +
  find "$COMMON_LIB_DIR" -type f -exec chmod 0644 {} +
  chmod 0755 "$MCP_MANAGER"

  install -m 0755 "${SOURCE_DIR}/harr" "${BIN_DIR}/harr"
  install -m 0755 "${FILES_DIR}/mcp/harr-mcp-run" "${BIN_DIR}/harr-mcp-run"
  # CodeGraph is also a user-facing CLI (init/status/etc.), independently of
  # its registry-managed MCP launch path. Preserve that convenience launcher.
  install -m 0755 "${FILES_DIR}/mcp/codegraph-cli" "${BIN_DIR}/codegraph"

  local f
  for f in common help agents hosts components secret leanctx mcp uninstall; do
    install -m 0644 "${FILES_DIR}/harr-cli/${f}.sh" "${CLI_LIB_DIR}/${f}.sh"
  done

  install -m 0755 "${FILES_DIR}/state/harr-state" "${STATE_LIB_DIR}/harr-state"
  install -m 0755 "${FILES_DIR}/leanctx/lean-ctx-wrapper" "${LEANCTX_LIB_DIR}/lean-ctx-wrapper"
  install -m 0644 "${SYSTEMD_SOURCE_DIR}/${MCP_UNIT_TEMPLATE}" "${SYSTEMD_USER_DIR}/${MCP_UNIT_TEMPLATE}"
}

install_mcp_configs() { python3 "$MCP_MANAGER" install-configs --config-dir "$MCP_CONFIG_DIR"; }

remove_legacy_services() {
  local unit path
  for unit in "$LEGACY_GITLAB_UNIT" "$LEGACY_CODEGRAPH_UNIT"; do
    path="${SYSTEMD_USER_DIR}/${unit}"
    if [[ -e "$path" ]]; then
      systemctl --user disable --now "$unit" >/dev/null 2>&1 || true
      rm -f -- "$path"
      printf 'Removed obsolete Harr unit: %s\n' "$unit"
    fi
  done
  rm -f -- "${MCP_CONFIG_DIR}/codegraph.env"
}

configure_systemd() {
  command -v systemctl >/dev/null 2>&1 || die 'systemctl not found'
  remove_legacy_services
  systemctl --user daemon-reload
  if ((harr_only)); then return; fi
  local name
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    systemctl --user enable "harr-mcp@${name}.service" >/dev/null
  done < <(python3 "$MCP_MANAGER" names --lifecycle service)
}

main() {
  [[ "$EUID" -ne 0 ]] || die 'run Harr installer as your normal user, without sudo'
  parse_arguments "$@"
  command -v python3 >/dev/null 2>&1 || die 'python3 is required for Harr host configuration management'

  prepare_clean_ownership
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

  printf '\nHarr installed in clean global-harness mode.\n'
  printf 'CLI: %s\n' "${BIN_DIR}/harr"
  printf 'Project-level configs/files were not touched.\n'
  printf 'MCP registry: %s\n' "${COMMON_LIB_DIR}/mcp/registry.json"
  if ((harr_only)); then
    printf 'Stack components were skipped (--harr-only). Install later with: harr install all\n'
  else
    printf 'Pinned stack installed; LeanCTX registered in Codex/OpenCode; global agent policy applied.\n'
  fi
  if (( ! start_now )); then
    printf 'Service MCPs were enabled but not started/restarted. Start all with:\n  harr mcp start all\n'
  fi
  printf '\nCheck the complete harness with:\n  harr status\n'
  printf 'Rollback completely with:\n  harr uninstall\n'
  printf '\nConfigure missing secrets listed by `harr secret status` with:\n  harr secret set NAME\n'

  if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then printf '\nNote: add %s to PATH.\n' "$BIN_DIR"; fi
}

main "$@"
