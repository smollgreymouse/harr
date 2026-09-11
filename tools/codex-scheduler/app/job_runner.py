#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from core import extract_assistant_answer
from task_store import update_task_file, utc_now


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Codex, persist JSONL, and optionally save its clean answer")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--answer", type=Path)
    parser.add_argument("--task-state", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def task_cancel_requested(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("cancel_requested")) if isinstance(data, dict) else False


def patch_task(path: Path | None, **values: object) -> None:
    if path is not None:
        update_task_file(path, values)


def main() -> int:
    args = parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    if args.answer:
        args.answer.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    try:
        with args.log.open("w", encoding="utf-8", buffering=1) as log:
            proc = subprocess.Popen(
                args.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            patch_task(
                args.task_state,
                status="running",
                pid=proc.pid,
                started_at=utc_now(),
                finished_at=None,
                error=None,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log.write(line)
                lines.append(line)
            rc = proc.wait()
    except Exception as exc:
        patch_task(
            args.task_state,
            status="failed",
            pid=None,
            finished_at=utc_now(),
            error=str(exc),
        )
        raise

    if args.answer:
        answer = extract_assistant_answer(lines)
        if not answer:
            answer = "".join(lines).strip()
        args.answer.write_text(answer + ("\n" if answer else ""), encoding="utf-8")

    cancelled = task_cancel_requested(args.task_state)
    if cancelled:
        status = "cancelled"
        error = None
    elif rc == 0:
        status = "completed"
        error = None
    else:
        status = "failed"
        error = f"Codex exited with status {rc}"
    patch_task(
        args.task_state,
        status=status,
        pid=None,
        finished_at=utc_now(),
        error=error,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
