#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class SessionResolutionError(RuntimeError):
    pass


def _send(proc: subprocess.Popen[str], message: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    proc.stdin.flush()


def _wait_for_response(proc: subprocess.Popen[str], request_id: int, timeout: float) -> dict:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SessionResolutionError(f"timed out waiting for codex app-server response id={request_id}")
        ready, _, _ = select.select([proc.stdout], [], [], remaining)
        if not ready:
            raise SessionResolutionError(f"timed out waiting for codex app-server response id={request_id}")
        line = proc.stdout.readline()
        if line == "":
            raise SessionResolutionError("codex app-server exited before returning the requested thread")
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") != request_id:
            continue
        if "error" in message:
            error = message.get("error")
            if isinstance(error, dict):
                detail = error.get("message") or json.dumps(error, ensure_ascii=False)
            else:
                detail = str(error)
            raise SessionResolutionError(f"codex app-server request failed: {detail}")
        result = message.get("result")
        if not isinstance(result, dict):
            raise SessionResolutionError("codex app-server returned a malformed result")
        return result


def _read_stderr(stderr_file) -> str:
    try:
        stderr_file.flush()
        stderr_file.seek(0)
        return stderr_file.read().strip()
    except OSError:
        return ""


def resolve_session_cwd(
    session: str,
    *,
    codex_bin: str | Path = "codex",
    timeout: float = 10.0,
    require_git: bool = True,
) -> Path:
    session = session.strip()
    if not session:
        raise SessionResolutionError("session id is empty")

    codex = str(codex_bin)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr_file:
        try:
            proc = subprocess.Popen(
                [codex, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise SessionResolutionError(f"codex executable not found: {codex}") from exc

        try:
            _send(
                proc,
                {
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "clientInfo": {
                            "name": "harr_codex_scheduler",
                            "title": "Harr Codex Scheduler",
                            "version": "1.0.0",
                        }
                    },
                },
            )
            _wait_for_response(proc, 0, timeout)
            _send(proc, {"method": "initialized", "params": {}})
            _send(
                proc,
                {
                    "method": "thread/read",
                    "id": 1,
                    "params": {"threadId": session, "includeTurns": False},
                },
            )
            result = _wait_for_response(proc, 1, timeout)
        except SessionResolutionError as exc:
            detail = _read_stderr(stderr_file)
            if detail:
                raise SessionResolutionError(f"{exc}; app-server stderr: {detail}") from exc
            raise
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)

    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise SessionResolutionError("thread/read response does not contain a thread object")
    returned_id = str(thread.get("id", ""))
    if returned_id and returned_id != session:
        raise SessionResolutionError(
            f"thread/read returned unexpected thread id {returned_id!r} for requested {session!r}"
        )
    cwd_value = thread.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value.strip():
        raise SessionResolutionError("thread/read response does not contain thread.cwd")

    cwd = Path(cwd_value).expanduser()
    if not cwd.is_absolute():
        raise SessionResolutionError(f"thread/read returned non-absolute cwd: {cwd_value!r}")
    try:
        cwd = cwd.resolve(strict=True)
    except OSError as exc:
        raise SessionResolutionError(f"saved session cwd does not exist: {cwd}") from exc
    if not cwd.is_dir():
        raise SessionResolutionError(f"saved session cwd is not a directory: {cwd}")

    if require_git:
        try:
            probe = subprocess.run(
                ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SessionResolutionError("git executable not found; cannot verify session cwd") from exc
        if probe.returncode != 0:
            detail = probe.stderr.strip() or "not inside a Git worktree"
            raise SessionResolutionError(f"session cwd is not a usable Git worktree: {cwd}: {detail}")

    return cwd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a Codex session cwd through the documented codex app-server thread/read API"
    )
    parser.add_argument("--session", required=True)
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--no-git-check", action="store_true")
    args = parser.parse_args()
    try:
        cwd = resolve_session_cwd(
            args.session,
            codex_bin=args.codex_bin,
            timeout=args.timeout,
            require_git=not args.no_git_check,
        )
    except SessionResolutionError as exc:
        print(f"codex-session-cwd: {exc}", file=sys.stderr)
        return 2
    print(cwd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
