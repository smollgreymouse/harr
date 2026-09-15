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

for tool in cmake ninja dpkg-deb; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "build-release: required build tool not found: $tool" >&2
    exit 127
  }
done

ARCH=${ARCH:-$(dpkg --print-architecture 2>/dev/null || uname -m)}
case "$ARCH" in
  x86_64) ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
esac

BUILD="$WORK_DIR/build"
cmake -S "$ROOT" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$BUILD" >/dev/null
BINARY="$BUILD/harr-codex-scheduler"
[[ -x "$BINARY" ]] || { echo 'build-release: scheduler binary was not produced' >&2; exit 1; }

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/harr-codex-scheduler_${VERSION}_"*.deb \
      "$OUT_DIR/harr-codex-scheduler-${VERSION}-linux-${ARCH}.tar.gz"

BIN_FILES=(codex-schedule codex-scheduler-ui sol terra luna)

# ---------------------------------------------------------------------------
# Debian package: one native Qt/C++ executable plus thin shell entrypoints.
# Python/PyQt are intentionally not runtime dependencies.
# ---------------------------------------------------------------------------
PKG="$WORK_DIR/deb"
install -d "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/applications" \
           "$PKG/usr/share/doc/harr-codex-scheduler"
install -m 0755 "$BINARY" "$PKG/usr/bin/harr-codex-scheduler"
for file in "${BIN_FILES[@]}"; do
  install -m 0755 "$ROOT/bin/$file" "$PKG/usr/bin/$file"
done

sed 's|@EXEC@|/usr/bin/harr-codex-scheduler|g' \
  "$ROOT/desktop/harr-codex-scheduler.desktop.in" \
  > "$PKG/usr/share/applications/harr-codex-scheduler.desktop"
install -m 0644 "$ROOT/README.md" "$PKG/usr/share/doc/harr-codex-scheduler/README.md"

cat > "$PKG/DEBIAN/control" <<EOF
Package: harr-codex-scheduler
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: at, git, bash, util-linux, libqt6core6t64, libqt6gui6t64, libqt6widgets6t64
Recommends: qt6-gtk-platformtheme
Maintainer: Harr Codex Scheduler contributors
Description: Native Qt scheduler for existing OpenAI Codex CLI sessions
 Schedule Codex CLI turns through at(1), manage multiple persisted tasks,
 use the tray-first quick scheduler, and inspect captured Codex JSONL output.
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

DEB="$OUT_DIR/harr-codex-scheduler_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$PKG" "$DEB" >/dev/null

# ---------------------------------------------------------------------------
# Portable bundle.  It is portable across compatible Ubuntu/Debian hosts but
# deliberately uses the host Qt libraries so GNOME/Wayland integration stays
# native instead of bundling a second Qt stack.
# ---------------------------------------------------------------------------
PORTABLE_NAME="harr-codex-scheduler-${VERSION}-linux-${ARCH}"
PORTABLE="$WORK_DIR/$PORTABLE_NAME"
install -d "$PORTABLE/bin"
install -m 0755 "$BINARY" "$PORTABLE/harr-codex-scheduler"
for file in "${BIN_FILES[@]}"; do
  install -m 0755 "$ROOT/bin/$file" "$PORTABLE/bin/$file"
done
install -m 0644 "$ROOT/README.md" "$PORTABLE/README.md"
install -m 0644 "$ROOT/VERSION" "$PORTABLE/VERSION"

cat > "$PORTABLE/INSTALL.txt" <<'EOF'
Harr Codex Scheduler portable C++ bundle

Runtime requirements on Ubuntu/Debian:
  sudo apt install at git libqt6core6t64 libqt6gui6t64 libqt6widgets6t64
  sudo systemctl enable --now atd

Optional GNOME integration:
  sudo apt install qt6-gtk-platformtheme

OpenAI Codex CLI must be installed and available as `codex` in PATH.

Run without installing:
  ./harr-codex-scheduler

CLI selectors:
  ./bin/sol
  ./bin/terra
  ./bin/luna
EOF

TGZ="$OUT_DIR/$PORTABLE_NAME.tar.gz"
tar -C "$WORK_DIR" -czf "$TGZ" "$PORTABLE_NAME"

printf 'Built:\n  %s\n  %s\n' "$DEB" "$TGZ"
