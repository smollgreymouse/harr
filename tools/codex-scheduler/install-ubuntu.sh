#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
VERSION=$(tr -d '[:space:]' < "$ROOT/VERSION")
DEB="$ROOT/dist/harr-codex-scheduler_${VERSION}_all.deb"

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

for tool in dpkg-deb apt-get; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "install-ubuntu: required tool not found: $tool" >&2
    exit 127
  }
done

"$ROOT/packaging/build-release.sh" "$VERSION"

printf '\nInstalling %s with apt...\n' "$DEB"
sudo apt-get install -y "$DEB"

cat <<EOF

Harr Codex Scheduler $VERSION is installed.

GUI:
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
EOF
