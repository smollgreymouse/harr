# Harr uninstall / rollback to the exact pre-Harr global harness snapshot.

readonly HARR_STATE_HELPER="${HARR_LIBEXEC_DIR}/state/harr-state"
readonly HARR_STATE_ROOT="${HOME}/.local/share/harr-state"

cmd_uninstall() {
  [[ $# -eq 0 ]] || die 'usage: harr uninstall'
  [[ -x "$HARR_STATE_HELPER" ]] || die "rollback helper missing: $HARR_STATE_HELPER"
  [[ -f "${HARR_STATE_ROOT}/pre-harr/complete" ]] || \
    die 'no clean pre-Harr snapshot exists; refusing destructive uninstall'

  local safety=''
  safety="$($HARR_STATE_HELPER safety-snapshot)"
  [[ -n "$safety" ]] && printf 'Saved current Harr state before rollback: %s\n' "$safety"

  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now harr-mcp-gitlab.service >/dev/null 2>&1 || true
  fi

  # The snapshot itself records whether every shared/global target existed.
  # It therefore removes Harr-created paths or restores old paths exactly.
  "$HARR_STATE_HELPER" restore

  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi

  # Rollback completed successfully; the independent uninstall safety snapshot
  # remains outside this directory.
  rm -rf -- "$HARR_STATE_ROOT"

  printf '\nHarr uninstalled and the exact pre-Harr global harness state was restored.\n'
  [[ -n "$safety" ]] && printf 'Safety snapshot of the removed Harr state: %s\n' "$safety"
  printf 'Project-level files were not touched.\n'
}
