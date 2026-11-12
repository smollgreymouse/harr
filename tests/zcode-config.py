#!/usr/bin/env python3
"""ZCode host helper contract: managed LeanCTX registration in ~/.zcode/cli/config.json."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "common" / "hosts" / "zcode-config.py"
LEANCTX = "/tmp/harr-test-lean-ctx"


def run(env: dict[str, str], *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        env=env, text=True, capture_output=True, check=check,
    )


def entry(config_path: Path) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data["mcp"]["servers"]["lean-ctx"]


with tempfile.TemporaryDirectory(prefix="harr-zcode-config-") as raw:
    tmp = Path(raw)
    env = os.environ.copy()
    env["HARR_ZCODE_HOME"] = str(tmp / "zcode")
    env["HARR_LEANCTX_COMMAND"] = LEANCTX
    config_path = tmp / "zcode/cli/config.json"

    # Missing config: status fails, apply creates the managed registration.
    failed = run(env, "status", check=False)
    assert failed.returncode == 1 and "missing" in failed.stdout
    run(env, "apply")
    assert entry(config_path) == {"type": "stdio", "command": LEANCTX, "args": ["mcp"]}
    ok = run(env, "status")
    assert ok.returncode == 0 and "managed" in ok.stdout

    # Unrelated user keys and servers survive a re-apply byte-preserving them.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["plugins"] = {"some-plugin": True}
    data["hooks"] = {"enabled": False}
    data["mcp"]["servers"]["other-server"] = {"type": "stdio", "command": "other"}
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    run(env, "apply")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["plugins"] == {"some-plugin": True}
    assert data["hooks"] == {"enabled": False}
    assert data["mcp"]["servers"]["other-server"] == {"type": "stdio", "command": "other"}
    assert entry(config_path) == {"type": "stdio", "command": LEANCTX, "args": ["mcp"]}
    assert run(env, "status").returncode == 0

    # The pre-Harr bootstrap registration (relative command) is adoptable and reported stale.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["mcp"]["servers"]["lean-ctx"] = {"type": "stdio", "command": "lean-ctx", "args": ["mcp"]}
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    failed = run(env, "status", check=False)
    assert failed.returncode == 1 and "bootstrap" in failed.stdout
    run(env, "apply")
    assert entry(config_path) == {"type": "stdio", "command": LEANCTX, "args": ["mcp"]}

    # A foreign lean-ctx entry is never overwritten: apply fails closed and the
    # file stays byte-identical.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["mcp"]["servers"]["lean-ctx"] = {"type": "stdio", "command": "/usr/bin/foreign-lean-ctx", "args": ["mcp"]}
    foreign_text = json.dumps(data, indent=2) + "\n"
    config_path.write_text(foreign_text, encoding="utf-8")
    failed = run(env, "apply", check=False)
    assert failed.returncode != 0
    assert "refusing to overwrite a foreign ZCode MCP entry" in failed.stderr
    assert config_path.read_text(encoding="utf-8") == foreign_text
    failed = run(env, "status", check=False)
    assert failed.returncode == 1 and "stale" in failed.stdout

    # Invalid JSON is reported as invalid, not rewritten.
    config_path.write_text("{not json", encoding="utf-8")
    failed = run(env, "status", check=False)
    assert failed.returncode == 2 and "invalid" in failed.stdout
    failed = run(env, "apply", check=False)
    assert failed.returncode != 0
    assert config_path.read_text(encoding="utf-8") == "{not json"

    # An empty config file adopts the managed entry.
    config_path.write_text("", encoding="utf-8")
    run(env, "apply")
    assert entry(config_path) == {"type": "stdio", "command": LEANCTX, "args": ["mcp"]}

print("ZCode host config contract: PASS")
