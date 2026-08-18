# Common Harr CLI helpers.

readonly HARR_SYSTEMD_USER_DIR="${HARR_SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user}"
readonly HARR_CONFIG_DIR="${HARR_CONFIG_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/harr}"
readonly HARR_MCP_CONFIG_DIR="${HARR_MCP_CONFIG_DIR:-${HARR_CONFIG_DIR}/mcp}"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

validate_mcp_name() {
  local name="$1"
  [[ "$name" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid MCP name: $name"
}

mcp_unit() {
  local name="$1"
  validate_mcp_name "$name"
  printf 'harr-mcp-%s.service\n' "$name"
}

mcp_unit_path() {
  local name="$1"
  printf '%s/%s\n' "$HARR_SYSTEMD_USER_DIR" "$(mcp_unit "$name")"
}

mcp_exists() {
  [[ -f "$(mcp_unit_path "$1")" ]]
}

managed_mcp_names() {
  local path base name
  shopt -s nullglob
  for path in "${HARR_SYSTEMD_USER_DIR}"/harr-mcp-*.service; do
    base="${path##*/}"
    name="${base#harr-mcp-}"
    name="${name%.service}"
    printf '%s\n' "$name"
  done | sort
  shopt -u nullglob
}

require_mcp() {
  local name="$1"
  mcp_exists "$name" || die "unknown Harr MCP: $name"
}

mcp_env_file() {
  printf '%s/%s.env\n' "$HARR_MCP_CONFIG_DIR" "$1"
}

env_value() {
  local file="$1" key="$2" line
  [[ -r "$file" ]] || return 1
  line="$(grep -m1 -E "^${key}=" "$file" 2>/dev/null || true)"
  [[ -n "$line" ]] || return 1
  printf '%s\n' "${line#*=}"
}

systemctl_user() {
  systemctl --user "$@"
}
