# Harr Git transport helpers. GitLab HTTPS transport preserves the real local commit/SHA.

readonly HARR_GIT_HOST="${HARR_COMMON_DIR}/git_host/git_host.py"

cmd_git() {
  (($#)) || die 'usage: harr git <git-arguments>'
  require_command python3
  [[ -r "$HARR_GIT_HOST" ]] || die "Harr Git host client missing: $HARR_GIT_HOST"
  python3 "$HARR_GIT_HOST" client -- "$@"
}

cmd_git_host_status() {
  local state=missing
  if [[ -r "$HARR_GIT_HOST" ]]; then
    state="$(python3 "$HARR_GIT_HOST" health 2>/dev/null || true)"
    [[ -n "$state" ]] || state=unreachable
  fi
  printf '%-18s %s\n' 'host-git-service' "$state"
}

cmd_gitlab_transport() {
  ensure_mcp_effective
  mcp_manager names | grep -Fxq gitlab || die 'GitLab MCP is disabled; enable it before using Harr GitLab transport'
  require_command git
  require_command python3
}

cmd_gitlab() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    fetch)
      cmd_gitlab_transport
      python3 "${HARR_COMMON_DIR}/gitlab/git_https.py" fetch \
        --registry "$HARR_MCP_EFFECTIVE" \
        --config-dir "$HARR_MCP_CONFIG_DIR" \
        --secrets-dir "$HARR_SECRETS_DIR" \
        -- "$@"
      ;;
    push)
      cmd_gitlab_transport
      python3 "${HARR_COMMON_DIR}/gitlab/git_https.py" push \
        --registry "$HARR_MCP_EFFECTIVE" \
        --config-dir "$HARR_MCP_CONFIG_DIR" \
        --secrets-dir "$HARR_SECRETS_DIR" \
        -- "$@"
      ;;
    publish)
      [[ $# -le 1 ]] || die 'usage: harr gitlab publish [remote]'
      cmd_gitlab_transport
      python3 "${HARR_COMMON_DIR}/gitlab/git_https.py" publish \
        --registry "$HARR_MCP_EFFECTIVE" \
        --config-dir "$HARR_MCP_CONFIG_DIR" \
        --secrets-dir "$HARR_SECRETS_DIR" \
        "${1:-origin}"
      ;;
    *) die 'usage: harr gitlab {fetch [git-fetch-options] [remote] [refspec...]|publish [remote]|push [git-push-options] [remote] [refspec...]}' ;;
  esac
}
