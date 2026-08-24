# Harr Kubernetes helpers. Kubernetes operations use the real kubectl with a Harr-managed portable kubeconfig.

harr_state_snapshot_for_kube() {
  local helper="${HARR_STATE_HELPER:-${HARR_LIBEXEC_DIR}/state/harr-state}"
  if [[ -x "$helper" ]]; then
    "$helper" snapshot >/dev/null
    return
  fi
  if [[ -n "${SELF_DIR:-}" && -x "${SELF_DIR}/files/state/harr-state" ]]; then
    "${SELF_DIR}/files/state/harr-state" snapshot >/dev/null
    return
  fi
  die 'Harr state helper is unavailable; refusing to change managed Kubernetes state without rollback ownership'
}

harr_kube_bridge() {
  require_command python3
  local bridge="${HARR_COMMON_DIR}/kubernetes/kubectl.py"
  [[ -r "$bridge" ]] || die "Harr Kubernetes bridge missing: $bridge"
  python3 "$bridge" "$@"
}

cmd_kube() {
  local sub="${1:-status}"
  shift || true
  case "$sub" in
    configure|sync)
      harr_state_snapshot_for_kube
      harr_kube_bridge "$sub" "$@"
      ;;
    status)
      harr_kube_bridge status "$@"
      ;;
    *) die 'usage: harr kube {configure [--source PATHLIST] [--kubectl PATH] [--allow-exec] [--no-check]|sync [--allow-exec] [--no-check]|status [--no-check]}' ;;
  esac
}

cmd_kubectl() {
  harr_kube_bridge run -- "$@"
}
