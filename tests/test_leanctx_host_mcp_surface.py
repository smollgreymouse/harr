#!/usr/bin/env python3
"""Integration smoke: simultaneous MCP hosts share one config but not tool visibility.

Run explicitly against the installed Harr LeanCTX binary:
  python3 tests/test_leanctx_host_mcp_surface.py /path/to/real/lean-ctx
"""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "common/hosts/leanctx-mcp-host.py"


def request(binary: Path, config_dir: Path, host: str) -> tuple[str, set[str], str]:
    env = dict(os.environ)
    env["LEAN_CTX_CONFIG_DIR"] = str(config_dir)
    env["LEAN_CTX_DATA_DIR"] = str(config_dir / f"data-{host}")
    env["LEAN_CTX_STRICT_WORKSPACE"] = "1"
    env["LEAN_CTX_STRICT_WORKSPACE_LEGACY_TOOLS"] = "1"
    env.pop("LEAN_CTX_TOOL_PROFILE", None)
    env.pop("LEAN_CTX_CONFIG_PROFILE", None)
    cmd = [str(binary), "mcp"] if host == "codex" else [
        sys.executable, str(LAUNCHER), host, str(binary)
    ]
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": host, "version": "1.0"},
        }},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "ctx_call",
            "arguments": {"name": "ctx_expand", "arguments": {
                "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }},
        }},
    ]
    proc = subprocess.run(
        cmd, input="\n".join(json.dumps(m) for m in messages) + "\n",
        text=True, capture_output=True, env=env, timeout=15, check=False,
        cwd=ROOT,
    )
    if proc.returncode:
        raise AssertionError(f"{host}: MCP exit {proc.returncode}: {proc.stderr[-1000:]}")
    replies = {
        item["id"]: item for line in proc.stdout.splitlines()
        if line.startswith("{")
        if (item := json.loads(line)).get("id") is not None
    }
    names = {tool["name"] for tool in replies[2]["result"]["tools"]}
    if "result" not in replies[3]:
        raise AssertionError(f"{host}: ctx_call returned a JSON-RPC error: {replies[3]}")
    recovery_text = " ".join(c.get("text", "") for c in replies[3]["result"]["content"])
    return host, names, recovery_text


def verify_zcode_launcher_context() -> None:
    """The host adapter must preserve the session project CWD for Harr auto-binding."""
    if os.name == "nt":
        return
    with tempfile.TemporaryDirectory(prefix="harr-zcode-launch-context-") as temp:
        temp_path = Path(temp)
        project = temp_path / "project"
        project.mkdir()
        fake_binary = temp_path / "lean-ctx-probe"
        fake_binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os\n"
            "print(json.dumps({\n"
            "  'cwd': os.getcwd(),\n"
            "  'profile': os.environ.get('LEAN_CTX_CONFIG_PROFILE'),\n"
            "  'workspace_root': os.environ.get('HARR_WORKSPACE_ROOT'),\n"
            "}))\n",
            encoding="utf-8",
        )
        fake_binary.chmod(0o755)
        env = dict(os.environ)
        env.pop("HARR_WORKSPACE_ROOT", None)
        env.pop("LEAN_CTX_CONFIG_PROFILE", None)
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "zcode", str(fake_binary)],
            text=True, capture_output=True, env=env, cwd=project, timeout=5,
            check=False,
        )
        if proc.returncode:
            raise AssertionError(f"ZCode host adapter failed: {proc.stderr[-1000:]}")
        context = json.loads(proc.stdout)
        assert context == {
            "cwd": str(project),
            "profile": "harr-zcode",
            "workspace_root": None,
        }, context


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_leanctx_host_mcp_surface.py LEANCTX_BINARY")
    binary = Path(sys.argv[1]).resolve(strict=True)
    verify_zcode_launcher_context()
    template = (ROOT / "common/leanctx/config.base.toml").read_text()
    template = template.replace("{{HARR_ALLOW_PATHS}}", "").replace(
        "{{HARR_SHELL_ALLOWLIST_EXTRA}}", ""
    ).replace("# {{HARR_GATEWAY_SERVERS}}", "")
    with tempfile.TemporaryDirectory(prefix="harr-mcp-host-profiles-") as temp:
        config_dir = Path(temp)
        (config_dir / "config.toml").write_text(template)
        # Same config directory and binary for all concurrent MCP processes.
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(
                (host, (names, recovery))
                for host, names, recovery in pool.map(
                    lambda host: request(binary, config_dir, host),
                    ["codex", "opencode", "zcode"],
                )
            )
    codex, _ = results["codex"]
    assert {"ctx_read", "ctx_search", "ctx_glob", "ctx_shell", "ctx_tools"}.issubset(codex), codex
    for host in ["opencode", "zcode"]:
        names, recovery = results[host]
        assert {"ctx_shell", "ctx_tools", "ctx_call"}.issubset(names), (host, names)
        assert names.isdisjoint({"ctx_read", "ctx_search", "ctx_glob", "ctx_expand"}), (host, names)
        assert "not found or expired" in recovery, (host, recovery)
        print(f"{host}: {sorted(names)}; ctx_call→ctx_expand dispatch OK")
    print(f"codex: {sorted(codex)}; shared config, independent MCP surfaces OK")


if __name__ == "__main__":
    main()
