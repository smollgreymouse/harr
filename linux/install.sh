#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly FILES_DIR="${SOURCE_DIR}/files"
readonly SYSTEMD_SOURCE_DIR="${SOURCE_DIR}/systemd"

readonly BIN_DIR="${HOME}/.local/bin"
readonly LIBEXEC_DIR="${HOME}/.local/libexec/harr"
readonly CLI_LIB_DIR="${LIBEXEC_DIR}/cli"
readonly MCP_LIB_DIR="${LIBEXEC_DIR}/mcp"
readonly CONFIG_HOME="${HOME}/.config"
readonly HARR_CONFIG_DIR="${CONFIG_HOME}/harr"
readonly MCP_CONFIG_DIR="${HARR_CONFIG_DIR}/mcp"
readonly SYSTEMD_USER_DIR="${CONFIG_HOME}/systemd/user"
readonly GITLAB_ENV="${MCP_CONFIG_DIR}/gitlab.env"
readonly GITLAB_UNIT="harr-mcp-gitlab.service"

start_now=0

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

show_help() {
  cat <<'EOF'
Harr installer

Usage:
  ./install.sh [--start]

Options:
  --start     Start/restart managed MCP services after installation.
  -h, --help  Show this help.

The installation is user-level. Do not run it with sudo.
Existing ~/.config/harr/mcp/*.env files are preserved.
EOF
}

parse_arguments() {
  while (($#)); do
    case "$1" in
      --start)
        start_now=1
        shift
        ;;
      -h|--help)
        show_help
        exit 0
        ;;
      *)
        die "unknown option: $1 (see ./install.sh --help)"
        ;;
    esac
  done
}

detect_gitlab_bin() {
  local candidate
  for candidate in mcp-gitlab zereight-mcp-gitlab; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

existing_gitlab_bin() {
  local line
  [[ -r "$GITLAB_ENV" ]] || return 1
  line="$(grep -m1 '^HARR_MCP_GITLAB_BIN=' "$GITLAB_ENV" 2>/dev/null || true)"
  [[ -n "$line" ]] || return 1
  printf '%s\n' "${line#*=}"
}

install_runtime_files() {
  install -d -m 0755 \
    "$BIN_DIR" \
    "$CLI_LIB_DIR" \
    "$MCP_LIB_DIR" \
    "$MCP_CONFIG_DIR" \
    "$SYSTEMD_USER_DIR"

  install -m 0755 "${SOURCE_DIR}/harr" "${BIN_DIR}/harr"
  install -m 0644 "${FILES_DIR}/harr-cli/common.sh" "${CLI_LIB_DIR}/common.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/help.sh" "${CLI_LIB_DIR}/help.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/mcp.sh" "${CLI_LIB_DIR}/mcp.sh"
  install -m 0755 "${FILES_DIR}/mcp/gitlab-run" "${MCP_LIB_DIR}/gitlab-run"
  install -m 0644 "${SYSTEMD_SOURCE_DIR}/${GITLAB_UNIT}" "${SYSTEMD_USER_DIR}/${GITLAB_UNIT}"
}

install_gitlab_config() {
  local gitlab_bin=""

  if [[ -e "$GITLAB_ENV" ]]; then
    printf 'Preserving existing config: %s\n' "$GITLAB_ENV"
    gitlab_bin="$(existing_gitlab_bin || true)"
    if [[ -z "$gitlab_bin" || ! -x "$gitlab_bin" ]]; then
      printf 'Warning: configured HARR_MCP_GITLAB_BIN is missing or not executable.\n' >&2
      printf 'Edit %s before starting gitlab.\n' "$GITLAB_ENV" >&2
    fi
    return
  fi

  gitlab_bin="$(detect_gitlab_bin || true)"
  [[ -n "$gitlab_bin" ]] || die 'mcp-gitlab not found in PATH; install @zereight/mcp-gitlab first'

  cat >"$GITLAB_ENV" <<EOF
# Harr-managed GitLab MCP runtime.
# No GitLab PAT belongs here: REMOTE_AUTHORIZATION makes the MCP client send it.

HARR_MCP_GITLAB_BIN=${gitlab_bin}
HARR_MCP_ENDPOINT=http://127.0.0.1:3334/mcp

HOST=127.0.0.1
PORT=3334
STREAMABLE_HTTP=true
SSE=false
REMOTE_AUTHORIZATION=true
GITLAB_API_URL=https://gitlab.sca.ad-tech.ru/api/v4
GITLAB_PERMISSION_MODE=readonly
GITLAB_DISABLE_VERSION_CHECK=true
NO_PROXY=127.0.0.1,localhost
EOF
  chmod 0600 "$GITLAB_ENV"
  printf 'Created config: %s\n' "$GITLAB_ENV"
}

configure_systemd() {
  command -v systemctl >/dev/null 2>&1 || die 'systemctl not found'
  systemctl --user daemon-reload
  systemctl --user enable "$GITLAB_UNIT" >/dev/null

  if ((start_now)); then
    systemctl --user restart "$GITLAB_UNIT"
  fi
}

main() {
  [[ "$EUID" -ne 0 ]] || die 'run Harr installer as your normal user, without sudo'
  parse_arguments "$@"

  install_runtime_files
  install_gitlab_config
  configure_systemd

  printf '\nHarr installed.\n'
  printf 'CLI: %s\n' "${BIN_DIR}/harr"
  printf 'GitLab MCP: enabled for user startup\n'

  if ((start_now)); then
    "${BIN_DIR}/harr" mcp status gitlab
  else
    printf 'Current service was not started. Stop any foreground mcp-gitlab process, then run:\n'
    printf '  harr mcp start gitlab\n'
  fi

  if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    printf '\nNote: add %s to PATH.\n' "$BIN_DIR"
  fi
}

main "$@"
