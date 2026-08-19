# Harr-owned global agent policy and diagnostic skills.

if [[ -d "${SELF_DIR:-}/../common/skills" ]]; then
  readonly HARR_SKILLS_SOURCE_DIR="${SELF_DIR}/../common/skills"
  readonly HARR_POLICY_TEMPLATE="${SELF_DIR}/../common/policy/tool-routing.template.md"
  readonly HARR_HOSTS_SOURCE_DIR="${SELF_DIR}/../common/hosts"
else
  readonly HARR_SKILLS_SOURCE_DIR="${HARR_COMMON_DIR}/skills"
  readonly HARR_POLICY_TEMPLATE="${HARR_COMMON_DIR}/policy/tool-routing.template.md"
  readonly HARR_HOSTS_SOURCE_DIR="${HARR_COMMON_DIR}/hosts"
fi
readonly HARR_SKILL_MARKER='<!-- harr-managed-skill-v1 -->'
readonly HARR_POLICY_START='<!-- harr-tool-policy:start -->'
readonly HARR_CLEAN_SNAPSHOT="${HOME}/.local/share/harr/state/pre-harr/complete"

require_clean_ownership() {
  [[ -f "$HARR_CLEAN_SNAPSHOT" ]] || \
    die 'Harr has not taken clean ownership of the global harness; run the repository installer with --clean first'
}

agent_skill_root() {
  case "$1" in
    codex) printf '%s\n' "${CODEX_HOME:-${HOME}/.codex}/skills" ;;
    opencode) printf '%s\n' "${XDG_CONFIG_HOME:-${HOME}/.config}/opencode/skills" ;;
    *) die "unknown agent: $1" ;;
  esac
}

agent_policy_target() {
  case "$1" in
    codex) printf '%s\n' "${CODEX_HOME:-${HOME}/.codex}/AGENTS.md" ;;
    opencode) printf '%s\n' "${XDG_CONFIG_HOME:-${HOME}/.config}/opencode/AGENTS.md" ;;
    *) die "unknown agent: $1" ;;
  esac
}

agent_adapter() { printf '%s/%s.env\n' "$HARR_HOSTS_SOURCE_DIR" "$1"; }
agent_targets() {
  local requested="${1:-all}"
  case "$requested" in
    all) printf '%s\n' codex opencode ;;
    codex|opencode) printf '%s\n' "$requested" ;;
    *) die 'usage: harr agents apply [all|codex|opencode]' ;;
  esac
}
skill_source_dir() { printf '%s/%s\n' "$HARR_SKILLS_SOURCE_DIR" "$1"; }

install_one_skill() {
  local agent="$1" skill="$2" root source_dir target_dir
  root="$(agent_skill_root "$agent")"
  source_dir="$(skill_source_dir "$skill")"
  target_dir="${root}/${skill}"
  [[ -r "${source_dir}/SKILL.md" ]] || die "Harr skill source missing: ${source_dir}/SKILL.md"
  install -d -m 0755 "$root"
  rm -rf -- "$target_dir"
  install -d -m 0755 "$target_dir"
  cp -a "${source_dir}/." "$target_dir/"
}

render_agent_policy() {
  local agent="$1" output="$2" adapter
  adapter="$(agent_adapter "$agent")"
  [[ -r "$HARR_POLICY_TEMPLATE" ]] || die "Harr policy template missing: $HARR_POLICY_TEMPLATE"
  [[ -r "$adapter" ]] || die "Harr host adapter missing: $adapter"
  local CTX_READ='' CTX_SHELL='' CTX_SEARCH='' CTX_GLOB='' CTX_TOOLS='' CTX_CALL='' HOST_NATIVE_POLICY=''
  # shellcheck disable=SC1090
  source "$adapter"
  [[ -n "$CTX_READ" && -n "$CTX_SHELL" && -n "$CTX_SEARCH" && -n "$CTX_GLOB" && -n "$CTX_TOOLS" && -n "$CTX_CALL" && -n "$HOST_NATIVE_POLICY" ]] || die "incomplete Harr host adapter: $adapter"
  sed \
    -e "s|{{CTX_READ}}|${CTX_READ}|g" \
    -e "s|{{CTX_SHELL}}|${CTX_SHELL}|g" \
    -e "s|{{CTX_SEARCH}}|${CTX_SEARCH}|g" \
    -e "s|{{CTX_GLOB}}|${CTX_GLOB}|g" \
    -e "s|{{CTX_TOOLS}}|${CTX_TOOLS}|g" \
    -e "s|{{CTX_CALL}}|${CTX_CALL}|g" \
    -e "s|{{HOST_NATIVE_POLICY}}|${HOST_NATIVE_POLICY}|g" \
    "$HARR_POLICY_TEMPLATE" >"$output"
}

install_agent_policy() {
  local agent="$1" target rendered
  target="$(agent_policy_target "$agent")"
  install -d -m 0755 "$(dirname -- "$target")"
  rendered="$(mktemp)"
  render_agent_policy "$agent" "$rendered"
  install -m 0644 "$rendered" "$target"
  rm -f -- "$rendered"
  printf 'Applied Harr-owned global policy for %s: %s\n' "$agent" "$target"
}

policy_state() {
  local agent="$1" target rendered
  target="$(agent_policy_target "$agent")"
  [[ -r "$target" ]] || { printf 'missing'; return; }
  rendered="$(mktemp)"
  render_agent_policy "$agent" "$rendered"
  if cmp -s "$rendered" "$target"; then printf 'managed';
  elif grep -qF "$HARR_POLICY_START" "$target" 2>/dev/null; then printf 'modified';
  else printf 'external'; fi
  rm -f -- "$rendered"
}

cmd_agents_apply() {
  require_clean_ownership
  local requested="${1:-all}"
  [[ $# -le 1 ]] || die 'usage: harr agents apply [all|codex|opencode]'
  local agent skill
  while IFS= read -r agent; do
    install_agent_policy "$agent"
    for skill in lean-ctx harr; do install_one_skill "$agent" "$skill"; done
  done < <(agent_targets "$requested")
}

skill_state() {
  local agent="$1" skill="$2" source_dir target_dir target
  source_dir="$(skill_source_dir "$skill")"
  target_dir="$(agent_skill_root "$agent")/${skill}"
  target="${target_dir}/SKILL.md"
  if [[ ! -e "$target_dir" ]]; then printf 'missing';
  elif [[ ! -r "${source_dir}/SKILL.md" ]]; then printf 'source-missing';
  elif diff -qr "$source_dir" "$target_dir" >/dev/null 2>&1; then printf 'managed';
  elif [[ -r "$target" ]] && grep -qF "$HARR_SKILL_MARKER" "$target" 2>/dev/null; then printf 'modified';
  else printf 'external'; fi
}

cmd_agents_status() {
  [[ $# -eq 0 ]] || die 'usage: harr agents status'
  local agent ownership=missing
  [[ -f "$HARR_CLEAN_SNAPSHOT" ]] && ownership=clean
  printf 'ownership: %s\n' "$ownership"
  printf '%-12s %-12s %-16s %s\n' AGENT POLICY LEAN-CTX-SKILL HARR-SKILL
  for agent in codex opencode; do
    printf '%-12s %-12s %-16s %s\n' "$agent" "$(policy_state "$agent")" "$(skill_state "$agent" lean-ctx)" "$(skill_state "$agent" harr)"
  done
}

cmd_agents() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    apply) cmd_agents_apply "$@" ;;
    status) cmd_agents_status "$@" ;;
    help|-h|--help) printf '%s\n' 'Usage:' '  harr agents apply [all|codex|opencode]' '  harr agents status' ;;
    *) die "unknown agents command: $command (see harr help)" ;;
  esac
}
