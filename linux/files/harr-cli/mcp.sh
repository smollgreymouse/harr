# MCP lifecycle orchestration.

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
mcp_service_state() { systemctl_user is-active "$(mcp_unit "$1")" 2>/dev/null || true; }
mcp_startup_state() { systemctl_user is-enabled "$(mcp_unit "$1")" 2>/dev/null || true; }
mcp_pid() {
  local pid
  pid="$(systemctl_user show "$(mcp_unit "$1")" -p MainPID --value 2>/dev/null || true)"
  [[ "$pid" != 0 && -n "$pid" ]] && printf '%s\n' "$pid" || printf '%s\n' '-'
}

mcp_status_row() {
  local name="$1" endpoint
  endpoint="$(mcp_endpoint "$name")"
  printf '%-16s %-11s %-11s %-8s %-12s %s\n' "$name" "$(mcp_service_state "$name")" "$(mcp_startup_state "$name")" "$(mcp_pid "$name")" "$(mcp_endpoint_state "$endpoint")" "${endpoint:--}"
}

cmd_mcp_status_all() {
  [[ $# -eq 0 ]] || die 'usage: harr mcp status'
  local -a names=()
  mapfile -t names < <(managed_mcp_names)
  printf '%-16s %-11s %-11s %-8s %-12s %s\n' MCP SERVICE STARTUP PID ENDPOINT URL
  if ((${#names[@]} == 0)); then printf '%s\n' '(no Harr service MCPs configured)'; return; fi
  local name
  for name in "${names[@]}"; do mcp_status_row "$name"; done
}

cmd_mcp_status() {
  if [[ $# -eq 0 ]]; then cmd_mcp_status_all; return; fi
  [[ $# -eq 1 ]] || die 'usage: harr mcp status [NAME]'
  require_mcp "$1"
  printf '%-16s %-11s %-11s %-8s %-12s %s\n' MCP SERVICE STARTUP PID ENDPOINT URL
  mcp_status_row "$1"
}

cmd_mcp_lifecycle() {
  local action="$1" target="$2"
  local -a names=()
  mapfile -t names < <(mcp_targets "$target")
  ((${#names[@]} > 0)) || die 'no Harr service MCPs configured'
  local name unit
  for name in "${names[@]}"; do
    unit="$(mcp_unit "$name")"
    printf '%s %s...\n' "$action" "$name"
    systemctl_user "$action" "$unit"
  done
}

reconcile_mcp_services() {
  require_command systemctl
  systemctl_user daemon-reload
  local name
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if managed_mcp_names | grep -Fxq -- "$name"; then
      systemctl_user enable "$(mcp_unit "$name")" >/dev/null
    else
      systemctl_user disable --now "$(mcp_unit "$name")" >/dev/null 2>&1 || true
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
  local name="$1"
  require_mcp "$name"
  shift
  local -a args=(-u "$(mcp_unit "$name")" --no-pager -n 100)
  if (($#)); then case "$1" in -f|--follow) args=(-u "$(mcp_unit "$name")" -f -n 100) ;; *) die 'usage: harr mcp logs NAME [-f|--follow]' ;; esac; fi
  journalctl --user "${args[@]}"
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
