# Harr-managed agent skills.

if [[ -d "${SELF_DIR:-}/files/skills" ]]; then
  readonly HARR_SKILLS_SOURCE_DIR="${SELF_DIR}/files/skills"
else
  readonly HARR_SKILLS_SOURCE_DIR="${HARR_LIBEXEC_DIR}/skills"
fi
readonly HARR_SKILL_MARKER='<!-- harr-managed-skill-v1 -->'

agent_skill_root() {
  case "$1" in
    codex) printf '%s\n' "${HOME}/.codex/skills" ;;
    opencode) printf '%s\n' "${HOME}/.config/opencode/skills" ;;
    *) die "unknown agent: $1" ;;
  esac
}

agent_targets() {
  local requested="${1:-all}"
  case "$requested" in
    all) printf '%s\n' codex opencode ;;
    codex|opencode) printf '%s\n' "$requested" ;;
    *) die 'usage: harr agents apply [all|codex|opencode]' ;;
  esac
}

skill_source_dir() {
  printf '%s/%s\n' "$HARR_SKILLS_SOURCE_DIR" "$1"
}

install_one_skill() {
  local agent="$1" skill="$2" root source_dir source target_dir target backup_dir backup
  root="$(agent_skill_root "$agent")"
  source_dir="$(skill_source_dir "$skill")"
  source="${source_dir}/SKILL.md"
  target_dir="${root}/${skill}"
  target="${target_dir}/SKILL.md"
  backup_dir="${HARR_LIBEXEC_DIR}/backup/skills/${agent}"
  backup="${backup_dir}/${skill}.pre-harr"

  [[ -r "$source" ]] || die "Harr skill source missing: $source"
  install -d -m 0755 "$root" "$backup_dir"

  if [[ -e "$target_dir" ]] && { [[ ! -r "$target" ]] || ! grep -qF "$HARR_SKILL_MARKER" "$target" 2>/dev/null; }; then
    if [[ ! -e "$backup" ]]; then
      cp -a "$target_dir" "$backup"
      printf 'Backed up existing %s/%s skill to %s\n' "$agent" "$skill" "$backup"
    fi
  fi

  rm -rf -- "$target_dir"
  install -d -m 0755 "$target_dir"
  cp -a "${source_dir}/." "$target_dir/"
}

cmd_agents_apply() {
  local requested="${1:-all}"
  [[ $# -le 1 ]] || die 'usage: harr agents apply [all|codex|opencode]'
  local agent skill
  while IFS= read -r agent; do
    for skill in lean-ctx harr; do
      install_one_skill "$agent" "$skill"
    done
    printf 'Applied Harr-managed skills for %s.\n' "$agent"
  done < <(agent_targets "$requested")
}

skill_state() {
  local agent="$1" skill="$2" source_dir source target_dir target
  source_dir="$(skill_source_dir "$skill")"
  source="${source_dir}/SKILL.md"
  target_dir="$(agent_skill_root "$agent")/${skill}"
  target="${target_dir}/SKILL.md"

  if [[ ! -e "$target_dir" ]]; then
    printf 'missing'
  elif [[ ! -r "$source" ]]; then
    printf 'source-missing'
  elif diff -qr "$source_dir" "$target_dir" >/dev/null 2>&1; then
    printf 'managed'
  elif [[ -r "$target" ]] && grep -qF "$HARR_SKILL_MARKER" "$target" 2>/dev/null; then
    printf 'stale'
  else
    printf 'external'
  fi
}

cmd_agents_status() {
  [[ $# -eq 0 ]] || die 'usage: harr agents status'
  local agent skill
  printf '%-12s %-12s %s\n' AGENT SKILL STATE
  for agent in codex opencode; do
    for skill in lean-ctx harr; do
      printf '%-12s %-12s %s\n' "$agent" "$skill" "$(skill_state "$agent" "$skill")"
    done
  done
}

cmd_agents() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    apply) cmd_agents_apply "$@" ;;
    status) cmd_agents_status "$@" ;;
    help|-h|--help)
      printf '%s\n' 'Usage:' \
        '  harr agents apply [all|codex|opencode]' \
        '  harr agents status'
      ;;
    *) die "unknown agents command: $command (see harr help)" ;;
  esac
}
