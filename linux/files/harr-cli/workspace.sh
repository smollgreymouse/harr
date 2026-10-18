# Harr project Workspace management.

workspace_real_binary() {
  if [[ -n "${HARR_LEANCTX_REAL:-}" ]]; then
    printf '%s\n' "$HARR_LEANCTX_REAL"
  else
    printf '%s/lean-ctx/%s/lean-ctx\n' "$HARR_VENDOR_DIR" "$HARR_LEANCTX_BUILD"
  fi
}

workspace_usage() {
  cat <<'EOF_HELP'
Usage:
  harr workspace show
  harr workspace list
  harr workspace add PATH
  harr workspace remove PATH
  harr workspace sync PATH [PATH ...]

Workspace is selected from the current Git repository root (or current directory
outside Git). Changes are live for already-running Harr-managed LeanCTX MCP sessions.
EOF_HELP
}

cmd_workspace() {
  local action="${1:-show}" real
  shift || true
  case "$action" in
    show|list) [[ $# -eq 0 ]] || { workspace_usage >&2; return 2; } ;;
    add|remove) [[ $# -eq 1 ]] || { workspace_usage >&2; return 2; } ;;
    sync) [[ $# -ge 1 ]] || { workspace_usage >&2; return 2; } ;;
    -h|--help|help) workspace_usage; return 0 ;;
    *) workspace_usage >&2; return 2 ;;
  esac
  real="$(workspace_real_binary)"
  [[ -x "$real" ]] || die "Harr LeanCTX binary missing: $real"
  python3 "$HARR_MCP_MANAGER" --registry "${HARR_MCP_EFFECTIVE:-${HARR_CONFIG_DIR}/mcp-registry.json}" \
    workspace "$action" "$@" --real "$real"
}
