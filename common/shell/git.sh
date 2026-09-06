# Harr host Git transport helpers.

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
