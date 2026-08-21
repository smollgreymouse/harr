# Cross-platform MCP selection/effective-registry helpers for POSIX hosts.

readonly HARR_MCP_CATALOG="${HARR_MCP_CATALOG:-${HARR_COMMON_DIR}/mcp/registry.json}"
readonly HARR_MCP_SELECTOR="${HARR_MCP_SELECTOR:-${HARR_COMMON_DIR}/mcp/selector.py}"
readonly HARR_MCP_ASSETS="${HARR_MCP_ASSETS:-${HARR_COMMON_DIR}/mcp/assets.py}"
readonly HARR_MCP_SELECTION="${HARR_MCP_SELECTION:-${HARR_CONFIG_DIR}/mcp-selection.json}"
readonly HARR_MCP_EFFECTIVE="${HARR_MCP_EFFECTIVE:-${HARR_CONFIG_DIR}/mcp-registry.json}"

require_mcp_selector() {
  [[ -r "$HARR_MCP_CATALOG" ]] || die "Harr MCP catalog missing: $HARR_MCP_CATALOG"
  [[ -r "$HARR_MCP_SELECTOR" ]] || die "Harr MCP selector missing: $HARR_MCP_SELECTOR"
  require_command python3
}

ensure_mcp_effective() {
  require_mcp_selector
  if [[ ! -r "$HARR_MCP_SELECTION" || ! -r "$HARR_MCP_EFFECTIVE" ]]; then
    ensure_private_dir "$HARR_CONFIG_DIR"
    python3 "$HARR_MCP_SELECTOR" \
      --catalog "$HARR_MCP_CATALOG" \
      --selection "$HARR_MCP_SELECTION" \
      --effective "$HARR_MCP_EFFECTIVE" \
      --default all >/dev/null
  fi
}

mcp_manager() {
  require_mcp_manager
  ensure_mcp_effective
  python3 "$HARR_MCP_MANAGER" --registry "$HARR_MCP_EFFECTIVE" "$@"
}

mcp_catalog_manager() {
  require_mcp_manager
  python3 "$HARR_MCP_MANAGER" --registry "$HARR_MCP_CATALOG" "$@"
}

mcp_select() {
  local mode="${1:-configure}" value="${2:-}" default="${3:-required}"
  require_mcp_selector
  ensure_private_dir "$HARR_CONFIG_DIR"
  local args=(--catalog "$HARR_MCP_CATALOG" --selection "$HARR_MCP_SELECTION" --effective "$HARR_MCP_EFFECTIVE" --default "$default")
  case "$mode" in
    configure) args+=(--configure) ;;
    spec) args+=(--spec "$value") ;;
    keep) ;;
    *) die "unknown MCP selection mode: $mode" ;;
  esac
  python3 "$HARR_MCP_SELECTOR" "${args[@]}"
}

mcp_available() {
  require_mcp_selector
  local spec=''
  if [[ -r "$HARR_MCP_SELECTION" ]]; then
    python3 "$HARR_MCP_SELECTOR" --catalog "$HARR_MCP_CATALOG" --selection "$HARR_MCP_SELECTION" --effective "$HARR_MCP_EFFECTIVE" --default required
  else
    python3 "$HARR_MCP_SELECTOR" --catalog "$HARR_MCP_CATALOG" --selection "$HARR_MCP_SELECTION" --effective "$HARR_MCP_EFFECTIVE" --default all
  fi
}
