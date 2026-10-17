#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REAL="${LEANCTX_TEST_BIN:?set LEANCTX_TEST_BIN to the multi-root LeanCTX development binary}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home" XDG_CONFIG_HOME="$TMP/config"
export HARR_LEANCTX_REAL="$REAL" HARR_MCP_EFFECTIVE="$ROOT/common/mcp/registry.json"
mkdir -p "$HOME" "$TMP/repo/.git" "$TMP/extra"
cd "$TMP/repo"
"$ROOT/linux/harr" workspace show >"$TMP/show1.json"
"$ROOT/linux/harr" workspace add "$TMP/extra" >"$TMP/add.json"
"$ROOT/linux/harr" workspace show >"$TMP/show2.json"
"$ROOT/linux/harr" workspace list >"$TMP/list.json"
"$ROOT/linux/harr" workspace remove "$TMP/extra" >"$TMP/remove.json"
python3 - "$TMP" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); s1=json.loads((p/'show1.json').read_text()); add=json.loads((p/'add.json').read_text()); s2=json.loads((p/'show2.json').read_text()); ls=json.loads((p/'list.json').read_text()); rem=json.loads((p/'remove.json').read_text())
assert s1['revision']==1 and s1['additional']==[]
assert add['revision']==2 and str(p/'extra') in add['additional']
assert s2['revision']==2 and str(p/'extra') in s2['additional']
assert len(ls)==1 and ls[0]['primary']==str((p/'repo').resolve())
assert rem['revision']==3 and rem['additional']==[]
print('PASS: harr workspace show/list/add/remove')
PY
