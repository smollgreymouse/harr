#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REAL="${LEANCTX_TEST_BIN:?set LEANCTX_TEST_BIN to the multi-root LeanCTX binary}"
CODEX_BIN="${CODEX_TEST_BIN:-$(command -v codex)}"
CODEX_MODEL="${CODEX_TEST_MODEL:-gpt-6-luna}"
TMP="$(mktemp -d -p /tmp harr-codex-workspace-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
FIX_HOME="$TMP/home"; FIX_CONFIG="$TMP/config"; REPO="$TMP/repo-a"; EXTRA="$TMP/repo-b"
mkdir -p "$FIX_HOME" "$FIX_CONFIG" "$REPO/.git" "$EXTRA/.git"
printf 'harr_codex_live_marker_4815162342\n' > "$EXTRA/unique-b.txt"
cat > "$TMP/leanctx-wrapper" <<EOF_WRAP
#!/usr/bin/env bash
set -Eeuo pipefail
export HOME=${FIX_HOME@Q}
export XDG_CONFIG_HOME=${FIX_CONFIG@Q}
export HARR_CONFIG_DIR=${FIX_CONFIG@Q}/harr
export HARR_LEANCTX_REAL=${REAL@Q}
export HARR_MCP_EFFECTIVE=${ROOT@Q}/common/mcp/registry.json
export LEAN_CTX_HEADLESS=1
exec python3 ${ROOT@Q}/common/mcp/manager.py --registry ${ROOT@Q}/common/mcp/registry.json exec-leanctx ${REAL@Q} -- mcp
EOF_WRAP
chmod 0700 "$TMP/leanctx-wrapper"
ADD_CMD="HOME=${FIX_HOME@Q} XDG_CONFIG_HOME=${FIX_CONFIG@Q} HARR_CONFIG_DIR=${FIX_CONFIG@Q}/harr HARR_LEANCTX_REAL=${REAL@Q} HARR_MCP_EFFECTIVE=${ROOT@Q}/common/mcp/registry.json ${ROOT@Q}/linux/harr workspace add ${EXTRA@Q}"
REMOVE_CMD="HOME=${FIX_HOME@Q} XDG_CONFIG_HOME=${FIX_CONFIG@Q} HARR_CONFIG_DIR=${FIX_CONFIG@Q}/harr HARR_LEANCTX_REAL=${REAL@Q} HARR_MCP_EFFECTIVE=${ROOT@Q}/common/mcp/registry.json ${ROOT@Q}/linux/harr workspace remove ${EXTRA@Q}"
PROMPT=$(cat <<EOF_PROMPT
This is a live multi-root acceptance test. Do not inspect repo-b with shell, cat, grep, Python, native file reads, or any tool except the lean-ctx MCP ctx_search tool.
Perform these operations in this single Codex session, in order:
1. Use lean-ctx ctx_search for query "harr_codex_live_marker_4815162342" with path "$EXTRA". Confirm access is denied.
2. Run this native shell command exactly:
$ADD_CMD
3. Without restarting or reconnecting MCP, use lean-ctx ctx_search again with the same query/path. Confirm it succeeds and the result contains harr_codex_live_marker_4815162342.
4. Run this native shell command exactly:
$REMOVE_CMD
5. Without restarting or reconnecting MCP, use lean-ctx ctx_search a third time with the same query/path. Confirm access is denied again.
If and only if every check passes, final response must contain exactly WORKSPACE_CODEX_ACCEPTANCE_PASS. Otherwise final response must start WORKSPACE_CODEX_ACCEPTANCE_FAIL and explain the failed step. Do not modify source files.
EOF_PROMPT
)
set +e
"$CODEX_BIN" --no-daemon -a never exec --ephemeral --json --skip-git-repo-check -C "$REPO" \
  -s workspace-write --add-dir "$FIX_CONFIG" -m "$CODEX_MODEL" \
  -c "mcp_servers.lean-ctx.command=\"$TMP/leanctx-wrapper\"" \
  -c 'mcp_servers.lean-ctx.enabled=true' \
  "$PROMPT" >"$TMP/events.jsonl" 2>"$TMP/codex.stderr"
status=$?
set -e
if [[ $status -ne 0 ]]; then
  if grep -Fq "hit your usage limit" "$TMP/events.jsonl"; then
    echo 'BLOCKED: Codex account usage limit prevented the real acceptance session from starting' >&2
    exit 77
  fi
  echo "Codex exec failed: $status" >&2
  echo '--- Codex stderr ---' >&2
  tail -80 "$TMP/codex.stderr" >&2 || true
  echo '--- Codex JSONL tail ---' >&2
  tail -80 "$TMP/events.jsonl" >&2 || true
  exit "$status"
fi
python3 - "$TMP/events.jsonl" "$FIX_CONFIG/harr/workspaces" <<'PY'
import json,sys
from pathlib import Path
lines=Path(sys.argv[1]).read_text(errors='replace').splitlines(); objs=[]
for line in lines:
    try: objs.append(json.loads(line))
    except json.JSONDecodeError: pass
text='\n'.join(json.dumps(o,ensure_ascii=False) for o in objs)
assert 'WORKSPACE_CODEX_ACCEPTANCE_PASS' in text, text[-10000:]
assert text.count('ctx_search') >= 3, 'expected three ctx_search calls in Codex trace'
assert 'workspace add' in text and 'workspace remove' in text, 'expected Harr add/remove shell calls in Codex trace'
stores=list(Path(sys.argv[2]).glob('*.json'))
assert len(stores)==1,stores
state=json.loads(stores[0].read_text())
assert state['revision']==3,state
assert state['additional']==[],state
print('PASS: real Codex one-session deny -> add -> allow -> remove -> deny acceptance')
PY
