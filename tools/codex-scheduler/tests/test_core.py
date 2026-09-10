#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from core import extract_assistant_answer, parse_codex_json_line


class CoreTests(unittest.TestCase):
    def test_agent_message(self) -> None:
        line = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}})
        events = parse_codex_json_line(line)
        self.assertEqual([(e.kind, e.text) for e in events], [("assistant", "Done")])

    def test_error(self) -> None:
        events = parse_codex_json_line(json.dumps({"type": "error", "message": "limit"}))
        self.assertEqual(events[0].kind, "error"); self.assertEqual(events[0].text, "limit")

    def test_answer_extraction(self) -> None:
        lines = [json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "First"}}), json.dumps({"type": "item.completed", "item": {"type": "agent_message", "content": [{"text": "Second"}]}})]
        self.assertEqual(extract_assistant_answer(lines), "First\n\nSecond")

    def test_job_runner_saves_log_and_clean_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir); fake = tmp / "fake.py"
            fake.write_text("import json\nprint(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Final answer'}}))\nprint(json.dumps({'type':'turn.completed'}))\n", encoding="utf-8")
            log = tmp / "job.jsonl"; answer = tmp / "answer.md"
            proc = subprocess.run([sys.executable, str(ROOT / "app" / "job_runner.py"), "--log", str(log), "--answer", str(answer), "--", sys.executable, str(fake)], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("agent_message", log.read_text(encoding="utf-8"))
            self.assertEqual(answer.read_text(encoding="utf-8"), "Final answer\n")


if __name__ == "__main__": unittest.main()
