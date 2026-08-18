# Harr-owned global host configuration. Project configuration is intentionally out of scope.

if [[ -d "${SELF_DIR:-}/files/hosts" ]]; then
  readonly HARR_HOST_HELPER_DIR="${SELF_DIR}/files/hosts"
else
  readonly HARR_HOST_HELPER_DIR="${HARR_LIBEXEC_DIR}/hosts"
fi
readonly HARR_OPENCODE_HELPER="${HARR_HOST_HELPER_DIR}/opencode-config.py"
readonly HARR_CLEAN_STATE_MARKER="${HOME}/.local/share/harr/state/pre-harr/complete"

require_global_harness_ownership() {
  [[ -f "$HARR_CLEAN_STATE_MARKER" ]] || \
    die 'global harness ownership is not initialized; rerun the repository installer with --clean'
}

cmd_hosts_apply() {
  [[ $# -eq 0 ]] || die 'usage: harr hosts apply'
  require_global_harness_ownership
  require_command python3
  [[ -r "$HARR_OPENCODE_HELPER" ]] || die "OpenCode helper missing: $HARR_OPENCODE_HELPER"
  python3 "$HARR_OPENCODE_HELPER" apply
}

cmd_hosts_status() {
  [[ $# -eq 0 ]] || die 'usage: harr hosts status'
  printf '%-12s %-14s %s\n' HOST STATE DETAIL
  if [[ -r "$HARR_OPENCODE_HELPER" ]] && command -v python3 >/dev/null 2>&1; then
    local line state detail
    line="$(python3 "$HARR_OPENCODE_HELPER" status 2>/dev/null || true)"
    state="$(printf '%s' "$line" | cut -f2)"
    detail="$(printf '%s' "$line" | cut -f3-)"
    printf '%-12s %-14s %s\n' opencode "${state:-unknown}" "${detail:--}"
  else
    printf '%-12s %-14s %s\n' opencode unavailable '-'
  fi
  # Codex config.toml is deliberately preserved until Harr has a verified
  # versioned writer for its MCP registry. Harr currently owns Codex AGENTS and
  # its Harr/LeanCTX skills only.
  printf '%-12s %-14s %s\n' codex preserved 'config.toml unchanged; AGENTS/skills managed by Harr'
}

cmd_hosts() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    apply) cmd_hosts_apply "$@" ;;
    status) cmd_hosts_status "$@" ;;
    help|-h|--help)
      printf '%s\n' 'Usage:' \
        '  harr hosts apply' \
        '  harr hosts status'
      ;;
    *) die "unknown hosts command: $command (see harr help)" ;;
  esac
}
