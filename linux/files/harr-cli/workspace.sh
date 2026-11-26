# Harr project Workspace management.

workspace_real_binary() {
  if [[ -n "${HARR_LEANCTX_REAL:-}" ]]; then
    printf '%s\n' "$HARR_LEANCTX_REAL"
  else
    leanctx_real_binary
  fi
}

workspace_usage() {
  cat <<'EOF_HELP'
Usage:
  harr workspace show
  harr workspace list
  harr workspace add PATH [--expected-revision N]
  harr workspace remove PATH [--expected-revision N]
  harr workspace sync PATH [PATH ...]
  harr workspace prune [--dry-run] [--all]
  harr workspace owner get ROOT --project PROJECT
  harr workspace owner claim ROOT --project PROJECT --owner-id ID [--owner-label LABEL] [--take-over-from ID]
  harr workspace owner release ROOT --project PROJECT --owner-id ID

Workspace is selected from the current Git repository root (or current directory
outside Git). Changes are live for already-running Harr-managed LeanCTX MCP sessions.
Prune removes only proven stale registrations by default; --all resets every
registration before rebuilding the Workspace list.
EOF_HELP
}

cmd_workspace() {
  local action="${1:-show}" real option seen_all=0 seen_dry_run=0
  shift || true
  case "$action" in
    show|list) [[ $# -eq 0 ]] || { workspace_usage >&2; return 2; } ;;
    add|remove)
      if [[ $# -ne 1 && $# -ne 3 ]]; then workspace_usage >&2; return 2; fi
      if [[ $# -eq 3 && "$2" != "--expected-revision" ]]; then workspace_usage >&2; return 2; fi
      ;;
    sync) [[ $# -ge 1 ]] || { workspace_usage >&2; return 2; } ;;
    owner) [[ $# -ge 2 ]] || { workspace_usage >&2; return 2; } ;;
    prune)
      for option in "$@"; do
        case "$option" in
          --all) [[ $seen_all -eq 0 ]] || { workspace_usage >&2; return 2; }; seen_all=1 ;;
          --dry-run) [[ $seen_dry_run -eq 0 ]] || { workspace_usage >&2; return 2; }; seen_dry_run=1 ;;
          *) workspace_usage >&2; return 2 ;;
        esac
      done
      ;;
    -h|--help|help) workspace_usage; return 0 ;;
    *) workspace_usage >&2; return 2 ;;
  esac
  if [[ "$action" == prune ]]; then
    real="${HARR_LEANCTX_REAL:-}"
  else
    real="$(workspace_real_binary)"
    [[ -x "$real" ]] || die "Harr LeanCTX binary missing: $real"
  fi
  python3 "$HARR_MCP_MANAGER" --registry "${HARR_MCP_EFFECTIVE:-${HARR_CONFIG_DIR}/mcp-registry.json}" \
    workspace "$action" "$@" --real "$real"
}
