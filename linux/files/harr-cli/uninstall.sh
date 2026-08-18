# Harr uninstall / rollback to the exact pre-Harr global harness snapshot.

readonly HARR_STATE_HELPER="${HARR_LIBEXEC_DIR}/state/harr-state"
readonly HARR_SHARE_ROOT="${HOME}/.local/share/harr"

cmd_uninstall() {
  [[ $# -eq 0 ]] || die 'usage: harr uninstall'
  [[ -x "$HARR_STATE_HELPER" ]] || die "rollback helper missing: $HARR_STATE_HELPER"
  [[ -f "${HARR_SHARE_ROOT}/state/pre-harr/complete" ]] || \
    die 'no clean pre-Harr snapshot exists; refusing destructive uninstall'

  local safety=''
  safety="$($HARR_STATE_HELPER safety-snapshot)"
  [[ -n "$safety" ]] && printf 'Saved current Harr state before rollback: %s\n' "$safety"

  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now harr-mcp-gitlab.service >/dev/null 2>&1 || true
  fi

  "$HARR_STATE_HELPER" restore

  # Paths below are Harr-private namespaces, never project paths or extension
  # directories. Restored shared targets above are intentionally left intact.
  rm -rf -- \
    "${HOME}/.config/harr" \
    "${HOME}/.local/libexec/harr" \
    "${HOME}/.local/share/harr"

  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi

  printf '\nHarr uninstalled and the pre-Harr global harness state was restored.\n'
  [[ -n "$safety" ]] && printf 'Safety snapshot of the removed Harr state: %s\n' "$safety"
  printf 'Project-level files were not touched.\n'
}
