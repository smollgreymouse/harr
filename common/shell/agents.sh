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
readonly HARR_ASA_CONFIG="${HARR_COMMON_DIR}/agents/asa_config.py"
readonly HARR_POLICY_START='<!-- harr-tool-policy:start -->'
readonly HARR_CLEAN_SNAPSHOT="${HOME}/.local/share/harr/state/pre-harr/complete"

require_clean_ownership() {
  [[ -f "$HARR_CLEAN_SNAPSHOT" ]] || die 'Harr has not taken clean ownership of the global harness; run the repository installer with --clean first'
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

filter_mcp_text() {
  local input="$1" output="$2"
  ensure_mcp_effective
  [[ -r "$HARR_MCP_ASSETS" ]] || die "Harr MCP asset renderer missing: $HARR_MCP_ASSETS"
  python3 "$HARR_MCP_ASSETS" filter-text --catalog "$HARR_MCP_CATALOG" --registry "$HARR_MCP_EFFECTIVE" --input "$input" --output "$output"
}

render_harr_skill() {
  local target_dir="$1"
  ensure_mcp_effective
  python3 "$HARR_MCP_ASSETS" filter-skill --catalog "$HARR_MCP_CATALOG" --registry "$HARR_MCP_EFFECTIVE" --source "$(skill_source_dir harr)" --output "$target_dir"
}

install_one_skill() {
  local agent="$1" skill="$2" root source_dir target_dir
  root="$(agent_skill_root "$agent")"
  source_dir="$(skill_source_dir "$skill")"
  target_dir="${root}/${skill}"
  [[ -r "${source_dir}/SKILL.md" ]] || die "Harr skill source missing: ${source_dir}/SKILL.md"
  install -d -m 0755 "$root"
  if [[ "$skill" == harr ]]; then
    render_harr_skill "$target_dir"
  else
    rm -rf -- "$target_dir"
    install -d -m 0755 "$target_dir"
    cp -a "${source_dir}/." "$target_dir/"
  fi
}

remove_managed_skill() {
  local agent="$1" skill="$2" root target
  root="$(agent_skill_root "$agent")"
  target="${root}/${skill}"
  if [[ -r "${target}/SKILL.md" ]] && grep -qF "$HARR_SKILL_MARKER" "${target}/SKILL.md"; then
    rm -rf -- "$target"
  fi
}

asa_config() {
  [[ -r "$HARR_ASA_CONFIG" ]] || die "Harr Asa config helper missing: $HARR_ASA_CONFIG"
  require_command python3
  env HARR_CONFIG_DIR="$HARR_CONFIG_DIR" CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}" python3 "$HARR_ASA_CONFIG" "$@"
}

orchestration_enabled() {
  if asa_config enabled >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

sync_asa_role() {
  asa_config sync --force
}

cmd_agents_orchestration() {
  local sub="${1:-status}"
  shift || true
  [[ $# -eq 0 ]] || die 'usage: harr agents orchestration {status|enable|disable}'
  case "$sub" in
    status) asa_config status ;;
    enable|disable)
      require_clean_ownership
      asa_config "$sub"
      cmd_agents_apply codex
      cmd_leanctx_apply
      ;;
    *) die 'usage: harr agents orchestration {status|enable|disable}' ;;
  esac
}

cmd_agents_asa() {
  local sub="${1:-status}"
  shift || true
  case "$sub" in
    status) [[ $# -eq 0 ]] || die 'usage: harr agents asa status'; asa_config status ;;
    configure) require_clean_ownership; asa_config configure "$@" --force ;;
    apply) [[ $# -eq 0 ]] || die 'usage: harr agents asa apply'; require_clean_ownership; sync_asa_role ;;
    *) die 'usage: harr agents asa {status|configure|apply}' ;;
  esac
}

render_agent_policy() {
  local agent="$1" output="$2" adapter expanded
  adapter="$(agent_adapter "$agent")"
  [[ -r "$HARR_POLICY_TEMPLATE" ]] || die "Harr policy template missing: $HARR_POLICY_TEMPLATE"
  [[ -r "$adapter" ]] || die "Harr host adapter missing: $adapter"
  local CTX_READ='' CTX_SHELL='' CTX_SEARCH='' CTX_GLOB='' CTX_TOOLS='' CTX_CALL='' HOST_ORCHESTRATION_POLICY='' HOST_NATIVE_POLICY=''
  # shellcheck disable=SC1090
  source "$adapter"
  [[ -n "$CTX_READ" && -n "$CTX_SHELL" && -n "$CTX_SEARCH" && -n "$CTX_GLOB" && -n "$CTX_TOOLS" && -n "$CTX_CALL" && -n "$HOST_NATIVE_POLICY" ]] || die "incomplete Harr host adapter: $adapter"
  if [[ "$agent" != codex ]] || ! orchestration_enabled; then
    HOST_ORCHESTRATION_POLICY=''
  fi
  expanded="$(mktemp)"
  sed \
    -e "s|{{CTX_READ}}|${CTX_READ}|g" \
    -e "s|{{CTX_SHELL}}|${CTX_SHELL}|g" \
    -e "s|{{CTX_SEARCH}}|${CTX_SEARCH}|g" \
    -e "s|{{CTX_GLOB}}|${CTX_GLOB}|g" \
    -e "s|{{CTX_TOOLS}}|${CTX_TOOLS}|g" \
    -e "s|{{CTX_CALL}}|${CTX_CALL}|g" \
    -e "s|{{HOST_ORCHESTRATION_POLICY}}|${HOST_ORCHESTRATION_POLICY}|g" \
    -e "s|{{HOST_NATIVE_POLICY}}|${HOST_NATIVE_POLICY}|g" \
    "$HARR_POLICY_TEMPLATE" >"$expanded"
  filter_mcp_text "$expanded" "$output"
  rm -f -- "$expanded"
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
  local agent skill root
  local einherjar_enabled=0
  if grep -q '"ein_instance"' "$HARR_MCP_EFFECTIVE" 2>/dev/null; then einherjar_enabled=1; fi
  while IFS= read -r agent; do
    install_agent_policy "$agent"
    for skill in lean-ctx harr; do install_one_skill "$agent" "$skill"; done
    root="$(agent_skill_root "$agent")"
    if [[ "${HARR_PLATFORM:-linux}" == linux ]]; then
      install_one_skill "$agent" harr-workspace
    else
      remove_managed_skill "$agent" harr-workspace
    fi
    remove_managed_skill "$agent" gigacode-executor
    remove_managed_skill "$agent" einherjar-worker
    if [[ "$agent" == codex ]] && orchestration_enabled; then
      install_one_skill "$agent" asa
    else
      remove_managed_skill "$agent" asa
    fi
    if [[ "$agent" == codex ]]; then
      sync_asa_role
    fi
    if ((einherjar_enabled)); then
      install_one_skill "$agent" ein
    else
      remove_managed_skill "$agent" ein
    fi
  done < <(agent_targets "$requested")
}

skill_state() {
  local agent="$1" skill="$2" source_dir target_dir target expected
  source_dir="$(skill_source_dir "$skill")"
  target_dir="$(agent_skill_root "$agent")/${skill}"
  target="${target_dir}/SKILL.md"
  if [[ ! -e "$target_dir" ]]; then printf 'missing'; return; fi
  if [[ ! -r "${source_dir}/SKILL.md" ]]; then printf 'source-missing'; return; fi
  if [[ "$skill" == harr ]]; then
    expected="$(mktemp -d)"
    render_harr_skill "$expected"
    if diff -qr "$expected" "$target_dir" >/dev/null 2>&1; then printf 'managed';
    elif [[ -r "$target" ]] && grep -qF "$HARR_SKILL_MARKER" "$target" 2>/dev/null; then printf 'modified';
    else printf 'external'; fi
    rm -rf -- "$expected"
  elif diff -qr "$source_dir" "$target_dir" >/dev/null 2>&1; then printf 'managed';
  elif [[ -r "$target" ]] && grep -qF "$HARR_SKILL_MARKER" "$target" 2>/dev/null; then printf 'modified';
  else printf 'external'; fi
}

cmd_agents_status() {
  [[ $# -eq 0 ]] || die 'usage: harr agents status'
  local agent ownership=missing
  [[ -f "$HARR_CLEAN_SNAPSHOT" ]] && ownership=clean
  printf 'ownership: %s\n' "$ownership"
  printf 'orchestration: %s\n' "$(if orchestration_enabled; then printf enabled; else printf disabled; fi)"
  printf '%-12s %-12s %-14s %-12s %-10s %-10s %s\n' AGENT POLICY LEAN-CTX HARR ASA EIN WORKSPACE
  for agent in codex opencode; do
    local asa_state='n/a'
    [[ "$agent" == codex ]] && asa_state="$(skill_state "$agent" asa)"
    printf '%-12s %-12s %-14s %-12s %-10s %-10s %s\n' "$agent" "$(policy_state "$agent")" "$(skill_state "$agent" lean-ctx)" "$(skill_state "$agent" harr)" "$asa_state" "$(skill_state "$agent" ein)" "$(skill_state "$agent" harr-workspace)"
  done
}

cmd_agents() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    apply) cmd_agents_apply "$@" ;;
    status) cmd_agents_status "$@" ;;
    orchestration) cmd_agents_orchestration "$@" ;;
    asa) cmd_agents_asa "$@" ;;
    help|-h|--help) printf '%s\n' 'Usage:' '  harr agents apply [all|codex|opencode]' '  harr agents status' '  harr agents orchestration {status|enable|disable}' '  harr agents asa status' '  harr agents asa configure [--model MODEL] [--effort EFFORT]' '  harr agents asa apply' ;;
    *) die "unknown agents command: $command (see harr help)" ;;
  esac
}
