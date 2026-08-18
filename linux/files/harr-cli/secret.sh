# Secret management. Harr never prints stored secret material.

write_secret_file() {
  local file="$1" value="$2"
  ensure_private_dir "$HARR_SECRETS_DIR"
  umask 077
  printf '%s\n' "$value" >"$file"
  chmod 0600 "$file"
}

migrate_gitlab_secret_from_leanctx() {
  [[ -s "$HARR_GITLAB_SECRET_FILE" ]] && return 0
  [[ -r "$HARR_LEANCTX_CONFIG" ]] || return 0

  local token
  token="$(sed -n 's/^[[:space:]]*Private-Token[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$HARR_LEANCTX_CONFIG" | head -1)"
  [[ -n "$token" ]] || return 0

  write_secret_file "$HARR_GITLAB_SECRET_FILE" "$token"
  printf 'Migrated GitLab PAT from existing LeanCTX config into Harr secret storage.\n'
}

cmd_secret_set() {
  local name="$1"
  case "$name" in
    gitlab)
      local value=''
      if [[ ! -t 0 ]]; then
        IFS= read -r value || true
      else
        read -rsp 'GitLab PAT: ' value
        printf '\n'
      fi
      [[ -n "$value" ]] || die 'empty GitLab PAT was not stored'
      write_secret_file "$HARR_GITLAB_SECRET_FILE" "$value"
      printf 'GitLab PAT stored in %s (0600).\n' "$HARR_GITLAB_SECRET_FILE"
      ;;
    *) die "unknown secret: $name" ;;
  esac
}

cmd_secret_status() {
  [[ $# -eq 0 ]] || die 'usage: harr secret status'
  printf '%-16s %s\n' SECRET STATE
  if [[ -s "$HARR_GITLAB_SECRET_FILE" ]]; then
    printf '%-16s %s\n' gitlab configured
  else
    printf '%-16s %s\n' gitlab missing
  fi
}

cmd_secret_unset() {
  local name="$1"
  case "$name" in
    gitlab)
      rm -f -- "$HARR_GITLAB_SECRET_FILE"
      printf 'GitLab PAT removed from Harr secret storage.\n'
      ;;
    *) die "unknown secret: $name" ;;
  esac
}

cmd_secret() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    set)
      [[ $# -eq 1 ]] || die 'usage: harr secret set gitlab'
      cmd_secret_set "$1"
      ;;
    status) cmd_secret_status "$@" ;;
    unset)
      [[ $# -eq 1 ]] || die 'usage: harr secret unset gitlab'
      cmd_secret_unset "$1"
      ;;
    *) die 'usage: harr secret {set gitlab|status|unset gitlab}' ;;
  esac
}
