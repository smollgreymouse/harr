#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REAL="${LEANCTX_TEST_BIN:?set LEANCTX_TEST_BIN to the multi-root LeanCTX development binary}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home" XDG_CONFIG_HOME="$TMP/config"
export HARR_LEANCTX_REAL="$REAL" HARR_MCP_EFFECTIVE="$ROOT/common/mcp/registry.json"
mkdir -p "$HOME" "$TMP/repo/.git" "$TMP/extra" "$TMP/extra2"
cd "$TMP/repo"
"$ROOT/linux/harr" workspace show >"$TMP/show1.json"
"$ROOT/linux/harr" workspace sync "$TMP/repo" "$TMP/extra" "$TMP/extra" "$TMP/extra2" >"$TMP/sync.json"
set +e
"$ROOT/linux/harr" workspace remove "$TMP/extra" --expected-revision 1 >"$TMP/stale.out" 2>"$TMP/stale.err"
stale_rc=$?
set -e
[[ $stale_rc -ne 0 ]]
grep -qi 'revision' "$TMP/stale.err"
"$ROOT/linux/harr" workspace remove "$TMP/extra2" --expected-revision 3 >"$TMP/remove-extra2.json"
"$ROOT/linux/harr" workspace remove "$TMP/extra" --expected-revision 4 >"$TMP/remove-extra.json"
"$ROOT/linux/harr" workspace add "$TMP/extra" --expected-revision 5 >"$TMP/add.json"
"$ROOT/linux/harr" workspace show >"$TMP/show2.json"
"$ROOT/linux/harr" workspace list >"$TMP/list.json"
"$ROOT/linux/harr" workspace remove "$TMP/extra" --expected-revision 6 >"$TMP/remove.json"
python3 - "$TMP" <<'PY2'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); s1=json.loads((p/'show1.json').read_text()); sync=json.loads((p/'sync.json').read_text()); add=json.loads((p/'add.json').read_text()); s2=json.loads((p/'show2.json').read_text()); ls=json.loads((p/'list.json').read_text()); rem=json.loads((p/'remove.json').read_text())
assert s1['revision']==1 and s1['additional']==[]
assert sync['revision']==3 and sync['sync']['added']==[str(p/'extra'),str(p/'extra2')]
reasons={(x['path'],x['reason']) for x in sync['sync']['skipped']}
assert (str((p/'repo').resolve()),'primary') in reasons
assert (str((p/'extra').resolve()),'duplicate-input') in reasons
assert add['revision']==6 and str(p/'extra') in add['additional']
assert s2['revision']==6 and str(p/'extra') in s2['additional']
assert len(ls)==1 and ls[0]['primary']==str((p/'repo').resolve())
assert rem['revision']==7 and rem['additional']==[]
print('PASS: harr workspace sync/show/list/add/remove with CAS conflict')
PY2
