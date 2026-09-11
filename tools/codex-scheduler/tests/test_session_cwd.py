#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from session_cwd import SessionResolutionError, list_codex_sessions, resolve_session_cwd


FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) < 2 or sys.argv[1] != "app-server":
    raise SystemExit(64)

sessions = json.loads(os.environ["FAKE_CODEX_SESSIONS"])
for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        print(json.dumps({"id": msg["id"], "result": {"userAgent": "fake", "codexHome": "/tmp", "platformFamily": "unix", "platformOs": "linux"}}), flush=True)
    elif method == "initialized":
        pass
    elif method == "thread/read":
        session = msg["params"]["threadId"]
        if session not in sessions:
            print(json.dumps({"id": msg["id"], "error": {"code": -32000, "message": "thread not found"}}), flush=True)
        else:
            print(json.dumps({"id": msg["id"], "result": {"thread": {"id": session, "cwd": sessions[session], "ephemeral": False, "status": {"type": "notLoaded"}}}}), flush=True)
    elif method == "thread/list":
        params = msg["params"]
        if params.get("sortKey") != "recency_at" or params.get("sortDirection") != "desc":
            print(json.dumps({"id": msg["id"], "error": {"code": -32001, "message": "wrong sort"}}), flush=True)
        else:
            ids = list(sessions.keys())
            data = []
            for index, session in enumerate(ids):
                data.append({
                    "id": session,
                    "cwd": sessions[session],
                    "preview": "Preview " + session,
                    "name": "Name " + session if index == 0 else None,
                    "createdAt": 100 + index,
                    "updatedAt": 200 + index,
                    "status": {"type": "notLoaded"},
                })
            print(json.dumps({"id": msg["id"], "result": {"data": data, "nextCursor": None}}), flush=True)
'''


def make_fake_codex(path: Path) -> None:
    path.write_text(FAKE_CODEX, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        fake = root / "codex"
        repo = root / "repo"
        git_init(repo)
        nested = repo / "subdir"
        nested.mkdir()
        nongit = root / "nongit"
        nongit.mkdir()
        make_fake_codex(fake)

        os.environ["FAKE_CODEX_SESSIONS"] = json.dumps({
            "session-root": str(repo),
            "session-nested": str(nested),
            "session-nongit": str(nongit),
        })

        assert resolve_session_cwd("session-root", codex_bin=fake) == repo.resolve()
        assert resolve_session_cwd("session-nested", codex_bin=fake) == nested.resolve()

        recent = list_codex_sessions(codex_bin=fake, limit=20)
        assert [item["id"] for item in recent] == ["session-root", "session-nested", "session-nongit"]
        assert recent[0]["name"] == "Name session-root"
        assert recent[0]["preview"] == "Preview session-root"
        assert recent[0]["cwd"] == str(repo)

        try:
            resolve_session_cwd("missing", codex_bin=fake)
        except SessionResolutionError as exc:
            assert "thread not found" in str(exc)
        else:
            raise AssertionError("missing thread must fail")

        try:
            resolve_session_cwd("session-nongit", codex_bin=fake)
        except SessionResolutionError as exc:
            assert "Git worktree" in str(exc)
        else:
            raise AssertionError("non-Git cwd must fail")

    print("session cwd + recent thread/list app-server tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
