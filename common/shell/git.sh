# Harr Git transport helpers. GitLab HTTPS fallback preserves the real local commit/SHA.

cmd_git() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    push)
      ensure_mcp_effective
      mcp_manager names | grep -Fxq gitlab || die 'GitLab MCP is disabled; enable it before using `harr git push`'
      require_command git
      require_command python3
      python3 "${HARR_COMMON_DIR}/gitlab/git_https.py" push \
        --registry "$HARR_MCP_EFFECTIVE" \
        --config-dir "$HARR_MCP_CONFIG_DIR" \
        --secrets-dir "$HARR_SECRETS_DIR" \
        -- "$@"
      ;;
    *) die 'usage: harr git push [git-push-options] [remote] [refspec...]' ;;
  esac
}
