#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "common" / "git_host" / "git_host.py"
spec = importlib.util.spec_from_file_location("harr_git_host", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check_secret() -> None:
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "secrets" / "capability"
        first = mod.ensure_secret(path)
        second = mod.ensure_secret(path)
        assert first == second
        assert len(first) >= 32
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def check_request() -> None:
    with tempfile.TemporaryDirectory() as raw:
        cwd = Path(raw)
        actual = mod.validate_request({"cwd": str(cwd), "args": ["push", "origin", "HEAD"]})
        assert actual == (cwd, ["push", "origin", "HEAD"])
        for invalid in (
            {},
            {"cwd": "relative", "args": ["status"]},
            {"cwd": str(cwd), "args": []},
            {"cwd": str(cwd), "args": ["status\x00bad"]},
        ):
            try:
                mod.validate_request(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid request accepted: {invalid!r}")


def check_git_execution() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        binary_dir = root / "bin"
        work = root / "work"
        binary_dir.mkdir()
        work.mkdir()
        fake_git = binary_dir / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            "printf 'cwd=%s\\n' \"$PWD\"\n"
            "printf 'agent=%s\\n' \"${SSH_AUTH_SOCK:-}\"\n"
            "printf 'args=%s\\n' \"$*\"\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{binary_dir}:{old_path}"
        try:
            with mock.patch.dict(os.environ, {"SSH_AUTH_SOCK": "/agent.sock"}):
                result = mod.run_git(work, ["push", "origin", "HEAD"])
        finally:
            os.environ["PATH"] = old_path
        assert result["exit_code"] == 0
        assert f"cwd={work}" in result["stdout"]
        assert "agent=/agent.sock" in result["stdout"]
        assert "args=push origin HEAD" in result["stdout"]


check_secret()
check_request()
check_git_execution()
print("Git host bridge: PASS")
