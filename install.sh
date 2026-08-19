#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR

case "$(uname -s)" in
  Linux)
    exec "${ROOT_DIR}/linux/install.sh" "$@"
    ;;
  Darwin)
    exec "${ROOT_DIR}/macos/install.sh" "$@"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    printf 'Error: use PowerShell on Windows: .\\install.ps1 -Clean [-Start]\n' >&2
    exit 1
    ;;
  *)
    printf 'Error: unsupported Harr platform: %s\n' "$(uname -s)" >&2
    exit 1
    ;;
esac
