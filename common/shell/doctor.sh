# Harr doctor dispatcher.

cmd_doctor() {
  require_command python3
  local doctor="${HARR_COMMON_DIR}/doctor.py"
  [[ -r "$doctor" ]] || die "Harr doctor implementation missing: $doctor"
  env \
    HARR_PLATFORM="${HARR_PLATFORM:-linux}" \
    HARR_VERSION="${HARR_VERSION:-}" \
    HARR_LEANCTX_VERSION="${HARR_LEANCTX_VERSION:-}" \
    HARR_LEANCTX_BUILD="${HARR_LEANCTX_BUILD:-}" \
    HARR_LEANCTX_ID="${HARR_LEANCTX_ID:-}" \
    HARR_LIBEXEC_DIR="${HARR_LIBEXEC_DIR}" \
    HARR_COMMON_DIR="${HARR_COMMON_DIR}" \
    python3 "$doctor" "$@"
}
