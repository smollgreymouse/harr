#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from core import extract_assistant_answer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Codex, persist JSONL, and optionally save its clean answer")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--answer", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main() -> int:
    args = parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    if args.answer:
        args.answer.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    with args.log.open("w", encoding="utf-8", buffering=1) as log:
        proc = subprocess.Popen(
            args.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log.write(line)
            lines.append(line)
        rc = proc.wait()

    if args.answer:
        answer = extract_assistant_answer(lines)
        if not answer:
            answer = "".join(lines).strip()
        args.answer.write_text(answer + ("\n" if answer else ""), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
