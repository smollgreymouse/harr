#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/work"
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
#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == "app-server":
    cwd = os.environ["FAKE_CODEX_CWD"]
    for line in sys.stdin:
        msg = json.loads(line)
        method = msg.get("method")
        if method == "initialize":
            print(json.dumps({"id": msg["id"], "result": {"userAgent": "fake", "codexHome": "/tmp", "platformFamily": "unix", "platformOs": "linux"}}), flush=True)
        elif method == "initialized":
            pass
        elif method == "thread/read":
            sid = msg["params"]["threadId"]
            print(json.dumps({"id": msg["id"], "result": {"thread": {"id": sid, "cwd": cwd, "ephemeral": False, "status": {"type": "notLoaded"}}}}), flush=True)
    raise SystemExit(0)

with open(os.environ["FAKE_CODEX_ARGS"], "w", encoding="utf-8") as fh:
    for arg in sys.argv[1:]:
        fh.write(arg + "\n")
EOF_CODEX
chmod +x "$TMP/bin/codex"

export AT_BIN="$TMP/bin/at" CODEX_BIN="$TMP/bin/codex" TTY_PATH="$TMP/tty"
export FAKE_CODEX_CWD="$TMP/work" FAKE_CODEX_ARGS="$TMP/codex.args"

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

FUTURE_TS=$(date -d '+1 day' +%Y%m%d%H%M)
"$ROOT/bin/codex-schedule" --model gpt-5.6-sol --reasoning medium --speed fast --timestamp "$FUTURE_TS" --session s --prompt p --cwd "$TMP/work" --output "$TMP/out.log"
grep -Fxq -- '-t' "$TMP/at.args"
grep -Fxq -- "$FUTURE_TS" "$TMP/at.args"
grep -Fq "cd '$TMP/work'" "$TMP/at.job"
grep -Fq 'service_tier="fast"' "$TMP/at.job"
grep -Fq 'model_reasoning_effort="medium"' "$TMP/at.job"

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

grep -Fq 'expected CCYYMMDDhhmm' "$TMP/bad_shape.out"
grep -Fq 'invalid calendar date/time' "$TMP/bad_calendar.out"
grep -Fq 'must be in the future' "$TMP/past_time.out"
grep -Fq 'invalid HH:MM' "$TMP/bad_clock.out"

mkdir -p "$TMP/wrong"
git init -q "$TMP/wrong"
if "$ROOT/bin/codex-schedule" --model gpt-5.6-sol --reasoning high --speed standard --at 02:05 --session s --prompt p --cwd "$TMP/wrong" --output "$TMP/out.log" >"$TMP/mismatch.out" 2>&1; then
  echo 'expected cwd mismatch to fail' >&2
  exit 1
fi
grep -Fq -- '--cwd mismatch' "$TMP/mismatch.out"

echo 'CLI scheduler tests passed'
