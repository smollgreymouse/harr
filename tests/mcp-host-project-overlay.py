#!/usr/bin/env python3
"""Contract: project MCP session configs preserve host-specific LeanCTX surfaces."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common" / "mcp"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


manager = load("harr_mcp_manager_overlay_host_test", ROOT / "common/mcp/manager.py")
import project_overlay as overlay

EXPECTED_HOST_TOOLS = ["ctx_shell", "ctx_tools", "ctx_call"]


def mcp_tools(binary: Path, config_dir: Path, host: str) -> set[str]:
    launcher = ROOT / "common/hosts/leanctx-mcp-host.py"
    env = dict(os.environ)
    env["LEAN_CTX_CONFIG_DIR"] = str(config_dir)
    env["LEAN_CTX_STRICT_WORKSPACE"] = "1"
    env["LEAN_CTX_STRICT_WORKSPACE_LEGACY_TOOLS"] = "1"
    env.pop("LEAN_CTX_CONFIG_PROFILE", None)
    env.pop("LEAN_CTX_TOOL_PROFILE", None)
    cmd = [str(binary), "mcp"] if host == "codex" else [
        sys.executable, str(launcher), host, str(binary)
    ]
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": host, "version": "1"},
        }},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    proc = subprocess.run(
        cmd,
        input="\n".join(json.dumps(item) for item in messages) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        env=env,
        timeout=15,
        check=False,
    )
    assert proc.returncode == 0, (host, proc.stderr[-1000:])
    replies = [
        json.loads(line)
        for line in proc.stdout.splitlines()
        if line.startswith("{")
    ]
    result = next(item["result"] for item in replies if item.get("id") == 2)
    return {tool["name"] for tool in result["tools"]}


with tempfile.TemporaryDirectory(prefix="harr-host-project-overlay-") as raw:
    temp = Path(raw)
    config = temp / "config"
    xdg = temp / "xdg"
    project = temp / "project"
    manifest_path = project / ".harr" / "mcp.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({
        "schema": 1,
        "instances": {},
        "extensions": {
            "project-http": {
                "transport": "http",
                "url": "https://project.example.invalid/mcp",
            }
        },
    }) + "\n")

    manifest = overlay.load_manifest(manifest_path)
    overlay.approve(project, config, manifest["digest"])
    session = {"overlay": overlay, "manifest": manifest, "root": project}
    data = {
        "schema": 1,
        "providers": {},
        "servers": [{
            "name": "global-stdio",
            "transport": "stdio",
            "runtime": {"kind": "path", "command": "true"},
            "secrets": [],
        }],
    }

    with patch.dict(os.environ, {
        "HARR_CONFIG_DIR": str(config),
        "XDG_CONFIG_HOME": str(xdg),
    }, clear=False):
        config_path, secret_refs = manager._session_config(data, session)

    assert secret_refs == []
    parsed = tomllib.loads(config_path.read_text())
    assert parsed["profiles"]["harr-zcode"]["tools_enabled"] == EXPECTED_HOST_TOOLS
    assert parsed["profiles"]["harr-opencode"]["tools_enabled"] == EXPECTED_HOST_TOOLS
    gateway_names = [entry["name"] for entry in parsed["gateway"]["servers"]]
    assert gateway_names == ["global-stdio", "project-http"], gateway_names

    # Optional black-box check against a real LeanCTX binary. CI can run the
    # pure config contract without shipping LeanCTX; local/release validation
    # supplies the binary path as argv[1].
    if len(sys.argv) > 1:
        binary = Path(sys.argv[1]).resolve(strict=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(zip(
                ["codex", "opencode", "zcode"],
                pool.map(
                    lambda host: mcp_tools(binary, config_path.parent, host),
                    ["codex", "opencode", "zcode"],
                ),
            ))
        assert {"ctx_read", "ctx_search", "ctx_glob", "ctx_shell", "ctx_tools"}.issubset(results["codex"])
        for host in ("opencode", "zcode"):
            tools = results[host]
            assert {"ctx_shell", "ctx_tools", "ctx_call"}.issubset(tools), (host, tools)
            assert tools.isdisjoint({"ctx_read", "ctx_search", "ctx_glob", "ctx_expand"}), (host, tools)
        print("runtime host surfaces on project session config: PASS")

print("project overlay preserves host-specific LeanCTX profiles: PASS")
