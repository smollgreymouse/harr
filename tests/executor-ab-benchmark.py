#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR_DIR = ROOT / "common" / "executor"
sys.path.insert(0, str(EXECUTOR_DIR))
import ab_benchmark as ab  # noqa: E402

parent_events = (
    {"type": "thread.started", "thread_id": "parent-1"},
    {
        "type": "item.completed",
        "item": {
            "type": "collab_tool_call",
            "tool": "spawn_agent",
            "receiver_thread_ids": ["child-1"],
        },
    },
    {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 500,
            "cached_input_tokens": 300,
            "cache_write_input_tokens": 10,
            "output_tokens": 40,
            "reasoning_output_tokens": 20,
        },
    },
)
assert ab.thread_id(parent_events) == "parent-1"
assert ab.spawned_child_ids(parent_events) == ["child-1"]
assert ab.parent_usage(parent_events)["input_tokens"] == 500

packet = {
    "protocol": "harr.executor.v1",
    "state": "DONE",
    "current_step": None,
    "completed_steps": ["B001"],
    "summary": "done",
    "changed_files": ["src/a.cpp"],
    "validation": [{"check": "unit", "status": "PASS", "detail": "ok"}],
    "blocker": None,
}
rollout_lines = [
    {
        "type": "turn_context",
        "payload": {"model": "gpt-5.6-luna", "reasoning_effort": "low"},
    },
    {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": 1200,
                    "cached_input_tokens": 800,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 100,
                    "reasoning_output_tokens": 30,
                }
            },
        },
    },
    {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": json.dumps(packet)}],
        },
    },
]
assert ab.packet_from_rollout_lines(rollout_lines) == packet
assert ab.rollout_usage(rollout_lines)["cached_input_tokens"] == 800
assert ab.rollout_model(rollout_lines) == ("gpt-5.6-luna", "low")

prompt = ab.native_initial_prompt("# HARR EXECUTOR CONTRACT v1", "gpt-5.6-luna", "low")
assert 'fork_turns="none"' in prompt
assert "model=gpt-5.6-luna" in prompt
assert "reasoning_effort=low" in prompt
assert "Do not inspect/edit/build/test" in prompt
assert "Terminal response JSON Schema (mandatory)" in prompt
assert '"required":["protocol","state"' in prompt

followup = ab.native_followup_prompt("Decision: use API A")
assert "Do not inspect/edit/build/test" in followup
assert "spawn another child" in followup
assert "Decision: use API A" in followup

cmp = ab.comparison(
    {"child_usage": ab.usage({"input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 50})},
    {"executor_usage": ab.usage({"input_tokens": 800, "cached_input_tokens": 500, "output_tokens": 60})},
)
assert cmp["input_tokens"]["delta_bridge_minus_native"] == -200
assert cmp["uncached_input_tokens_derived"]["native"] == 400
assert cmp["uncached_input_tokens_derived"]["bridge"] == 300

with tempfile.TemporaryDirectory() as tmp_raw:
    tmp = Path(tmp_raw)
    sessions = tmp / "sessions" / "2026" / "09" / "15"
    sessions.mkdir(parents=True)
    rollout = sessions / "rollout-2026-09-15T00-00-00-child-1.jsonl"
    rollout.write_text("\n".join(json.dumps(item) for item in rollout_lines) + "\n", encoding="utf-8")
    assert ab.find_rollout(tmp, "child-1", wait_seconds=0) == rollout

print("executor native-vs-bridge A/B helpers: PASS")
