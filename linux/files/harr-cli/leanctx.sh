# LeanCTX configuration managed by Harr.

leanctx_template() {
  printf '%s\n' "${HARR_LIBEXEC_DIR}/leanctx/config.toml"
}

cmd_leanctx_apply() {
  [[ $# -eq 0 ]] || die 'usage: harr leanctx apply'
  local src backup
  src="$(leanctx_template)"
  [[ -r "$src" ]] || die "LeanCTX template not found: $src"

  migrate_gitlab_secret_from_leanctx
  ensure_private_dir "$HARR_LEANCTX_CONFIG_DIR"

  if [[ -e "$HARR_LEANCTX_CONFIG" ]] && ! grep -q '^# Managed by Harr\.$' "$HARR_LEANCTX_CONFIG" 2>/dev/null; then
    backup="${HARR_LEANCTX_CONFIG}.pre-harr.$(date +%Y%m%d-%H%M%S)"
    cp -a "$HARR_LEANCTX_CONFIG" "$backup"
    printf 'Backed up existing LeanCTX config to %s\n' "$backup"
  fi

  install -m 0600 "$src" "$HARR_LEANCTX_CONFIG"
  printf 'Applied Harr LeanCTX config: %s\n' "$HARR_LEANCTX_CONFIG"

  if [[ -x "${HOME}/.local/bin/lean-ctx" ]]; then
    if ! "${HOME}/.local/bin/lean-ctx" config validate >/dev/null 2>&1; then
      warn 'LeanCTX config validate did not succeed; run: lean-ctx config validate'
    fi
  fi

  if [[ ! -s "$HARR_GITLAB_SECRET_FILE" ]]; then
    warn 'GitLab PAT is not configured; run: harr secret set gitlab'
  fi
}

cmd_leanctx_status() {
  [[ $# -eq 0 ]] || die 'usage: harr leanctx status'
  local config_state secret_state wrapper_state
  config_state=missing
  secret_state=missing
  wrapper_state=missing
  [[ -r "$HARR_LEANCTX_CONFIG" ]] && config_state=present
  grep -q '^# Managed by Harr\.$' "$HARR_LEANCTX_CONFIG" 2>/dev/null && config_state=managed
  [[ -s "$HARR_GITLAB_SECRET_FILE" ]] && secret_state=configured
  grep -q 'HARR_LEANCTX_WRAPPER=1' "${HOME}/.local/bin/lean-ctx" 2>/dev/null && wrapper_state=managed

  printf '%-18s %s\n' ITEM STATE
  printf '%-18s %s\n' launcher "$wrapper_state"
  printf '%-18s %s\n' config "$config_state"
  printf '%-18s %s\n' gitlab-secret "$secret_state"
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
