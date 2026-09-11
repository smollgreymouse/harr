#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from task_store import TaskStore


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "state"
        store = TaskStore(root)

        first = store.new_draft()
        first_id = str(first["id"])
        assert first["status"] == "draft"
        store.patch(first_id, session="session-1", prompt="Do work")
        loaded = store.load(first_id)
        assert loaded is not None
        assert loaded["session"] == "session-1"
        assert loaded["prompt"] == "Do work"
        assert len(store.active()) == 1

        store.save_ui([first_id], first_id)
        ui = store.load_ui()
        assert ui["open_task_ids"] == [first_id]
        assert ui["current_task_id"] == first_id

        fake_bin = Path(tmp) / "bin"
        fake_bin.mkdir()
        atrm_log = Path(tmp) / "atrm.log"
        atrm = fake_bin / "atrm"
        atrm.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > " + repr(str(atrm_log)) + "\n",
            encoding="utf-8",
        )
        atrm.chmod(0o755)
        store.patch(first_id, status="scheduled", at_job="42")
        cancelled = store.cancel(first_id, atrm_bin=str(atrm))
        assert cancelled["status"] == "cancelled"
        assert atrm_log.read_text(encoding="utf-8").strip() == "42"

        log_path = Path(str(cancelled["log"]))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("internal log\n", encoding="utf-8")
        answer_path = Path(tmp) / "answer.md"
        answer_path.write_text("answer\n", encoding="utf-8")
        store.patch(first_id, answer=str(answer_path))
        store.delete(first_id, delete_log=True, delete_answer=False)
        assert store.load(first_id) is None
        assert not log_path.exists()
        assert answer_path.exists()

        second = store.new_draft()
        second_id = str(second["id"])
        second_log = Path(str(second["log"]))
        second_log.write_text("log\n", encoding="utf-8")
        second_answer = Path(tmp) / "answer-2.md"
        second_answer.write_text("answer\n", encoding="utf-8")
        store.patch(second_id, status="completed", answer=str(second_answer))
        store.delete(second_id, delete_log=True, delete_answer=True)
        assert store.load(second_id) is None
        assert not second_log.exists()
        assert not second_answer.exists()

        third = store.new_draft()
        third_id = str(third["id"])
        store.patch(third_id, status="running", pid=999999)
        try:
            store.delete(third_id)
        except RuntimeError as exc:
            assert "cancel" in str(exc).lower()
        else:
            raise AssertionError("active task deletion should be rejected")

        assert json.loads(store.task_path(third_id).read_text(encoding="utf-8"))["status"] == "running"

    print("Task store lifecycle tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
