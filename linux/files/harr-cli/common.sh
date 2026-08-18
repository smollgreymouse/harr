# Common Harr CLI helpers.

readonly HARR_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
readonly HARR_CONFIG_DIR="${HARR_CONFIG_DIR:-${HARR_CONFIG_HOME}/harr}"
readonly HARR_MCP_CONFIG_DIR="${HARR_MCP_CONFIG_DIR:-${HARR_CONFIG_DIR}/mcp}"
readonly HARR_SECRETS_DIR="${HARR_SECRETS_DIR:-${HARR_CONFIG_DIR}/secrets}"
readonly HARR_RUNTIME_ENV="${HARR_RUNTIME_ENV:-${HARR_CONFIG_DIR}/runtime.env}"
readonly HARR_SYSTEMD_USER_DIR="${HARR_SYSTEMD_USER_DIR:-${HARR_CONFIG_HOME}/systemd/user}"
readonly HARR_LIBEXEC_DIR="${HARR_LIBEXEC_DIR:-${HOME}/.local/libexec/harr}"
readonly HARR_VENDOR_DIR="${HARR_VENDOR_DIR:-${HARR_LIBEXEC_DIR}/vendor}"
readonly HARR_NPM_PREFIX="${HARR_NPM_PREFIX:-${HOME}/.local/share/harr/npm}"
readonly HARR_NPM_BIN_DIR="${HARR_NPM_BIN_DIR:-${HARR_NPM_PREFIX}/node_modules/.bin}"
readonly HARR_LEANCTX_CONFIG_DIR="${LEAN_CTX_CONFIG_DIR:-${HARR_CONFIG_HOME}/lean-ctx}"
readonly HARR_LEANCTX_CONFIG="${HARR_LEANCTX_CONFIG_DIR}/config.toml"
readonly HARR_GITLAB_SECRET_FILE="${HARR_SECRETS_DIR}/gitlab-pat"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'Warning: %s\n' "$*" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

ensure_private_dir() {
  install -d -m 0700 "$1"
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

package_version() {
  local package_json="$1"
  [[ -r "$package_json" ]] || return 1
  sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$package_json" | head -1
}
