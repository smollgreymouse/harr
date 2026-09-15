#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
VERSION=${1:-$(tr -d '[:space:]' < "$ROOT/VERSION")}
OUT_DIR=${OUT_DIR:-"$ROOT/dist"}
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+~-][A-Za-z0-9.+~-]+)?$ ]]; then
  echo "build-release: invalid version: $VERSION" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/harr-codex-scheduler_${VERSION}_all.deb" \
      "$OUT_DIR/harr-codex-scheduler-${VERSION}-linux.tar.gz"

APP_FILES=(
  core.py
  datetime_picker.py
  job_runner.py
  main.py
  session_cwd.py
  session_selector.py
  system_theme.py
  task_page_native.py
  task_store.py
  tray_workflow.py
  ui_chrome.py
  workspace.py
)
BIN_FILES=(codex-schedule codex-scheduler-ui sol terra luna)

copy_runtime_tree() {
  local dest=$1
  install -d "$dest/app" "$dest/bin" "$dest/desktop"
  local file
  for file in "${APP_FILES[@]}"; do
    install -m 0644 "$ROOT/app/$file" "$dest/app/$file"
  done
  for file in "${BIN_FILES[@]}"; do
    install -m 0755 "$ROOT/bin/$file" "$dest/bin/$file"
  done
  install -m 0644 "$ROOT/desktop/harr-codex-scheduler.desktop.in" "$dest/desktop/harr-codex-scheduler.desktop.in"
  install -m 0644 "$ROOT/README.md" "$dest/README.md"
  install -m 0644 "$ROOT/VERSION" "$dest/VERSION"
}

# ---------------------------------------------------------------------------
# Debian package
# ---------------------------------------------------------------------------
PKG="$WORK_DIR/deb"
LIB="$PKG/usr/lib/harr-codex-scheduler"
install -d "$PKG/DEBIAN" "$LIB" "$PKG/usr/bin" "$PKG/usr/share/applications" \
           "$PKG/usr/share/doc/harr-codex-scheduler"
copy_runtime_tree "$LIB"

cat > "$PKG/DEBIAN/control" <<EOF
Package: harr-codex-scheduler
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-pyqt6, at, git, bash
Maintainer: Harr Codex Scheduler contributors
Description: Desktop scheduler for existing OpenAI Codex CLI sessions
 Schedule Codex CLI turns through at(1), choose model/reasoning/speed,
 inspect persisted task history, and view task output in a Qt desktop UI.
 The OpenAI Codex CLI itself must be installed separately.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now atd.service >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$PKG/DEBIAN/postinst"

make_wrapper() {
  local name=$1 target=$2
  cat > "$PKG/usr/bin/$name" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec /usr/lib/harr-codex-scheduler/$target "\$@"
EOF
  chmod 0755 "$PKG/usr/bin/$name"
}

make_wrapper harr-codex-scheduler bin/codex-scheduler-ui
make_wrapper codex-scheduler-ui bin/codex-scheduler-ui
make_wrapper codex-schedule bin/codex-schedule
make_wrapper sol bin/sol
make_wrapper terra bin/terra
make_wrapper luna bin/luna

sed 's|@EXEC@|/usr/bin/harr-codex-scheduler|g' \
  "$ROOT/desktop/harr-codex-scheduler.desktop.in" \
  > "$PKG/usr/share/applications/harr-codex-scheduler.desktop"
install -m 0644 "$ROOT/README.md" "$PKG/usr/share/doc/harr-codex-scheduler/README.md"

dpkg-deb --root-owner-group --build "$PKG" "$OUT_DIR/harr-codex-scheduler_${VERSION}_all.deb" >/dev/null

# ---------------------------------------------------------------------------
# Portable source bundle. Runtime dependencies stay on the host intentionally:
# this preserves the distro Qt/GNOME integration instead of shipping another Qt.
# ---------------------------------------------------------------------------
PORTABLE_NAME="harr-codex-scheduler-$VERSION-linux"
PORTABLE="$WORK_DIR/$PORTABLE_NAME"
copy_runtime_tree "$PORTABLE"

cat > "$PORTABLE/harr-codex-scheduler" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
exec "$ROOT/bin/codex-scheduler-ui" "$@"
EOF
chmod 0755 "$PORTABLE/harr-codex-scheduler"

cat > "$PORTABLE/INSTALL.txt" <<'EOF'
Harr Codex Scheduler portable bundle

Host requirements on Ubuntu/Debian:
  sudo apt install at git python3 python3-pyqt6
  sudo systemctl enable --now atd

OpenAI Codex CLI must also be installed and available as `codex` in PATH.

Run without installing:
  ./harr-codex-scheduler

CLI selectors are available as:
  ./bin/sol
  ./bin/terra
  ./bin/luna
EOF

tar -C "$WORK_DIR" -czf "$OUT_DIR/$PORTABLE_NAME.tar.gz" "$PORTABLE_NAME"

printf 'Built:\n  %s\n  %s\n' \
  "$OUT_DIR/harr-codex-scheduler_${VERSION}_all.deb" \
  "$OUT_DIR/$PORTABLE_NAME.tar.gz"
