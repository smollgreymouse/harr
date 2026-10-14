#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SELF="$(readlink -f "${BASH_SOURCE[0]}")"
DEFAULT_ROOT="${HARR_SMOKE_CHECKPOINT_ROOT:-${HOME}/.local/share/harr-smoke-checkpoints}"
XDG_CONFIG_HOME_REAL="${XDG_CONFIG_HOME:-${HOME}/.config}"
CODEX_HOME_REAL="${CODEX_HOME:-${HOME}/.codex}"
SYSTEMD_USER_ROOT="${XDG_CONFIG_HOME_REAL}/systemd/user"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

safe_key() {
  printf '%s' "$1" | tr -cs 'A-Za-z0-9._-' '_'
}

snapshot_item() {
  local root="$1" key="$2" target="$3" dir
  dir="${root}/items/$(safe_key "$key")"
  mkdir -p "$dir"
  printf '%s\n' "$target" >"${dir}/target"
  if [[ -e "$target" || -L "$target" ]]; then
    printf '1\n' >"${dir}/existed"
    cp -a -- "$target" "${dir}/payload"
  else
    printf '0\n' >"${dir}/existed"
  fi
}

base_targets() {
  cat <<EOF
harr-libexec|${HOME}/.local/libexec/harr
harr-launcher|${HOME}/.local/bin/harr
leanctx-launcher|${HOME}/.local/bin/lean-ctx
mcp-runner|${HOME}/.local/bin/harr-mcp-run
codegraph-launcher|${HOME}/.local/bin/codegraph
harr-config|${XDG_CONFIG_HOME_REAL}/harr
leanctx-config|${XDG_CONFIG_HOME_REAL}/lean-ctx
codex-agents|${CODEX_HOME_REAL}/AGENTS.md
codex-config|${CODEX_HOME_REAL}/config.toml
codex-skill-harr|${CODEX_HOME_REAL}/skills/harr
codex-skill-leanctx|${CODEX_HOME_REAL}/skills/lean-ctx
codex-skill-gigacode|${CODEX_HOME_REAL}/skills/gigacode-executor
opencode-agents|${XDG_CONFIG_HOME_REAL}/opencode/AGENTS.md
opencode-jsonc|${XDG_CONFIG_HOME_REAL}/opencode/opencode.jsonc
opencode-json|${XDG_CONFIG_HOME_REAL}/opencode/opencode.json
opencode-skill-harr|${XDG_CONFIG_HOME_REAL}/opencode/skills/harr
opencode-skill-leanctx|${XDG_CONFIG_HOME_REAL}/opencode/skills/lean-ctx
opencode-skill-gigacode|${XDG_CONFIG_HOME_REAL}/opencode/skills/gigacode-executor
opencode-leanctx|${XDG_CONFIG_HOME_REAL}/opencode/lean-ctx
opencode-desktop-leanctx|${XDG_CONFIG_HOME_REAL}/ai.opencode.desktop/lean-ctx
harr-share|${HOME}/.local/share/harr
harr-state|${HOME}/.local/share/harr-state
leanctx-share|${HOME}/.local/share/lean-ctx
leanctx-state|${HOME}/.local/state/lean-ctx
leanctx-cache|${HOME}/.cache/lean-ctx
EOF
}

systemd_available() {
  [[ "${HARR_SMOKE_SYSTEMD:-1}" != 0 ]] && command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1
}

capture_services() {
  local root="$1" unit enabled active
  : >"${root}/services.tsv"
  systemd_available || return 0
  {
    systemctl --user list-unit-files 'harr*' --no-legend --plain 2>/dev/null | awk '{print $1}'
    systemctl --user list-units 'harr*' --all --type=service --no-legend --plain 2>/dev/null | awk '{print $1}'
  } | sed '/^$/d' | sort -u | while IFS= read -r unit; do
    enabled="$(systemctl --user is-enabled "$unit" 2>/dev/null || true)"
    active="$(systemctl --user is-active "$unit" 2>/dev/null || true)"
    printf '%s\t%s\t%s\n' "$unit" "${enabled:-unknown}" "${active:-unknown}"
  done >"${root}/services.tsv"
}

capture_metadata() {
  local root="$1"
  mkdir -p "${root}/metadata"
  date --iso-8601=seconds >"${root}/metadata/created-at" 2>/dev/null || date >"${root}/metadata/created-at"
  printf '%s\n' "$HOME" >"${root}/metadata/home"
  printf '%s\n' "$XDG_CONFIG_HOME_REAL" >"${root}/metadata/xdg-config-home"
  printf '%s\n' "$CODEX_HOME_REAL" >"${root}/metadata/codex-home"
  if command -v lean-ctx >/dev/null 2>&1; then
    lean-ctx --version >"${root}/metadata/leanctx-version" 2>&1 || true
    command -v lean-ctx >"${root}/metadata/leanctx-command" || true
  fi
  if command -v harr >/dev/null 2>&1; then
    command -v harr >"${root}/metadata/harr-command" || true
  fi
  find "${HOME}/.local/libexec/harr/vendor/lean-ctx" -maxdepth 2 -type f -name 'lean-ctx' -print0 2>/dev/null \
    | sort -z \
    | xargs -0 -r sha256sum >"${root}/metadata/leanctx-binaries.sha256"
  {
    printf 'HOME=%s\n' "$HOME"
    printf 'XDG_CONFIG_HOME=%s\n' "$XDG_CONFIG_HOME_REAL"
    printf 'CODEX_HOME=%s\n' "$CODEX_HOME_REAL"
    printf 'checkpoint_script=%s\n' "$SELF"
  } >"${root}/metadata/environment"
}

capture_systemd_files() {
  local root="$1" path key n=0
  [[ -d "$SYSTEMD_USER_ROOT" ]] || return 0
  while IFS= read -r -d '' path; do
    n=$((n + 1))
    key="$(printf 'systemd-%04d' "$n")"
    snapshot_item "$root" "$key" "$path"
  done < <(
    find "$SYSTEMD_USER_ROOT" -maxdepth 2 \
      \( -name 'harr*' -o -lname '*harr*' \) -print0 2>/dev/null | sort -z
  )
}

verify_checkpoint() {
  local root="$1" dir target existed count=0
  [[ -f "${root}/complete" ]] || die "checkpoint is incomplete: $root"
  [[ -d "${root}/items" ]] || die "checkpoint has no items: $root"
  while IFS= read -r -d '' dir; do
    [[ -r "${dir}/target" && -r "${dir}/existed" ]] || die "broken item: $dir"
    target="$(cat "${dir}/target")"
    existed="$(cat "${dir}/existed")"
    [[ "$existed" == 0 || "$existed" == 1 ]] || die "invalid existed flag in $dir"
    if [[ "$existed" == 1 ]]; then
      [[ -e "${dir}/payload" || -L "${dir}/payload" ]] || die "missing payload for $target"
    fi
    count=$((count + 1))
  done < <(find "${root}/items" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
  (( count > 0 )) || die "checkpoint contains no items"
  note "Checkpoint verified: $root"
  note "Items: $count"
  if [[ -r "${root}/metadata/leanctx-version" ]]; then
    printf 'Captured LeanCTX: %s\n' "$(tr '\n' ' ' <"${root}/metadata/leanctx-version")"
  fi
}

create_checkpoint() {
  local label="${1:-before-smoke}" stamp root tmp key target
  label="$(safe_key "$label")"
  stamp="$(date +%Y%m%d-%H%M%S)"
  root="${DEFAULT_ROOT}/${stamp}-${label}"
  tmp="${root}.tmp.$$"
  [[ ! -e "$root" && ! -e "$tmp" ]] || die "checkpoint path already exists: $root"
  mkdir -p "${tmp}/items"
  note "Creating full Harr/LeanCTX smoke checkpoint..."
  while IFS='|' read -r key target; do
    [[ -n "$key" ]] || continue
    note "  snapshot $key"
    snapshot_item "$tmp" "$key" "$target"
  done < <(base_targets)
  capture_systemd_files "$tmp"
  capture_services "$tmp"
  capture_metadata "$tmp"

  cp -a -- "$SELF" "${tmp}/smoke-checkpoint.sh"
  cat >"${tmp}/rollback.sh" <<'ROLLBACK'
#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/smoke-checkpoint.sh" restore "$ROOT"
ROLLBACK
  chmod 700 "${tmp}/rollback.sh" "${tmp}/smoke-checkpoint.sh"
  printf 'ok\n' >"${tmp}/complete"
  mv -- "$tmp" "$root"
  verify_checkpoint "$root"
  note
  note "Rollback command:"
  printf '  %q\n' "${root}/rollback.sh"
}

stop_current_harr_services() {
  systemd_available || return 0
  local unit
  while IFS= read -r unit; do
    [[ -n "$unit" ]] || continue
    systemctl --user stop "$unit" >/dev/null 2>&1 || true
  done < <(systemctl --user list-units 'harr*' --all --type=service --no-legend --plain 2>/dev/null | awk '{print $1}')
}

remove_current_harr_systemd_files() {
  [[ -d "$SYSTEMD_USER_ROOT" ]] || return 0
  local path
  while IFS= read -r -d '' path; do
    rm -rf -- "$path"
  done < <(
    find "$SYSTEMD_USER_ROOT" -maxdepth 2 \
      \( -name 'harr*' -o -lname '*harr*' \) -print0 2>/dev/null
  )
}

restore_services() {
  local root="$1" unit enabled active
  systemd_available || return 0
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  [[ -r "${root}/services.tsv" ]] || return 0
  while IFS=$'\t' read -r unit enabled active; do
    [[ -n "$unit" ]] || continue
    case "$enabled" in
      enabled|enabled-runtime)
        systemctl --user enable "$unit" >/dev/null 2>&1 || true
        ;;
      disabled)
        systemctl --user disable "$unit" >/dev/null 2>&1 || true
        ;;
    esac
  done <"${root}/services.tsv"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  while IFS=$'\t' read -r unit enabled active; do
    [[ "$active" == active ]] || continue
    systemctl --user start "$unit" >/dev/null 2>&1 || true
  done <"${root}/services.tsv"
}

restore_checkpoint() {
  local root="$1" dir target existed parent
  root="$(readlink -f "$root")"
  verify_checkpoint "$root"

  note "Stopping current Harr services..."
  stop_current_harr_services
  remove_current_harr_systemd_files

  note "Restoring checkpoint payload..."
  while IFS= read -r -d '' dir; do
    target="$(cat "${dir}/target")"
    existed="$(cat "${dir}/existed")"
    rm -rf -- "$target"
    if [[ "$existed" == 1 ]]; then
      parent="$(dirname -- "$target")"
      mkdir -p "$parent"
      cp -a -- "${dir}/payload" "$target"
      note "  restored $target"
    else
      note "  removed smoke-created $target"
    fi
  done < <(find "${root}/items" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

  restore_services "$root"

  note
  note "Rollback complete."
  if command -v lean-ctx >/dev/null 2>&1; then
    printf 'LeanCTX now: '
    lean-ctx --version || true
  else
    note "LeanCTX now: missing"
  fi

  if [[ -s "${root}/metadata/leanctx-binaries.sha256" ]]; then
    if sha256sum -c "${root}/metadata/leanctx-binaries.sha256" >/dev/null 2>&1; then
      note "LeanCTX binary checksum: restored exactly"
    else
      die "rollback finished but LeanCTX binary checksum differs from checkpoint"
    fi
  fi
}

usage() {
  cat <<EOF
Usage:
  $0 create [LABEL]
  $0 verify CHECKPOINT
  $0 restore CHECKPOINT

create writes a self-contained checkpoint under:
  $DEFAULT_ROOT

The generated CHECKPOINT/rollback.sh restores the captured pre-smoke state
without depending on the currently installed Harr or LeanCTX.
EOF
}

case "${1:-}" in
  create)
    shift
    create_checkpoint "${1:-before-smoke}"
    ;;
  verify)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    verify_checkpoint "$2"
    ;;
  restore)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    restore_checkpoint "$2"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
