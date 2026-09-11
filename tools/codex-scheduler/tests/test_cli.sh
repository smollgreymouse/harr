#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/work" "$TMP/codex-home/sessions/2026/09/11"
git init -q "$TMP/work"
: > "$TMP/tty"

cat > "$TMP/bin/at" <<EOF_AT
#!/bin/sh
printf '%s\n' "\$@" > '$TMP/at.args'
cat > '$TMP/at.job'
echo 'job 42 at Fri Sep 11 02:05:00 2026' >&2
EOF_AT
chmod +x "$TMP/bin/at"
cat > "$TMP/bin/codex" <<EOF_CODEX
#!/bin/sh
printf '%s\n' "\$@" > '$TMP/codex.args'
EOF_CODEX
chmod +x "$TMP/bin/codex"

write_rollout() {
  local session=$1
  cat > "$TMP/codex-home/sessions/2026/09/11/rollout-2026-09-11T02-05-00-$session.jsonl" <<EOF_JSON
{"timestamp":"2026-09-11T02:05:00Z","type":"session_meta","payload":{"id":"$session","session_id":"$session","cwd":"$TMP/work","cli_version":"0.153.4","source":"cli"}}
EOF_JSON
}

write_rollout session-123
write_rollout s
export AT_BIN="$TMP/bin/at" CODEX_BIN="$TMP/bin/codex" CODEX_HOME="$TMP/codex-home" TTY_PATH="$TMP/tty"

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
  sh "$TMP/at.job"
  grep -Fxq "$expected_model" "$TMP/codex.args"
  grep -Fxq 'service_tier="default"' "$TMP/codex.args"
  grep -Fxq 'model_reasoning_effort="high"' "$TMP/codex.args"
  grep -Fxq 'resume' "$TMP/codex.args"
  grep -Fxq 'session-123' "$TMP/codex.args"
}

run_wrapper sol gpt-5.6-sol
run_wrapper terra gpt-5.6-terra
run_wrapper luna gpt-5.6-luna

"$ROOT/bin/codex-schedule" --model gpt-5.6-sol --reasoning medium --speed fast --timestamp 202609110205 --session s --prompt p --cwd "$TMP/work" --output "$TMP/out.log"
grep -Fxq -- '-t' "$TMP/at.args"
grep -Fxq -- '202609110205' "$TMP/at.args"
grep -Fq "cd '$TMP/work'" "$TMP/at.job"
grep -Fq 'service_tier="fast"' "$TMP/at.job"
grep -Fq 'model_reasoning_effort="medium"' "$TMP/at.job"

mkdir -p "$TMP/wrong"
git init -q "$TMP/wrong"
if "$ROOT/bin/codex-schedule" --model gpt-5.6-sol --reasoning high --speed standard --at 02:05 --session s --prompt p --cwd "$TMP/wrong" --output "$TMP/out.log" >"$TMP/mismatch.out" 2>&1; then
  echo 'expected cwd mismatch to fail' >&2
  exit 1
fi
grep -Fq -- '--cwd mismatch' "$TMP/mismatch.out"

echo 'CLI scheduler tests passed'
