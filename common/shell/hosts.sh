# Harr-owned global host configuration. Project configuration is intentionally out of scope.

if [[ -d "${SELF_DIR:-}/../common/hosts" ]]; then
  readonly HARR_HOST_HELPER_DIR="${SELF_DIR}/../common/hosts"
else
  readonly HARR_HOST_HELPER_DIR="${HARR_COMMON_DIR}/hosts"
fi
readonly HARR_OPENCODE_HELPER="${HARR_HOST_HELPER_DIR}/opencode-config.py"
readonly HARR_CODEX_HELPER="${HARR_HOST_HELPER_DIR}/codex-config.py"
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
  [[ -r "$HARR_CODEX_HELPER" ]] || die "Codex helper missing: $HARR_CODEX_HELPER"
  python3 "$HARR_OPENCODE_HELPER" apply
  python3 "$HARR_CODEX_HELPER" apply
}

host_helper_status_row() {
  local host="$1" helper="$2" line state detail
  if [[ -r "$helper" ]] && command -v python3 >/dev/null 2>&1; then
    line="$(python3 "$helper" status 2>/dev/null || true)"
    state="$(printf '%s' "$line" | cut -f2)"
    detail="$(printf '%s' "$line" | cut -f3-)"
    printf '%-12s %-14s %s\n' "$host" "${state:-unknown}" "${detail:--}"
  else
    printf '%-12s %-14s %s\n' "$host" unavailable '-'
  fi
}

cmd_hosts_status() {
  [[ $# -eq 0 ]] || die 'usage: harr hosts status'
  printf '%-12s %-14s %s\n' HOST STATE DETAIL
  host_helper_status_row opencode "$HARR_OPENCODE_HELPER"
  host_helper_status_row codex "$HARR_CODEX_HELPER"
}

cmd_hosts() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    apply) cmd_hosts_apply "$@" ;;
    status) cmd_hosts_status "$@" ;;
    help|-h|--help) printf '%s\n' 'Usage:' '  harr hosts apply' '  harr hosts status' ;;
    *) die "unknown hosts command: $command (see harr help)" ;;
  esac
}
