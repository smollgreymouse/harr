#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REAL="${LEANCTX_TEST_BIN:?set LEANCTX_TEST_BIN to the multi-root LeanCTX development binary}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home" XDG_CONFIG_HOME="$TMP/config"
export HARR_LEANCTX_REAL="$REAL" HARR_MCP_EFFECTIVE="$ROOT/common/mcp/registry.json"
mkdir -p "$HOME" "$TMP/repo" "$TMP/extra" "$TMP/extra2"
git -C "$TMP/repo" init -q
git -C "$TMP/repo" config user.email workspace@example.invalid
git -C "$TMP/repo" config user.name "Workspace Test"
printf 'primary\n' >"$TMP/repo/tracked.txt"
git -C "$TMP/repo" add tracked.txt
git -C "$TMP/repo" commit -qm initial
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
rm -rf "$TMP/extra"
"$ROOT/linux/harr" workspace show >"$TMP/show-stale.json"
"$ROOT/linux/harr" workspace list >"$TMP/list-stale.json"

mkdir -p "$TMP/independent"
git -C "$TMP/independent" init -q
git -C "$TMP/independent" config user.email workspace@example.invalid
git -C "$TMP/independent" config user.name "Workspace Test"
printf 'independent\n' >"$TMP/independent/tracked.txt"
git -C "$TMP/independent" add tracked.txt
git -C "$TMP/independent" commit -qm initial
"$ROOT/linux/harr" workspace sync "$TMP/independent" >"$TMP/sync-with-stale.json"

"$ROOT/linux/harr" workspace remove "$TMP/extra" --expected-revision 5 >"$TMP/remove-stale.json"
mkdir -p "$TMP/extra"
"$ROOT/linux/harr" workspace add "$TMP/extra" --expected-revision 6 >"$TMP/add.json"
"$ROOT/linux/harr" workspace show >"$TMP/show2.json"
"$ROOT/linux/harr" workspace list >"$TMP/list.json"
"$ROOT/linux/harr" workspace remove "$TMP/extra" --expected-revision 7 >"$TMP/remove-extra.json"
"$ROOT/linux/harr" workspace remove "$TMP/independent" --expected-revision 8 >"$TMP/remove-independent.json"

python3 - "$TMP" <<'PY2'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
s1=json.loads((p/'show1.json').read_text())
sync=json.loads((p/'sync.json').read_text())
stale_show=json.loads((p/'show-stale.json').read_text())
stale_list=json.loads((p/'list-stale.json').read_text())
sync_stale=json.loads((p/'sync-with-stale.json').read_text())
remove_stale=json.loads((p/'remove-stale.json').read_text())
add=json.loads((p/'add.json').read_text())
s2=json.loads((p/'show2.json').read_text())
ls=json.loads((p/'list.json').read_text())
remove_extra=json.loads((p/'remove-extra.json').read_text())
remove_independent=json.loads((p/'remove-independent.json').read_text())

assert s1['revision']==1 and s1['additional']==[]
assert sync['revision']==3 and sync['sync']['added']==[str(p/'extra'),str(p/'extra2')]
reasons={(x['path'],x['reason']) for x in sync['sync']['skipped']}
assert (str((p/'repo').resolve()),'primary') in reasons
assert (str((p/'extra').resolve()),'duplicate-input') in reasons

warning=stale_show['warnings'][0]
assert warning['code']=='workspace-root-missing'
assert warning['path']==str(p/'extra')
assert warning['state']=='missing'
assert warning['remove_command']==f"harr workspace remove {p/'extra'}"
row=next(item for item in stale_list if item.get('primary')==str((p/'repo').resolve()))
assert row['warnings']==stale_show['warnings']

assert sync_stale['revision']==5
assert sync_stale['sync']['added']==[str((p/'independent').resolve())]
assert str(p/'extra') in sync_stale['additional']
assert str((p/'independent').resolve()) in sync_stale['additional']
assert sync_stale['warnings'][0]['code']=='workspace-root-missing'

assert remove_stale['revision']==6 and str(p/'extra') not in remove_stale['additional']
assert 'warnings' not in remove_stale
assert add['revision']==7 and str(p/'extra') in add['additional']
assert s2['revision']==7 and set(s2['additional'])=={str(p/'extra'),str((p/'independent').resolve())}
assert 'warnings' not in s2
row=next(item for item in ls if item.get('primary')==str((p/'repo').resolve()))
assert 'warnings' not in row
assert remove_extra['revision']==8 and str(p/'extra') not in remove_extra['additional']
assert remove_independent['revision']==9 and remove_independent['additional']==[]
print('PASS: stale Workspace roots warn with cleanup command and do not block independent Git additions')
PY2


mkdir -p "$TMP/gitrepo"
git -C "$TMP/gitrepo" init -q
git -C "$TMP/gitrepo" config user.email workspace@example.invalid
git -C "$TMP/gitrepo" config user.name "Workspace Test"
printf 'main
' >"$TMP/gitrepo/tracked.txt"
git -C "$TMP/gitrepo" add tracked.txt
git -C "$TMP/gitrepo" commit -qm initial
git -C "$TMP/gitrepo" branch feature-worktree
git -C "$TMP/gitrepo" worktree add -q "$TMP/git-linked" feature-worktree
cd "$TMP/gitrepo"
"$ROOT/linux/harr" workspace show >"$TMP/git-show.json"
"$ROOT/linux/harr" workspace sync "$TMP/git-linked" >"$TMP/git-sync.json"
python3 - "$TMP" <<'PY3'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
show=json.loads((p/'git-show.json').read_text())
sync=json.loads((p/'git-sync.json').read_text())
assert show['revision']==1 and show['additional']==[]
assert sync['revision']==1 and sync['additional']==[]
assert sync['sync']['added']==[]
assert sync['sync']['skipped']==[{
    'path':str((p/'git-linked').resolve()),
    'reason':'same-repository-worktree',
}]
print('PASS: sibling Git worktree is topology, not additional Workspace authority')
PY3


git -C "$TMP/gitrepo" branch feature-primary
git -C "$TMP/gitrepo" worktree add -q "$TMP/primary-old" feature-primary
cd "$TMP/primary-old"
"$ROOT/linux/harr" workspace show >"$TMP/primary-before-move.json"
git -C "$TMP/gitrepo" worktree move "$TMP/primary-old" "$TMP/primary-new"
cd "$TMP/primary-new"
"$ROOT/linux/harr" workspace show >"$TMP/primary-after-move.json"
python3 - "$TMP" <<'PY4'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
before=json.loads((p/'primary-before-move.json').read_text())
after=json.loads((p/'primary-after-move.json').read_text())
assert before['workspaceId'] if 'workspaceId' in before else before['id']
assert before['id']==after['id']
assert before['store']==after['store']
assert before['primary']==str((p/'primary-old').resolve(strict=False))
assert after['primary']==before['primary']
assert after['activePrimary']==str((p/'primary-new').resolve())
assert after['primaryStatus']=='moved'
print('PASS: Harr reuses the same Workspace store after git worktree move')
PY4


git -C "$TMP/gitrepo" worktree remove "$TMP/primary-new"
git -C "$TMP/gitrepo" worktree add -q "$TMP/primary-old" feature-primary
cd "$TMP/primary-old"
set +e
"$ROOT/linux/harr" workspace show >"$TMP/recreated-primary.out" 2>"$TMP/recreated-primary.err"
recreated_rc=$?
set -e
[[ $recreated_rc -ne 0 ]]
grep -qi 'primary mismatch' "$TMP/recreated-primary.err"
echo 'PASS: recreated worktree at the old primary path does not inherit old Workspace authority'
