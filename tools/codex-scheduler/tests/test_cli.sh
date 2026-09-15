#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
BIN=${HARR_CODEX_SCHEDULER_BIN:-"$ROOT/build/harr-codex-scheduler"}
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

export AT_BIN="$TMP/bin/at" CODEX_BIN="$TMP/bin/codex" TTY_PATH="$TMP/tty"
export FAKE_CODEX_CWD="$TMP/work" FAKE_CODEX_ARGS="$TMP/codex.args"
export HARR_CODEX_SCHEDULER_BIN="$BIN"

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

echo 'native C++ CLI scheduler tests passed'
