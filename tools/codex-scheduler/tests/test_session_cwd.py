#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from session_cwd import SessionResolutionError, resolve_session_cwd


def write_rollout(home: Path, session: str, cwd: Path, suffix: str = "") -> Path:
    target = home / "sessions" / "2026" / "09" / "11"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"rollout-2026-09-11T02-05-00{suffix}-{session}.jsonl"
    record = {
        "timestamp": "2026-09-11T02:05:00Z",
        "type": "session_meta",
        "payload": {
            "id": session,
            "session_id": session,
            "cwd": str(cwd),
            "cli_version": "0.153.4",
            "source": "cli",
        },
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return path


def git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        home = root / "codex"
        repo = root / "repo"
        git_init(repo)
        session = "01a08c7c-df16-74c3-9357-a6cac183895c"
        write_rollout(home, session, repo)
        assert resolve_session_cwd(session, codex_home=home) == repo.resolve()

        nested = repo / "subdir"
        nested.mkdir()
        session_nested = "01a08c7c-df16-74c3-9357-a6cac183895d"
        write_rollout(home, session_nested, nested, "-nested")
        assert resolve_session_cwd(session_nested, codex_home=home) == nested.resolve()

        other = root / "other"
        git_init(other)
        write_rollout(home, session, other, "-conflict")
        try:
            resolve_session_cwd(session, codex_home=home)
        except SessionResolutionError as exc:
            assert "conflicting cwd" in str(exc)
        else:
            raise AssertionError("conflicting session cwd must fail closed")

        nongit = root / "nongit"
        nongit.mkdir()
        nongit_session = "01a08c7c-df16-74c3-9357-a6cac183895e"
        write_rollout(home, nongit_session, nongit, "-nongit")
        try:
            resolve_session_cwd(nongit_session, codex_home=home)
        except SessionResolutionError as exc:
            assert "Git worktree" in str(exc)
        else:
            raise AssertionError("non-Git session cwd must fail closed")

    print("session cwd resolver tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
