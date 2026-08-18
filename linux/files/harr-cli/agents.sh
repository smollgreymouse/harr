# Harr-managed agent policy and diagnostic skills.

if [[ -d "${SELF_DIR:-}/files/skills" ]]; then
  readonly HARR_SKILLS_SOURCE_DIR="${SELF_DIR}/files/skills"
  readonly HARR_POLICY_TEMPLATE="${SELF_DIR}/files/policy/tool-routing.template.md"
  readonly HARR_HOSTS_SOURCE_DIR="${SELF_DIR}/files/hosts"
else
  readonly HARR_SKILLS_SOURCE_DIR="${HARR_LIBEXEC_DIR}/skills"
  readonly HARR_POLICY_TEMPLATE="${HARR_LIBEXEC_DIR}/policy/tool-routing.template.md"
  readonly HARR_HOSTS_SOURCE_DIR="${HARR_LIBEXEC_DIR}/hosts"
fi
readonly HARR_SKILL_MARKER='<!-- harr-managed-skill-v1 -->'
readonly HARR_POLICY_START='<!-- harr-tool-policy:start -->'
readonly HARR_POLICY_END='<!-- harr-tool-policy:end -->'

agent_skill_root() {
  case "$1" in
    codex) printf '%s\n' "${CODEX_HOME:-${HOME}/.codex}/skills" ;;
    opencode) printf '%s\n' "${HOME}/.config/opencode/skills" ;;
    *) die "unknown agent: $1" ;;
  esac
}

agent_policy_target() {
  case "$1" in
    codex) printf '%s\n' "${CODEX_HOME:-${HOME}/.codex}/AGENTS.md" ;;
    opencode) printf '%s\n' "${HOME}/.config/opencode/AGENTS.md" ;;
    *) die "unknown agent: $1" ;;
  esac
}

agent_adapter() {
  printf '%s/%s.env\n' "$HARR_HOSTS_SOURCE_DIR" "$1"
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

render_agent_policy() {
  local agent="$1" output="$2" adapter
  adapter="$(agent_adapter "$agent")"
  [[ -r "$HARR_POLICY_TEMPLATE" ]] || die "Harr policy template missing: $HARR_POLICY_TEMPLATE"
  [[ -r "$adapter" ]] || die "Harr host adapter missing: $adapter"

  local CTX_READ='' CTX_SHELL='' CTX_SEARCH='' CTX_GLOB='' CTX_TOOLS='' CTX_CALL=''
  # shellcheck disable=SC1090
  source "$adapter"
  [[ -n "$CTX_READ" && -n "$CTX_SHELL" && -n "$CTX_SEARCH" && -n "$CTX_GLOB" && -n "$CTX_TOOLS" && -n "$CTX_CALL" ]] || \
    die "incomplete Harr host adapter: $adapter"

  sed \
    -e "s|{{CTX_READ}}|${CTX_READ}|g" \
    -e "s|{{CTX_SHELL}}|${CTX_SHELL}|g" \
    -e "s|{{CTX_SEARCH}}|${CTX_SEARCH}|g" \
    -e "s|{{CTX_GLOB}}|${CTX_GLOB}|g" \
    -e "s|{{CTX_TOOLS}}|${CTX_TOOLS}|g" \
    -e "s|{{CTX_CALL}}|${CTX_CALL}|g" \
    "$HARR_POLICY_TEMPLATE" >"$output"
}

extract_policy_block() {
  local file="$1"
  awk -v start="$HARR_POLICY_START" -v end="$HARR_POLICY_END" '
    $0 == start { inside=1 }
    inside { print }
    inside && $0 == end { exit }
  ' "$file"
}

install_agent_policy() {
  local agent="$1" target target_dir backup_dir backup rendered tmp has_start=0 has_end=0
  target="$(agent_policy_target "$agent")"
  target_dir="$(dirname -- "$target")"
  backup_dir="${HARR_LIBEXEC_DIR}/backup/agents"
  backup="${backup_dir}/${agent}.AGENTS.md.pre-harr"
  install -d -m 0755 "$target_dir" "$backup_dir"

  rendered="$(mktemp)"
  tmp="$(mktemp)"
  render_agent_policy "$agent" "$rendered"

  if [[ -e "$target" ]]; then
    grep -qF "$HARR_POLICY_START" "$target" && has_start=1 || true
    grep -qF "$HARR_POLICY_END" "$target" && has_end=1 || true
    ((has_start == has_end)) || die "malformed Harr policy markers in $target"

    if [[ ! -e "$backup" ]]; then
      cp -a "$target" "$backup"
      printf 'Backed up existing %s global AGENTS.md to %s\n' "$agent" "$backup"
    fi

    if ((has_start)); then
      awk -v start="$HARR_POLICY_START" -v end="$HARR_POLICY_END" -v block="$rendered" '
        BEGIN {
          while ((getline line < block) > 0) rendered = rendered line ORS
          close(block)
        }
        $0 == start { printf "%s", rendered; inside=1; next }
        inside && $0 == end { inside=0; next }
        !inside { print }
      ' "$target" >"$tmp"
    else
      cat "$target" >"$tmp"
      [[ ! -s "$target" ]] || printf '\n' >>"$tmp"
      cat "$rendered" >>"$tmp"
    fi
  else
    cat "$rendered" >"$tmp"
  fi

  chmod 0644 "$tmp"
  mv -f "$tmp" "$target"
  rm -f -- "$rendered"
  printf 'Applied compact Harr tool policy for %s: %s\n' "$agent" "$target"
}

policy_state() {
  local agent="$1" target rendered current
  target="$(agent_policy_target "$agent")"
  [[ -r "$target" ]] || { printf 'missing'; return; }
  grep -qF "$HARR_POLICY_START" "$target" || { printf 'missing'; return; }
  grep -qF "$HARR_POLICY_END" "$target" || { printf 'malformed'; return; }

  rendered="$(mktemp)"
  current="$(mktemp)"
  render_agent_policy "$agent" "$rendered"
  extract_policy_block "$target" >"$current"
  if cmp -s "$rendered" "$current"; then
    printf 'managed'
  else
    printf 'stale'
  fi
  rm -f -- "$rendered" "$current"
}

cmd_agents_apply() {
  local requested="${1:-all}"
  [[ $# -le 1 ]] || die 'usage: harr agents apply [all|codex|opencode]'
  local agent skill
  while IFS= read -r agent; do
    install_agent_policy "$agent"
    for skill in lean-ctx harr; do
      install_one_skill "$agent" "$skill"
    done
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
  local agent
  printf '%-12s %-12s %-16s %s\n' AGENT POLICY LEAN-CTX-SKILL HARR-SKILL
  for agent in codex opencode; do
    printf '%-12s %-12s %-16s %s\n' \
      "$agent" \
      "$(policy_state "$agent")" \
      "$(skill_state "$agent" lean-ctx)" \
      "$(skill_state "$agent" harr)"
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
