#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
VERSION=9.9.9
ARCH=$(dpkg --print-architecture)
BUILD="$TMP/build"
cmake -S "$ROOT" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSCHEDULER_VERSION="$VERSION" \
  -DSCHEDULER_PACKAGE_OUTPUT_DIR="$TMP/dist" >/dev/null
cmake --build "$BUILD" --target package-release >/dev/null

DEB="$TMP/dist/harr-codex-scheduler_${VERSION}_${ARCH}.deb"
TGZ="$TMP/dist/harr-codex-scheduler-${VERSION}-linux-${ARCH}.tar.gz"
[[ -f "$DEB" ]]
[[ -f "$TGZ" ]]

dpkg-deb --field "$DEB" Package | grep -qx 'harr-codex-scheduler'
dpkg-deb --field "$DEB" Version | grep -qx "$VERSION"
dpkg-deb --field "$DEB" Architecture | grep -qx "$ARCH"
dpkg-deb --field "$DEB" Depends | grep -q 'libqt6widgets6t64'
dpkg-deb --field "$DEB" Depends | grep -q 'at'
if dpkg-deb --field "$DEB" Depends | grep -qi 'python'; then
  echo 'native package unexpectedly depends on Python' >&2
  exit 1
fi

dpkg-deb -x "$DEB" "$TMP/root"
for path in \
  usr/bin/harr-codex-scheduler \
  usr/bin/codex-scheduler-ui \
  usr/bin/codex-schedule \
  usr/bin/sol \
  usr/bin/terra \
  usr/bin/luna \
  usr/share/applications/harr-codex-scheduler.desktop; do
  [[ -e "$TMP/root/$path" ]] || { echo "missing package path: $path" >&2; exit 1; }
done

[[ -x "$TMP/root/usr/bin/harr-codex-scheduler" ]]
grep -q '^Exec=/usr/bin/harr-codex-scheduler$' "$TMP/root/usr/share/applications/harr-codex-scheduler.desktop"
bash -n "$TMP/root/usr/bin/"{codex-scheduler-ui,codex-schedule,sol,terra,luna}

if find "$TMP/root" -type f \( -name '*.py' -o -name '*.pyc' \) | grep -q .; then
  echo 'Python files leaked into native package' >&2
  exit 1
fi

PORTABLE="harr-codex-scheduler-${VERSION}-linux-${ARCH}"
tar -tzf "$TGZ" > "$TMP/tar-list.txt"
grep -qx "$PORTABLE/harr-codex-scheduler" "$TMP/tar-list.txt"
grep -qx "$PORTABLE/bin/codex-schedule" "$TMP/tar-list.txt"
grep -qx "$PORTABLE/bin/terra" "$TMP/tar-list.txt"
if grep -E '\.py(c)?$' "$TMP/tar-list.txt" >/dev/null; then
  echo 'Python files leaked into portable bundle' >&2
  exit 1
fi

printf 'native packaging tests passed: %s and %s\n' "$(basename "$DEB")" "$(basename "$TGZ")"
