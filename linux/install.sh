#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly FILES_DIR="${SOURCE_DIR}/files"
readonly SYSTEMD_SOURCE_DIR="${SOURCE_DIR}/systemd"
readonly BIN_DIR="${HOME}/.local/bin"
readonly LIBEXEC_DIR="${HOME}/.local/libexec/harr"
readonly CLI_LIB_DIR="${LIBEXEC_DIR}/cli"
readonly MCP_LIB_DIR="${LIBEXEC_DIR}/mcp"
readonly LEANCTX_LIB_DIR="${LIBEXEC_DIR}/leanctx"
readonly SKILLS_LIB_DIR="${LIBEXEC_DIR}/skills"
readonly CONFIG_HOME="${HOME}/.config"
readonly HARR_CONFIG_DIR="${CONFIG_HOME}/harr"
readonly MCP_CONFIG_DIR="${HARR_CONFIG_DIR}/mcp"
readonly SECRETS_DIR="${HARR_CONFIG_DIR}/secrets"
readonly SYSTEMD_USER_DIR="${CONFIG_HOME}/systemd/user"
readonly GITLAB_ENV="${MCP_CONFIG_DIR}/gitlab.env"
readonly GITLAB_UNIT="harr-mcp-gitlab.service"
readonly LEGACY_CODEGRAPH_UNIT="harr-mcp-codegraph.service"

start_now=0
harr_only=0

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

show_help() {
  cat <<'EOF_HELP'
Harr installer

Usage:
  ./install.sh [--start] [--harr-only]

Default installation bootstraps Harr and installs the complete pinned stack:
  LeanCTX 3.9.15
  GitLab MCP
  CodeGraph
  Harr-aware agent skills for Codex and OpenCode

CodeGraph is installed by Harr but remains a stdio downstream spawned by LeanCTX,
so it automatically inherits the agent/project working directory.

Options:
  --start      Start/restart Harr long-lived MCP services after installation.
  --harr-only  Install/update Harr itself and managed agent skills but do not download stack components.
  -h, --help   Show this help.

The installation is user-level. Do not run it with sudo.
Existing Harr GitLab env is preserved and migrated where required.
Existing non-Harr LeanCTX config is backed up before Harr takes ownership.
Existing non-Harr lean-ctx/harr skills are backed up before Harr takes ownership.
EOF_HELP
}

parse_arguments() {
  while (($#)); do
    case "$1" in
      --start) start_now=1 ;;
      --harr-only) harr_only=1 ;;
      -h|--help) show_help; exit 0 ;;
      *) die "unknown option: $1 (see ./install.sh --help)" ;;
    esac
    shift
  done
}

install_skill_sources() {
  local skill source target
  for skill in lean-ctx harr; do
    source="${FILES_DIR}/skills/${skill}"
    target="${SKILLS_LIB_DIR}/${skill}"
    [[ -r "${source}/SKILL.md" ]] || die "missing Harr skill source: ${source}/SKILL.md"
    rm -rf -- "$target"
    install -d -m 0755 "$target"
    cp -a "${source}/." "$target/"
    find "$target" -type d -exec chmod 0755 {} +
    find "$target" -type f -exec chmod 0644 {} +
  done
}

install_runtime_files() {
  install -d -m 0755 \
    "$BIN_DIR" \
    "$CLI_LIB_DIR" \
    "$MCP_LIB_DIR" \
    "$LEANCTX_LIB_DIR" \
    "$SKILLS_LIB_DIR" \
    "$MCP_CONFIG_DIR" \
    "$SYSTEMD_USER_DIR"
  install -d -m 0700 "$SECRETS_DIR"

  install -m 0755 "${SOURCE_DIR}/harr" "${BIN_DIR}/harr"
  install -m 0644 "${FILES_DIR}/harr-cli/common.sh" "${CLI_LIB_DIR}/common.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/help.sh" "${CLI_LIB_DIR}/help.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/agents.sh" "${CLI_LIB_DIR}/agents.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/components.sh" "${CLI_LIB_DIR}/components.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/secret.sh" "${CLI_LIB_DIR}/secret.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/leanctx.sh" "${CLI_LIB_DIR}/leanctx.sh"
  install -m 0644 "${FILES_DIR}/harr-cli/mcp.sh" "${CLI_LIB_DIR}/mcp.sh"

  install -m 0755 "${FILES_DIR}/mcp/gitlab-run" "${MCP_LIB_DIR}/gitlab-run"
  install -m 0755 "${FILES_DIR}/mcp/codegraph-cli" "${MCP_LIB_DIR}/codegraph-cli"
  install -m 0755 "${FILES_DIR}/leanctx/lean-ctx-wrapper" "${LEANCTX_LIB_DIR}/lean-ctx-wrapper"
  install -m 0600 "${FILES_DIR}/leanctx/config.toml" "${LEANCTX_LIB_DIR}/config.toml"
  install_skill_sources

  install -m 0644 "${SYSTEMD_SOURCE_DIR}/${GITLAB_UNIT}" "${SYSTEMD_USER_DIR}/${GITLAB_UNIT}"
}

set_env_key() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp "${file}.XXXXXX")"
  if [[ -f "$file" ]]; then
    awk -v k="$key" -v v="$value" '
      BEGIN { done=0 }
      $0 ~ "^" k "=" { if (!done) print k "=" v; done=1; next }
      { print }
      END { if (!done) print k "=" v }
    ' "$file" >"$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >"$tmp"
  fi
  chmod 0600 "$tmp"
  mv -f "$tmp" "$file"
}

install_mcp_config() {
  if [[ ! -e "$GITLAB_ENV" ]]; then
    install -m 0600 "${FILES_DIR}/mcp/gitlab.env.example" "$GITLAB_ENV"
    printf 'Created config: %s\n' "$GITLAB_ENV"
  else
    printf 'Preserving existing config: %s\n' "$GITLAB_ENV"
  fi
  set_env_key "$GITLAB_ENV" GITLAB_PERMISSION_MODE full
  set_env_key "$GITLAB_ENV" GITLAB_TOOLSETS all
}

remove_legacy_codegraph_service() {
  local legacy_path="${SYSTEMD_USER_DIR}/${LEGACY_CODEGRAPH_UNIT}"
  if [[ -e "$legacy_path" ]]; then
    systemctl --user disable --now "$LEGACY_CODEGRAPH_UNIT" >/dev/null 2>&1 || true
    rm -f -- "$legacy_path"
    rm -f -- "${MCP_CONFIG_DIR}/codegraph.env"
    printf 'Removed obsolete Harr CodeGraph HTTP bridge service; CodeGraph now runs via LeanCTX stdio.\n'
  fi
}

configure_systemd() {
  command -v systemctl >/dev/null 2>&1 || die 'systemctl not found'
  remove_legacy_codegraph_service
  systemctl --user daemon-reload
  if (( ! harr_only )); then
    systemctl --user enable "$GITLAB_UNIT" >/dev/null
  fi
}

main() {
  [[ "$EUID" -ne 0 ]] || die 'run Harr installer as your normal user, without sudo'
  parse_arguments "$@"

  install_runtime_files
  install_mcp_config
  configure_systemd

  if (( ! harr_only )); then
    "${BIN_DIR}/harr" install all
  else
    "${BIN_DIR}/harr" agents apply all
  fi

  if ((start_now)); then
    "${BIN_DIR}/harr" mcp restart all
  fi

  printf '\nHarr installed.\n'
  printf 'CLI: %s\n' "${BIN_DIR}/harr"
  if ((harr_only)); then
    printf 'Stack components were skipped (--harr-only). Install later with: harr install all\n'
  else
    printf 'Stack components installed and LeanCTX config applied.\n'
  fi
  printf 'Harr-aware LeanCTX/Harr skills applied for Codex and OpenCode.\n'
  printf 'GitLab MCP service is enabled for user startup.\n'
  printf 'CodeGraph is spawned on demand by LeanCTX and is not a systemd service.\n'

  if (( ! start_now )); then
    printf 'GitLab service was not started/restarted. Stop any foreground server using port 3334, then run:\n'
    printf '  harr mcp start gitlab\n'
  fi

  printf '\nCheck the complete stack with:\n  harr status\n'
  if [[ ! -s "${SECRETS_DIR}/gitlab-pat" ]]; then
    printf '\nGitLab PAT is not configured. If it was not migrated from the old LeanCTX config, run:\n'
    printf '  harr secret set gitlab\n'
  fi

  if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    printf '\nNote: add %s to PATH.\n' "$BIN_DIR"
  fi
}

main "$@"
