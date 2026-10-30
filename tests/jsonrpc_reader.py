"""Deadline-bounded stdout reader for JSON-RPC subprocess tests on all OSes."""

from __future__ import annotations

import queue
import threading
from typing import TextIO


def _read_lines(stream: TextIO, lines: queue.Queue[str | None]) -> None:
    try:
        while True:
            line = stream.readline()
            if not line:
                lines.put(None)
                return
            lines.put(line)
    except OSError:
        lines.put(None)


def _reader(process):
    reader = getattr(process, "_harr_jsonrpc_reader", None)
    if reader is None:
        if process.stdout is None:
            raise AssertionError("JSON-RPC subprocess has no stdout pipe")
        lines: queue.Queue[str | None] = queue.Queue()
        reader = (lines, threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True))
        process._harr_jsonrpc_reader = reader
        reader[1].start()
    return reader


def read_jsonrpc_line(process, timeout: float) -> str:
    lines, _ = _reader(process)
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty as exc:
        raise AssertionError(f"timed out waiting for JSON-RPC subprocess output after {timeout}s") from exc
    if line is None:
        raise AssertionError("JSON-RPC subprocess closed stdout before replying")
    return line


def join_jsonrpc_reader(process, timeout: float = 5.0) -> None:
    reader = getattr(process, "_harr_jsonrpc_reader", None)
    if reader is None:
        return
    reader[1].join(timeout=timeout)
    if reader[1].is_alive():
        raise AssertionError("JSON-RPC subprocess stdout reader did not stop")
