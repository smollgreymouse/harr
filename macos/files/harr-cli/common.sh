# macOS Harr CLI helpers.

readonly HARR_PLATFORM="macos"
readonly HARR_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
readonly HARR_CONFIG_DIR="${HARR_CONFIG_DIR:-${HARR_CONFIG_HOME}/harr}"
readonly HARR_MCP_CONFIG_DIR="${HARR_MCP_CONFIG_DIR:-${HARR_CONFIG_DIR}/mcp}"
readonly HARR_SECRETS_DIR="${HARR_SECRETS_DIR:-${HARR_CONFIG_DIR}/secrets}"
readonly HARR_RUNTIME_ENV="${HARR_RUNTIME_ENV:-${HARR_CONFIG_DIR}/runtime.env}"
readonly HARR_LIBEXEC_DIR="${HARR_LIBEXEC_DIR:-${HOME}/.local/libexec/harr}"
readonly HARR_COMMON_DIR="${HARR_COMMON_DIR:-${HARR_LIBEXEC_DIR}/common}"
readonly HARR_MCP_MANAGER="${HARR_MCP_MANAGER:-${HARR_COMMON_DIR}/mcp/manager.py}"
readonly HARR_VENDOR_DIR="${HARR_VENDOR_DIR:-${HARR_LIBEXEC_DIR}/vendor}"
readonly HARR_NPM_PREFIX="${HARR_NPM_PREFIX:-${HOME}/.local/share/harr/npm}"
readonly HARR_NPM_BIN_DIR="${HARR_NPM_BIN_DIR:-${HARR_NPM_PREFIX}/node_modules/.bin}"
readonly HARR_LEANCTX_CONFIG_DIR="${LEAN_CTX_CONFIG_DIR:-${HARR_CONFIG_HOME}/lean-ctx}"
readonly HARR_LEANCTX_CONFIG="${HARR_LEANCTX_CONFIG_DIR}/config.toml"
readonly HARR_LAUNCH_AGENTS_DIR="${HARR_LAUNCH_AGENTS_DIR:-${HOME}/Library/LaunchAgents}"
readonly HARR_LOG_DIR="${HARR_LOG_DIR:-${HOME}/Library/Logs/Harr}"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }
ensure_private_dir() { install -d -m 0700 "$1"; }
require_mcp_manager() { [[ -r "$HARR_MCP_MANAGER" ]] || die "Harr MCP manager missing: $HARR_MCP_MANAGER"; require_command python3; }
validate_mcp_name() { [[ "$1" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid MCP name: $1"; }
managed_mcp_names() { mcp_manager names --lifecycle service; }
all_mcp_names() { mcp_manager names; }
catalog_service_mcp_names() { mcp_catalog_manager names --lifecycle service; }
mcp_exists() { managed_mcp_names | grep -Fxq -- "$1"; }
require_mcp() { mcp_exists "$1" || die "unknown or non-service enabled Harr MCP: $1"; }
mcp_env_file() { printf '%s/%s.env\n' "$HARR_MCP_CONFIG_DIR" "$1"; }
mcp_server_field() { mcp_manager server-field "$1" "$2"; }

env_value() {
  local file="$1" key="$2" line
  [[ -r "$file" ]] || return 1
  line="$(grep -m1 -E "^${key}=" "$file" 2>/dev/null || true)"
  [[ -n "$line" ]] || return 1
  printf '%s\n' "${line#*=}"
}

mcp_label() { validate_mcp_name "$1"; printf 'com.harr.mcp.%s\n' "$1"; }
mcp_plist() { printf '%s/%s.plist\n' "$HARR_LAUNCH_AGENTS_DIR" "$(mcp_label "$1")"; }
launch_domain() { printf 'gui/%s\n' "$(id -u)"; }
launch_target() { printf '%s/%s\n' "$(launch_domain)" "$(mcp_label "$1")"; }
