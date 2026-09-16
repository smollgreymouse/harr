#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
VERSION=$(tr -d '[:space:]' < "$ROOT/VERSION")

if [[ ! -r /etc/os-release ]]; then
  echo 'install-ubuntu: /etc/os-release not found; use the portable tar.gz bundle instead' >&2
  exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *)
    if [[ " ${ID_LIKE:-} " != *" debian "* ]]; then
      echo "install-ubuntu: unsupported distro '${ID:-unknown}'; use the portable tar.gz bundle instead" >&2
      exit 2
    fi
    ;;
esac

for tool in apt-get dpkg; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "install-ubuntu: required tool not found: $tool" >&2
    exit 127
  }
done

printf 'Installing C++ build dependencies...\n'
sudo apt-get update
sudo apt-get install -y cmake qt6-base-dev at git

ARCH=$(dpkg --print-architecture)
DEB="$ROOT/dist/harr-codex-scheduler_${VERSION}_${ARCH}.deb"
BUILD="$ROOT/build"
cmake -S "$ROOT" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSCHEDULER_VERSION="$VERSION" \
  -DSCHEDULER_PACKAGE_OUTPUT_DIR="$ROOT/dist"
cmake --build "$BUILD" --target package-release

printf '\nInstalling %s with apt...\n' "$DEB"
sudo apt-get install -y "$DEB"

cat <<EOF

Harr Codex Scheduler $VERSION is installed as a native Qt/C++ application.

GUI/tray:
  harr-codex-scheduler
  or open "Harr Codex Scheduler" from the application menu.

CLI selectors:
  sol   HH:MM SESSION_ID "prompt"
  terra HH:MM SESSION_ID "prompt"
  luna  HH:MM SESSION_ID "prompt"

The OpenAI Codex CLI must be installed separately and available as 'codex'.

Uninstall application files:
  sudo apt remove harr-codex-scheduler

User task history is intentionally kept under:
  \${XDG_STATE_HOME:-\$HOME/.local/state}/harr-codex-scheduler

Remove that directory manually only if you also want to erase task history/logs.
EOF
