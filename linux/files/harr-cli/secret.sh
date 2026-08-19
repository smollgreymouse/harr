# Secret management. Harr never prints stored secret material.

write_secret_file() {
  local file="$1" value="$2"
  ensure_private_dir "$HARR_SECRETS_DIR"
  umask 077
  printf '%s\n' "$value" >"$file"
  chmod 0600 "$file"
}

secret_meta_field() {
  local name="$1" field="$2"
  require_mcp_manager
  python3 "$HARR_MCP_MANAGER" secret "$name" | \
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[1], ""))' "$field"
}

secret_file() {
  printf '%s/%s\n' "$HARR_SECRETS_DIR" "$(secret_meta_field "$1" file)"
}

migrate_gitlab_secret_from_leanctx() {
  local target
  target="$(secret_file gitlab 2>/dev/null || true)"
  [[ -n "$target" ]] || return 0
  [[ -s "$target" ]] && return 0
  [[ -r "$HARR_LEANCTX_CONFIG" ]] || return 0

  local token
  token="$(sed -n 's/^[[:space:]]*Private-Token[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$HARR_LEANCTX_CONFIG" | head -1)"
  [[ -n "$token" ]] || return 0

  write_secret_file "$target" "$token"
  printf 'Migrated GitLab PAT from existing LeanCTX config into Harr secret storage.\n'
}

cmd_secret_set() {
  local name="$1" file prompt value=''
  file="$(secret_file "$name")"
  prompt="$(secret_meta_field "$name" prompt)"
  if [[ ! -t 0 ]]; then
    IFS= read -r value || true
  else
    read -rsp "${prompt:-$name}: " value
    printf '\n'
  fi
  [[ -n "$value" ]] || die "empty $name secret was not stored"
  write_secret_file "$file" "$value"
  printf '%s secret stored in %s (0600).\n' "$name" "$file"
}

cmd_secret_status() {
  [[ $# -eq 0 ]] || die 'usage: harr secret status'
  require_mcp_manager
  printf '%-16s %s\n' SECRET STATE
  local line name file
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    name="$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
    file="$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["file"])')"
    if [[ -s "${HARR_SECRETS_DIR}/${file}" ]]; then
      printf '%-16s %s\n' "$name" configured
    else
      printf '%-16s %s\n' "$name" missing
    fi
  done < <(python3 "$HARR_MCP_MANAGER" secrets)
}

cmd_secret_unset() {
  local name="$1" file
  file="$(secret_file "$name")"
  rm -f -- "$file"
  printf '%s secret removed from Harr secret storage.\n' "$name"
}

cmd_secret() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    set)
      [[ $# -eq 1 ]] || die 'usage: harr secret set NAME'
      cmd_secret_set "$1"
      ;;
    status) cmd_secret_status "$@" ;;
    unset)
      [[ $# -eq 1 ]] || die 'usage: harr secret unset NAME'
      cmd_secret_unset "$1"
      ;;
    *) die 'usage: harr secret {set NAME|status|unset NAME}' ;;
  esac
}
