#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
VERSION=9.9.9
OUT_DIR="$TMP/dist" bash "$ROOT/packaging/build-release.sh" "$VERSION" >/dev/null

DEB="$TMP/dist/harr-codex-scheduler_${VERSION}_all.deb"
TGZ="$TMP/dist/harr-codex-scheduler-${VERSION}-linux.tar.gz"
[[ -f "$DEB" ]]
[[ -f "$TGZ" ]]

dpkg-deb --field "$DEB" Package | grep -qx 'harr-codex-scheduler'
dpkg-deb --field "$DEB" Version | grep -qx "$VERSION"
dpkg-deb --field "$DEB" Architecture | grep -qx 'all'
dpkg-deb --field "$DEB" Depends | grep -q 'python3-pyqt6'
dpkg-deb --field "$DEB" Depends | grep -q 'at'

dpkg-deb -x "$DEB" "$TMP/root"
for path in \
  usr/bin/harr-codex-scheduler \
  usr/bin/codex-schedule \
  usr/bin/sol \
  usr/bin/terra \
  usr/bin/luna \
  usr/lib/harr-codex-scheduler/app/main.py \
  usr/lib/harr-codex-scheduler/app/session_selector.py \
  usr/share/applications/harr-codex-scheduler.desktop; do
  [[ -e "$TMP/root/$path" ]] || { echo "missing package path: $path" >&2; exit 1; }
done

grep -q '^Exec=/usr/bin/harr-codex-scheduler$' "$TMP/root/usr/share/applications/harr-codex-scheduler.desktop"
grep -q '/usr/lib/harr-codex-scheduler/bin/codex-scheduler-ui' "$TMP/root/usr/bin/harr-codex-scheduler"
bash -n "$TMP/root/usr/bin/"{harr-codex-scheduler,codex-schedule,sol,terra,luna}
bash -n "$TMP/root/usr/lib/harr-codex-scheduler/bin/"*
python3 -m py_compile "$TMP/root/usr/lib/harr-codex-scheduler/app/"*.py

tar -tzf "$TGZ" | grep -q "^harr-codex-scheduler-${VERSION}-linux/harr-codex-scheduler$"
tar -tzf "$TGZ" | grep -q "^harr-codex-scheduler-${VERSION}-linux/app/main.py$"
tar -tzf "$TGZ" | grep -q "^harr-codex-scheduler-${VERSION}-linux/bin/terra$"

printf 'packaging tests passed: %s and %s\n' "$(basename "$DEB")" "$(basename "$TGZ")"
