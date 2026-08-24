# macOS MCP lifecycle orchestration via per-user launchd agents.

mcp_targets() {
  local requested="${1:-}"
  [[ -n "$requested" ]] || die 'MCP name is required'
  if [[ "$requested" == all ]]; then managed_mcp_names; return; fi
  require_mcp "$requested"
  printf '%s\n' "$requested"
}

mcp_endpoint() { mcp_server_field "$1" url 2>/dev/null || true; }
mcp_endpoint_state() {
  local endpoint="$1"
  [[ -n "$endpoint" ]] || { printf '%s\n' '-'; return; }
  if command -v curl >/dev/null 2>&1 && curl --silent --show-error --max-time 1 --output /dev/null "$endpoint" 2>/dev/null; then printf '%s\n' reachable; else printf '%s\n' unreachable; fi
}

mcp_service_state() {
  local target state
  target="$(launch_target "$1")"
  if ! state="$(launchctl print "$target" 2>/dev/null)"; then printf '%s\n' unloaded; return; fi
  state="$(printf '%s\n' "$state" | awk '/^[[:space:]]*state = / {print $3; exit}')"
  printf '%s\n' "${state:-loaded}"
}

mcp_startup_state() {
  local label domain disabled
  label="$(mcp_label "$1")"; domain="$(launch_domain)"
  disabled="$(launchctl print-disabled "$domain" 2>/dev/null || true)"
  if printf '%s\n' "$disabled" | grep -Eq '"?'"${label}"'"?[[:space:]]*=>[[:space:]]*true'; then printf '%s\n' disabled; else printf '%s\n' enabled; fi
}

mcp_pid() {
  local output pid
  output="$(launchctl print "$(launch_target "$1")" 2>/dev/null || true)"
  pid="$(printf '%s\n' "$output" | awk '/^[[:space:]]*pid = / {print $3; exit}')"
  printf '%s\n' "${pid:--}"
}

mcp_status_row() {
  local name="$1" endpoint
  endpoint="$(mcp_endpoint "$name")"
  printf '%-16s %-11s %-11s %-8s %-12s %s\n' "$name" "$(mcp_service_state "$name")" "$(mcp_startup_state "$name")" "$(mcp_pid "$name")" "$(mcp_endpoint_state "$endpoint")" "${endpoint:--}"
}

cmd_mcp_status_all() {
  [[ $# -eq 0 ]] || die 'usage: harr mcp status'
  local names name
  names="$(managed_mcp_names)"
  printf '%-16s %-11s %-11s %-8s %-12s %s\n' MCP SERVICE STARTUP PID ENDPOINT URL
  [[ -n "$names" ]] || { printf '%s\n' '(no Harr service MCPs configured)'; return; }
  while IFS= read -r name; do [[ -n "$name" ]] && mcp_status_row "$name"; done <<<"$names"
}

cmd_mcp_status() {
  if [[ $# -eq 0 ]]; then cmd_mcp_status_all; return; fi
  [[ $# -eq 1 ]] || die 'usage: harr mcp status [NAME]'
  require_mcp "$1"
  printf '%-16s %-11s %-11s %-8s %-12s %s\n' MCP SERVICE STARTUP PID ENDPOINT URL
  mcp_status_row "$1"
}

launch_bootstrap() {
  local name="$1" plist target domain
  plist="$(mcp_plist "$name")"; target="$(launch_target "$name")"; domain="$(launch_domain)"
  [[ -r "$plist" ]] || die "Harr LaunchAgent is missing: $plist"
  if ! launchctl print "$target" >/dev/null 2>&1; then launchctl bootstrap "$domain" "$plist"; fi
}

cmd_mcp_lifecycle() {
  local action="$1" target="$2" names name plist service
  names="$(mcp_targets "$target")"
  [[ -n "$names" ]] || die 'no Harr service MCPs configured'
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    plist="$(mcp_plist "$name")"; service="$(launch_target "$name")"
    printf '%s %s...\n' "$action" "$name"
    case "$action" in
      start) launchctl enable "$service" >/dev/null 2>&1 || true; launch_bootstrap "$name"; launchctl kickstart "$service" ;;
      stop) launchctl bootout "$service" >/dev/null 2>&1 || true ;;
      restart) launchctl bootout "$service" >/dev/null 2>&1 || true; launchctl enable "$service" >/dev/null 2>&1 || true; launchctl bootstrap "$(launch_domain)" "$plist" ;;
      enable) launchctl enable "$service" ;;
      disable) launchctl disable "$service"; launchctl bootout "$service" >/dev/null 2>&1 || true ;;
      *) die "unknown MCP lifecycle action: $action" ;;
    esac
  done <<<"$names"
}

write_launch_agent() {
  local name="$1" label plist runner out err
  label="$(mcp_label "$name")"; plist="$(mcp_plist "$name")"; runner="${HOME}/.local/bin/harr-mcp-run"
  out="${HARR_LOG_DIR}/${name}.out.log"; err="${HARR_LOG_DIR}/${name}.err.log"
  install -d -m 0755 "$HARR_LAUNCH_AGENTS_DIR" "$HARR_LOG_DIR"
  python3 - "$plist" "$label" "$runner" "$name" "$out" "$err" <<'PY'
import plistlib, sys
path, label, runner, name, out, err = sys.argv[1:]
data = {"Label": label, "ProgramArguments": [runner, name], "RunAtLoad": True, "KeepAlive": True, "ProcessType": "Background", "StandardOutPath": out, "StandardErrorPath": err}
with open(path, "wb") as f: plistlib.dump(data, f, sort_keys=False)
PY
  chmod 0644 "$plist"
}

reconcile_mcp_services() {
  local name active
  active="$(managed_mcp_names)"
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if printf '%s\n' "$active" | grep -Fxq -- "$name"; then
      write_launch_agent "$name"
    else
      launchctl bootout "$(launch_target "$name")" >/dev/null 2>&1 || true
      rm -f -- "$(mcp_plist "$name")"
    fi
  done < <(catalog_service_mcp_names)
}

cmd_mcp_configure() {
  [[ $# -le 1 ]] || die 'usage: harr mcp configure [none|all|name1,name2]'
  if (($#)); then mcp_select spec "$1" all; else mcp_select configure '' all; fi
  mcp_manager install-configs --config-dir "$HARR_MCP_CONFIG_DIR"
  cmd_install_components mcp
  cmd_leanctx_apply
  reconcile_mcp_services
  cmd_agents_apply all
  printf 'MCP selection applied. Disabled MCP env/secret files were preserved.\n'
}

cmd_mcp_logs() {
  [[ $# -ge 1 && $# -le 2 ]] || die 'usage: harr mcp logs NAME [-f|--follow]'
  local name="$1" follow='' out err
  require_mcp "$name"; shift
  if (($#)); then case "$1" in -f|--follow) follow=-f ;; *) die 'usage: harr mcp logs NAME [-f|--follow]' ;; esac; fi
  out="${HARR_LOG_DIR}/${name}.out.log"; err="${HARR_LOG_DIR}/${name}.err.log"
  touch "$out" "$err"
  tail ${follow:+$follow} -n 100 "$out" "$err"
}

cmd_status() {
  [[ $# -eq 0 ]] || die 'usage: harr status'
  printf '== MCP selection ==\n\n'; mcp_available
  printf '\n== Components ==\n\n'; cmd_components_status
  printf '\n== LeanCTX ==\n\n'; cmd_leanctx_status
  printf '\n== Global hosts ==\n\n'; cmd_hosts_status
  printf '\n== Agent policy / diagnostic skills ==\n\n'; cmd_agents_status
  printf '\n== MCP services ==\n\n'; cmd_mcp_status_all
}

cmd_mcp() {
  local command="${1:-status}"
  shift || true
  case "$command" in
    list) [[ $# -eq 0 ]] || die 'usage: harr mcp list'; all_mcp_names ;;
    available) [[ $# -eq 0 ]] || die 'usage: harr mcp available'; mcp_available ;;
    configure) cmd_mcp_configure "$@" ;;
    start|stop|restart|enable|disable) [[ $# -eq 1 ]] || die "usage: harr mcp $command NAME|all"; cmd_mcp_lifecycle "$command" "$1" ;;
    status) cmd_mcp_status "$@" ;;
    logs) cmd_mcp_logs "$@" ;;
    help|-h|--help) mcp_usage ;;
    *) die "unknown mcp command: $command (see harr mcp help)" ;;
  esac
}
