# Harr Git transport helpers. GitLab HTTPS transport preserves the real local commit/SHA.

cmd_git_transport() {
  ensure_mcp_effective
  mcp_manager names | grep -Fxq gitlab || die 'GitLab MCP is disabled; enable it before using Harr GitLab transport'
  require_command git
  require_command python3
}

cmd_git() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    push)
      cmd_git_transport
      python3 "${HARR_COMMON_DIR}/gitlab/git_https.py" push \
        --registry "$HARR_MCP_EFFECTIVE" \
        --config-dir "$HARR_MCP_CONFIG_DIR" \
        --secrets-dir "$HARR_SECRETS_DIR" \
        -- "$@"
      ;;
    publish)
      [[ $# -le 1 ]] || die 'usage: harr git publish [remote]'
      cmd_git_transport
      python3 "${HARR_COMMON_DIR}/gitlab/git_https.py" publish \
        --registry "$HARR_MCP_EFFECTIVE" \
        --config-dir "$HARR_MCP_CONFIG_DIR" \
        --secrets-dir "$HARR_SECRETS_DIR" \
        "${1:-origin}"
      ;;
    *) die 'usage: harr git {publish [remote]|push [git-push-options] [remote] [refspec...]}' ;;
  esac
}
