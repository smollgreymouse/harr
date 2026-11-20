#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
BIN=${HARR_SCHEDULER_BIN:-"$ROOT/build/harr-scheduler"}
[[ -x "$BIN" ]] || { echo "test_cli: binary not found: $BIN" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/work" "$TMP/state/tasks" "$TMP/state/jobs"
git init -q "$TMP/work"
: > "$TMP/tty"

cat > "$TMP/bin/at" <<EOF_AT
#!/bin/sh
printf '%s\n' "\$@" > '$TMP/at.args'
cat > '$TMP/at.job'
echo 'job 42 at future test time' >&2
EOF_AT
chmod +x "$TMP/bin/at"

cat > "$TMP/bin/codex" <<'EOF_CODEX'
#!/bin/sh
set -eu
if [ "${1:-}" = app-server ]; then
  while IFS= read -r line; do
    case "$line" in
      *'"method":"initialize"'*)
        printf '%s\n' '{"id":0,"result":{"userAgent":"fake","codexHome":"/tmp","platformFamily":"unix","platformOs":"linux"}}'
        ;;
      *'"method":"initialized"'*)
        ;;
      *'"method":"thread/read"'*)
        sid=$(printf '%s' "$line" | sed -n 's/.*"threadId":"\([^"]*\)".*/\1/p')
        printf '{"id":1,"result":{"thread":{"id":"%s","cwd":"%s","name":"Named %s","preview":"Preview %s","archived":false,"status":{"type":"notLoaded"}}}}\n' "$sid" "$FAKE_CODEX_CWD" "$sid" "$sid"
        ;;
      *'"method":"thread/list"'*)
        printf '{"id":1,"result":{"data":[{"id":"active-session","cwd":"%s","name":"Active session","preview":"active","archived":false,"updatedAt":300},{"id":"archived-session","cwd":"%s","name":"Archived session","preview":"archive","archived":true,"updatedAt":200}],"nextCursor":null}}\n' "$FAKE_CODEX_CWD" "$FAKE_CODEX_CWD"
        ;;
    esac
  done
  exit 0
fi

: > "$FAKE_CODEX_ARGS"
for arg in "$@"; do printf '%s\n' "$arg" >> "$FAKE_CODEX_ARGS"; done
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"fake final answer"}}'
printf '%s\n' '{"type":"turn.completed"}'
EOF_CODEX
chmod +x "$TMP/bin/codex"

mkdir -p "$TMP/login-bin"
cat > "$TMP/login-bin/path-probe-tool" <<'EOF_PROBE_TOOL'
#!/bin/sh
exit 0
EOF_PROBE_TOOL
chmod +x "$TMP/login-bin/path-probe-tool"

cat > "$TMP/bin/fake-login-shell" <<'EOF_LOGIN_SHELL'
#!/bin/sh
if [ "$1" = "-l" ] && [ "$2" = "-i" ] && [ "$3" = "-c" ]; then
  printf 'LOGIN_BANNER=ignored\nPATH=%s\n' "$FAKE_LOGIN_PATH"
  exit 0
fi
exit 2
EOF_LOGIN_SHELL
chmod +x "$TMP/bin/fake-login-shell"

cat > "$TMP/bin/path-probe" <<'EOF_PATH_PROBE'
#!/bin/sh
command -v path-probe-tool > "$FAKE_PATH_RESULT"
EOF_PATH_PROBE
chmod +x "$TMP/bin/path-probe"

FAKE_LOGIN_PATH="$TMP/login-bin:/usr/bin:/bin" FAKE_PATH_RESULT="$TMP/path.result" \
  PATH="/usr/bin:/bin" SHELL="$TMP/bin/fake-login-shell" \
  "$BIN" job-runner --log "$TMP/path-probe.log" -- "$TMP/bin/path-probe"
grep -Fxq "$TMP/login-bin/path-probe-tool" "$TMP/path.result"

# atd omits SHELL from the job environment. The runner must still recover
# the account login shell's PATH instead of silently using /bin/sh.
LOGIN_SHELL=$(getent passwd "$(id -u)" | cut -d: -f7)
LOGIN_SHELL=${LOGIN_SHELL:-/bin/sh}
if [[ "$LOGIN_SHELL" = */bash ]]; then
  env -u SHELL PATH="/usr/bin:/bin" \
    "$BIN" job-runner --log "$TMP/no-shell-env.log" -- /usr/bin/env
  expected_path=$(env -u SHELL PATH="/usr/bin:/bin" "$LOGIN_SHELL" -l -i -c env 2>/dev/null | grep '^PATH=' | tail -n1)
  actual_path=$(grep '^PATH=' "$TMP/no-shell-env.log" | tail -n1)
  [[ -n "$expected_path" && "$actual_path" = "$expected_path" ]] || {
    echo 'runner did not restore login-shell PATH without SHELL (atd case)' >&2
    exit 1
  }
fi

export AT_BIN="$TMP/bin/at" CODEX_BIN="$TMP/bin/codex" TTY_PATH="$TMP/tty"
export FAKE_CODEX_CWD="$TMP/work" FAKE_CODEX_ARGS="$TMP/codex.args"
export HARR_SCHEDULER_BIN="$BIN"

run_wrapper() {
  local selector=$1 expected_model=$2
  : > "$TMP/at.job"
  "$ROOT/bin/$selector" '02:05' 'session-123' "Prompt with spaces and 'quotes'"
  grep -Fq "cd '$TMP/work'" "$TMP/at.job"
  grep -Fq "$expected_model" "$TMP/at.job"
  grep -Fq 'service_tier="default"' "$TMP/at.job"
  grep -Fq 'model_reasoning_effort="high"' "$TMP/at.job"
  grep -Fq 'session-123' "$TMP/at.job"
  grep -Fq 'Prompt with spaces' "$TMP/at.job"
  sh "$TMP/at.job" >/dev/null
  grep -Fxq "$expected_model" "$TMP/codex.args"
  grep -Fxq 'service_tier="default"' "$TMP/codex.args"
  grep -Fxq 'model_reasoning_effort="high"' "$TMP/codex.args"
  grep -Fxq 'resume' "$TMP/codex.args"
  grep -Fxq 'session-123' "$TMP/codex.args"
}

run_wrapper sol gpt-5.6-sol
run_wrapper terra gpt-5.6-terra
run_wrapper luna gpt-5.6-luna

FUTURE_TS=$(date -d '+1 day' +%Y%m%d%H%M)
"$ROOT/bin/codex-schedule" --model gpt-5.6-sol --reasoning medium --speed fast \
  --timestamp "$FUTURE_TS" --session s --prompt p --cwd "$TMP/work" --output "$TMP/out.log"
grep -Fxq -- '-t' "$TMP/at.args"
grep -Fxq -- "$FUTURE_TS" "$TMP/at.args"
grep -Fq "cd '$TMP/work'" "$TMP/at.job"
grep -Fq 'service_tier="fast"' "$TMP/at.job"
grep -Fq 'model_reasoning_effort="medium"' "$TMP/at.job"

TASK="$TMP/state/tasks/gui-task.json"
cat > "$TASK" <<EOF_TASK
{"id":"gui-task","status":"scheduled","cancel_requested":false,"log":"$TMP/state/jobs/gui-task.jsonl"}
EOF_TASK
"$ROOT/bin/codex-schedule" --model gpt-5.6-terra --reasoning high --speed standard \
  --timestamp "$FUTURE_TS" --session gui-session --prompt 'GUI task' --cwd "$TMP/work" \
  --log-json "$TMP/state/jobs/gui-task.jsonl" --save-answer "$TMP/answer.md" --task-state "$TASK"
grep -Fq -- 'job-runner' "$TMP/at.job"
grep -Fq -- '--task-state' "$TMP/at.job"
grep -Fq "$TASK" "$TMP/at.job"
sh "$TMP/at.job" >/dev/null
grep -Eq '"status"[[:space:]]*:[[:space:]]*"completed"' "$TASK"
grep -Eq '"pid"[[:space:]]*:[[:space:]]*null' "$TASK"
grep -Fq 'fake final answer' "$TMP/state/jobs/gui-task.jsonl"
grep -Fxq 'fake final answer' "$TMP/answer.md"

LIST=$($BIN session-list --codex-bin "$TMP/bin/codex")
grep -Fq 'active-session' <<<"$LIST"
if grep -Fq 'archived-session' <<<"$LIST"; then
  echo 'archived session leaked through session-list' >&2
  exit 1
fi

CWD=$($BIN session-cwd --session active-session --codex-bin "$TMP/bin/codex")
[[ "$CWD" == "$TMP/work" ]]

assert_rejected_before_at() {
  local name=$1; shift
  rm -f "$TMP/at.args" "$TMP/at.job"
  if "$ROOT/bin/codex-schedule" "$@" >"$TMP/$name.out" 2>&1; then
    echo "expected $name to fail" >&2
    exit 1
  fi
  [[ ! -e "$TMP/at.args" ]] || { echo "$name reached at unexpectedly" >&2; exit 1; }
}

COMMON=(--model gpt-5.6-sol --reasoning high --speed standard --session s --prompt p --cwd "$TMP/work" --output "$TMP/out.log")
assert_rejected_before_at bad_shape "${COMMON[@]}" --timestamp 20260911123
assert_rejected_before_at bad_calendar "${COMMON[@]}" --timestamp 202602300205
PAST_TS=$(date -d '-1 day' +%Y%m%d%H%M)
assert_rejected_before_at past_time "${COMMON[@]}" --timestamp "$PAST_TS"
assert_rejected_before_at bad_clock "${COMMON[@]}" --at 25:99
assert_rejected_before_at task_state_without_json --model gpt-5.6-sol --reasoning high --speed standard \
  --session s --prompt p --cwd "$TMP/work" --timestamp "$FUTURE_TS" --task-state "$TASK" --output "$TMP/out.log"

grep -Fq 'expected CCYYMMDDhhmm' "$TMP/bad_shape.out"
grep -Fq 'invalid calendar date/time' "$TMP/bad_calendar.out"
grep -Fq 'must be in the future' "$TMP/past_time.out"
grep -Fq 'invalid HH:MM' "$TMP/bad_clock.out"
grep -Fq 'requires --log-json' "$TMP/task_state_without_json.out"

mkdir -p "$TMP/wrong"
git init -q "$TMP/wrong"
if "$ROOT/bin/codex-schedule" --model gpt-5.6-sol --reasoning high --speed standard \
  --at 02:05 --session s --prompt p --cwd "$TMP/wrong" --output "$TMP/out.log" >"$TMP/mismatch.out" 2>&1; then
  echo 'expected cwd mismatch to fail' >&2
  exit 1
fi
grep -Fq -- '--cwd mismatch' "$TMP/mismatch.out"

# --- ZCode agent (public CLI contract only) --------------------------------
mkdir -p "$TMP/zwork"
git init -q "$TMP/zwork"

# Fake zcode CLI: emits NDJSON on --json and honours the documented
# standalone flags. It must never be called with app-server.
cat > "$TMP/bin/zcode" <<'EOF_ZCODE'
#!/bin/sh
set -eu
for arg in "$@"; do
  [ "$arg" != "app-server" ] || { echo 'zcode: app-server is not part of the public CLI' >&2; exit 2; }
done
prompt=''; resume=''; mode=''; cwd=''
while [ $# -gt 0 ]; do
  case "$1" in
    --prompt) prompt=$2; shift 2;;
    --resume) resume=$2; shift 2;;
    --mode) mode=$2; shift 2;;
    --cwd) cwd=$2; shift 2;;
    --json) shift;;
    *) shift;;
  esac
done
[ -n "$prompt" ] || { echo 'zcode: --prompt is required' >&2; exit 2; }
[ -n "$cwd" ] || { echo 'zcode: --cwd is required' >&2; exit 2; }
[ -n "$mode" ] || mode=yolo
if [ -n "${FAKE_ZCODE_FAIL:-}" ]; then
  echo 'zcode fake failure' >&2
  exit "$FAKE_ZCODE_FAIL"
fi
printf '%s\n' '{"type":"system","subtype":"init","session_id":"sess_zfake"}'
printf '%s\n' '{"type":"assistant","message":{"text":"z fake partial"}}'
printf '%s\n' '{"type":"result","session_id":"sess_zfake","result":"z fake answer","is_error":false}'
EOF_ZCODE
chmod +x "$TMP/bin/zcode"
export ZCODE_BIN="$TMP/bin/zcode"

# Catalog/session surfaces without a public CLI/API stay explicitly blocked.
if $BIN session-list --agent zcode >/tmp/zlist.out 2>&1; then
  echo 'zcode session-list must be unavailable' >&2
  exit 1
fi
grep -q 'public CLI' /tmp/zlist.out
if $BIN session-cwd --agent zcode --session sess_zfake >/tmp/zcwd.out 2>&1; then
  echo 'zcode session-cwd must be unavailable' >&2
  exit 1
fi
grep -q 'public CLI' /tmp/zcwd.out

ZTS=$(date -d '+1 day' +%Y%m%d%H%M)
# Resume turn: --resume + --cwd + --mode + --json on the direct CLI command.
"$ROOT/bin/harr-schedule" --agent zcode --mode build --timestamp "$ZTS" --session sess_zfake \
  --prompt 'Z task' --cwd "$TMP/zwork" --output "$TMP/zout.log"
grep -Fq "'--resume'" "$TMP/at.job"
grep -Fq "'sess_zfake'" "$TMP/at.job"
grep -Fq "'--cwd'" "$TMP/at.job"
grep -Fq "'--mode'" "$TMP/at.job"
grep -Fq "'build'" "$TMP/at.job"
grep -Fq "'--json'" "$TMP/at.job"
if grep -Fq "'app-server'" "$TMP/at.job"; then
  echo 'zcode at job must not use app-server' >&2
  exit 1
fi
sh "$TMP/at.job" >/dev/null
grep -Fq 'sess_zfake' "$TMP/zout.log"

# New turn without a session: no --resume, but --prompt/--cwd/--mode/--json stay.
"$ROOT/bin/harr-schedule" --agent zcode --timestamp "$ZTS" \
  --prompt 'Z fresh' --cwd "$TMP/zwork" --output "$TMP/zfresh.log"
grep -Fq "'--prompt'" "$TMP/at.job"
if grep -Fq "'--resume'" "$TMP/at.job"; then
  echo 'new zcode turn must not pass --resume' >&2
  exit 1
fi

# Runner-driven resume turn: NDJSON result parsing, answer + state persistence.
ZTASK="$TMP/state/tasks/z-task.json"
cat > "$ZTASK" <<EOF_ZTASK
{"id":"z-task","status":"scheduled","agent":"zcode","mode":"yolo","cancel_requested":false,"log":"$TMP/state/jobs/z-task.jsonl"}
EOF_ZTASK
"$ROOT/bin/harr-schedule" --agent zcode --mode yolo --timestamp "$ZTS" --session sess_zfake \
  --prompt 'Z task 2' --cwd "$TMP/zwork" --log-json "$TMP/state/jobs/z-task.jsonl" \
  --save-answer "$TMP/zanswer.md" --task-state "$ZTASK"
sh "$TMP/at.job" >/dev/null
grep -Eq '"status"[[:space:]]*:[[:space:]]*"completed"' "$ZTASK"
grep -Fq 'z fake answer' "$TMP/state/jobs/z-task.jsonl"
grep -Fxq 'z fake answer' "$TMP/zanswer.md"

# Non-zero CLI exit must fail the task and surface the exit status.
ZFAIL="$TMP/state/tasks/z-fail.json"
cat > "$ZFAIL" <<EOF_ZFAIL
{"id":"z-fail","status":"scheduled","agent":"zcode","cancel_requested":false,"log":"$TMP/state/jobs/z-fail.jsonl"}
EOF_ZFAIL
"$ROOT/bin/harr-schedule" --agent zcode --timestamp "$ZTS" --prompt 'Z boom' \
  --cwd "$TMP/zwork" --log-json "$TMP/state/jobs/z-fail.jsonl" --task-state "$ZFAIL"
FAKE_ZCODE_FAIL=3 sh "$TMP/at.job" >/dev/null 2>&1 || true
grep -Eq '"status"[[:space:]]*:[[:space:]]*"failed"' "$ZFAIL"
grep -Eq 'agent exited with status 3' "$ZFAIL"

# Cancel: a requested cancel turns the finished run into a cancelled task.
ZCANCEL="$TMP/state/tasks/z-cancel.json"
cat > "$ZCANCEL" <<EOF_ZCANCEL
{"id":"z-cancel","status":"running","agent":"zcode","pid":null,"cancel_requested":true,"log":"$TMP/state/jobs/z-cancel.jsonl"}
EOF_ZCANCEL
"$ROOT/bin/harr-schedule" --agent zcode --timestamp "$ZTS" --prompt 'Z cancel' \
  --cwd "$TMP/zwork" --log-json "$TMP/state/jobs/z-cancel.jsonl" --task-state "$ZCANCEL"
sh "$TMP/at.job" >/dev/null
grep -Eq '"status"[[:space:]]*:[[:space:]]*"cancelled"' "$ZCANCEL"

# Mode validation is agent-aware; bogus modes never reach at.
assert_rejected_before_at bad_zcode_mode --agent zcode --mode bogus --session sess_zfake \
  --prompt p --cwd "$TMP/zwork" --timestamp "$ZTS" --output "$TMP/out.log"
grep -Fq 'unsupported mode' "$TMP/bad_zcode_mode.out"

# Without --cwd (and without a public session API) scheduling is refused.
if "$ROOT/bin/harr-schedule" --agent zcode --timestamp "$ZTS" --session sess_zfake \
  --prompt p --output "$TMP/out.log" >"$TMP/zcwd-missing.out" 2>&1; then
  echo 'zcode schedule without verified cwd must fail' >&2
  exit 1
fi
grep -q 'public CLI' "$TMP/zcwd-missing.out"

unset ZCODE_BIN

echo 'native C++ CLI scheduler tests passed'
