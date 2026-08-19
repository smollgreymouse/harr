# LeanCTX configuration managed by Harr.

leanctx_template() { printf '%s\n' "${HARR_COMMON_DIR}/leanctx/config.base.toml"; }

cmd_leanctx_apply() {
  [[ $# -eq 0 ]] || die 'usage: harr leanctx apply'
  local src backup
  src="$(leanctx_template)"
  [[ -r "$src" ]] || die "LeanCTX base config not found: $src"
  require_mcp_manager
  migrate_gitlab_secret_from_leanctx
  ensure_private_dir "$HARR_LEANCTX_CONFIG_DIR"
  if [[ -e "$HARR_LEANCTX_CONFIG" ]] && ! grep -q '^# Managed by Harr\.$' "$HARR_LEANCTX_CONFIG" 2>/dev/null; then
    backup="${HARR_LEANCTX_CONFIG}.pre-harr.$(date +%Y%m%d-%H%M%S)"
    cp -a "$HARR_LEANCTX_CONFIG" "$backup"
    printf 'Backed up existing LeanCTX config to %s\n' "$backup"
  fi
  python3 "$HARR_MCP_MANAGER" render-leanctx \
    --base "$src" \
    --output "$HARR_LEANCTX_CONFIG" \
    --platform "${HARR_PLATFORM:-linux}" \
    --runner-command harr-mcp-run
  chmod 0600 "$HARR_LEANCTX_CONFIG"
  printf 'Applied Harr LeanCTX config from MCP registry: %s\n' "$HARR_LEANCTX_CONFIG"
  if [[ -x "${HOME}/.local/bin/lean-ctx" ]] && ! "${HOME}/.local/bin/lean-ctx" config validate >/dev/null 2>&1; then
    warn 'LeanCTX config validate did not succeed; run: lean-ctx config validate'
  fi
}

cmd_leanctx_status() {
  [[ $# -eq 0 ]] || die 'usage: harr leanctx status'
  local config_state=missing wrapper_state=missing
  [[ -r "$HARR_LEANCTX_CONFIG" ]] && config_state=present
  grep -q '^# Managed by Harr\.$' "$HARR_LEANCTX_CONFIG" 2>/dev/null && config_state=managed
  grep -q 'HARR_LEANCTX_WRAPPER=1' "${HOME}/.local/bin/lean-ctx" 2>/dev/null && wrapper_state=managed
  printf '%-18s %s\n' ITEM STATE
  printf '%-18s %s\n' launcher "$wrapper_state"
  printf '%-18s %s\n' config "$config_state"
  cmd_secret_status
}

cmd_leanctx() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    apply) cmd_leanctx_apply "$@" ;;
    status) cmd_leanctx_status "$@" ;;
    *) die 'usage: harr leanctx {apply|status}' ;;
  esac
}
