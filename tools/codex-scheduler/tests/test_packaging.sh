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

DEB="$TMP/dist/harr-scheduler_${VERSION}_${ARCH}.deb"
TGZ="$TMP/dist/harr-scheduler-${VERSION}-linux-${ARCH}.tar.gz"
[[ -f "$DEB" ]]
[[ -f "$TGZ" ]]

dpkg-deb --field "$DEB" Package | grep -qx 'harr-scheduler'
dpkg-deb --field "$DEB" Version | grep -qx "$VERSION"
dpkg-deb --field "$DEB" Architecture | grep -qx "$ARCH"
# The 0.3.x package was harr-codex-scheduler; the rename must replace it.
dpkg-deb --field "$DEB" Replaces | grep -qx 'harr-codex-scheduler'
dpkg-deb --field "$DEB" Provides | grep -qx 'harr-codex-scheduler'
DEPS=$(dpkg-deb --field "$DEB" Depends)
grep -q 'at' <<<"$DEPS"
grep -q 'git' <<<"$DEPS"
grep -q 'bash' <<<"$DEPS"
grep -q 'util-linux' <<<"$DEPS"

# Do not pin Qt's Debian package naming here. CPack/dpkg-shlibdeps must derive
# the distro-specific shared-library dependencies from the packaged ELF.
if ! grep -Eq '(^|, )libqt6[^,]*widgets' <<<"$DEPS"; then
  echo "dpkg-shlibdeps did not add a Qt Widgets runtime dependency: $DEPS" >&2
  exit 1
fi

# Verify that apt can resolve the complete dependency set on the build distro
# without changing the machine.
apt-get --simulate install "$DEB" >/dev/null

if grep -qi 'python' <<<"$DEPS"; then
  echo 'native package unexpectedly depends on Python' >&2
  exit 1
fi

dpkg-deb -x "$DEB" "$TMP/root"
dpkg-deb -e "$DEB" "$TMP/control"
for path in \
  usr/bin/harr-scheduler \
  usr/bin/harr-schedule \
  usr/bin/codex-scheduler-ui \
  usr/bin/codex-schedule \
  usr/bin/sol \
  usr/bin/terra \
  usr/bin/luna \
  usr/share/applications/harr-scheduler.desktop; do
  [[ -e "$TMP/root/$path" ]] || { echo "missing package path: $path" >&2; exit 1; }
done

grep -q 'harr-codex-scheduler' "$TMP/control/postinst" || {
  echo 'postinst does not install the legacy binary compatibility symlink' >&2
  exit 1
}

[[ -x "$TMP/root/usr/bin/harr-scheduler" ]]
if ldd "$TMP/root/usr/bin/harr-scheduler" | grep -q 'not found'; then
  echo 'packaged scheduler has unresolved shared-library dependencies' >&2
  ldd "$TMP/root/usr/bin/harr-scheduler" >&2
  exit 1
fi
grep -q '^Exec=/usr/bin/harr-scheduler$' "$TMP/root/usr/share/applications/harr-scheduler.desktop"
bash -n "$TMP/root/usr/bin/"{codex-scheduler-ui,codex-schedule,harr-schedule,sol,terra,luna}

if find "$TMP/root" -type f \( -name '*.py' -o -name '*.pyc' \) | grep -q .; then
  echo 'Python files leaked into native package' >&2
  exit 1
fi

PORTABLE="harr-scheduler-${VERSION}-linux-${ARCH}"
tar -tzf "$TGZ" > "$TMP/tar-list.txt"
grep -qx "$PORTABLE/harr-scheduler" "$TMP/tar-list.txt"
grep -qx "$PORTABLE/bin/codex-schedule" "$TMP/tar-list.txt"
grep -qx "$PORTABLE/bin/terra" "$TMP/tar-list.txt"
if grep -E '\.py(c)?$' "$TMP/tar-list.txt" >/dev/null; then
  echo 'Python files leaked into portable bundle' >&2
  exit 1
fi

printf 'native packaging tests passed: %s and %s\n' "$(basename "$DEB")" "$(basename "$TGZ")"
