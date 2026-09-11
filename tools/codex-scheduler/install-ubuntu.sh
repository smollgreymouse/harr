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
Runtime packages on Ubuntu 24.04+:
  sudo apt install at python3-pyqt6 qt6-gtk-platformtheme
  sudo systemctl enable --now atd

qt6-gtk-platformtheme lets standard Qt widgets and native dialogs follow the
GNOME/GTK desktop theme. The app still has a palette fallback if the platform
theme is unavailable.
MSG
