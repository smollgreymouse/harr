#!/usr/bin/env bash
set -Eeuo pipefail

HARR_BIN="${HOME}/.local/bin/harr"
if [[ ! -x "$HARR_BIN" ]]; then
  printf 'Error: installed Harr CLI not found: %s\n' "$HARR_BIN" >&2
  exit 1
fi
exec "$HARR_BIN" uninstall
