#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
for name in sol terra luna codex-schedule codex-scheduler-ui; do
  ln -sfn "$ROOT/bin/$name" "$HOME/.local/bin/$name"
done
sed "s|@EXEC@|$HOME/.local/bin/codex-scheduler-ui|g" "$ROOT/desktop/harr-codex-scheduler.desktop.in" > "$HOME/.local/share/applications/harr-codex-scheduler.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
cat <<'MSG'
Installed launchers in ~/.local/bin and desktop entry in ~/.local/share/applications.
Required runtime packages on Ubuntu 24.04+:
  sudo apt install at python3-pyqt6
  sudo systemctl enable --now atd

On Ubuntu releases that provide it (including 25.10), qgnomeplatform-qt6 is an
optional GNOME/Adwaita integration improvement:
  sudo apt install qgnomeplatform-qt6

It is not required for dark mode. The app normalizes all dark palette surface
roles itself, so editors, trees, dropdowns and dialogs cannot remain white in
a half-dark Qt palette.
MSG
