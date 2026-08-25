#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "common" / "mcp" / "manager.py"
REGISTRY_PATH = ROOT / "common" / "mcp" / "registry.json"
BASE_CONFIG = ROOT / "common" / "leanctx" / "config.base.toml"

spec = importlib.util.spec_from_file_location("harr_mcp_manager", MANAGER_PATH)
assert spec and spec.loader
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
servers = {item["name"]: item for item in registry["servers"]}
assert set(("codegraph", "gitlab", "grafana")) <= set(servers)

grafana = servers["grafana"]
assert grafana["transport"] == "stdio"
assert grafana["lifecycle"] == "on-demand"
assert grafana["runtime"] == {
    "kind": "uvx",
    "package": "mcp-grafana",
    "command": "uvx",
    "args": ["mcp-grafana"],
    "prefetch_args": ["mcp-grafana", "--version"],
    "probe_args": ["--offline", "mcp-grafana", "--version"],
    "install_hint": "uvx is required for Grafana MCP; install uv/uvx and run `harr install mcp`",
}
assert grafana["secrets"] == [
    {
        "name": "grafana",
        "file": "grafana-service-account-token",
        "prompt": "Grafana service account token",
        "memento_id": "mcp/grafana/default",
        "target": {"kind": "env", "name": "GRAFANA_SERVICE_ACCOUNT_TOKEN"},
    }
]

for platform in ("linux", "windows"):
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "config.toml"
        args = type("Args", (), {
            "base": str(BASE_CONFIG),
            "output": str(output),
            "platform": platform,
            "runner_command": "harr-mcp-run",
        })()
        manager.render_leanctx(args, manager.load_registry(REGISTRY_PATH))
        config = tomllib.loads(output.read_text(encoding="utf-8"))
        rendered = {item["name"]: item for item in config["gateway"]["servers"]}
        item = rendered["grafana"]
        assert item["transport"] == "stdio"
        assert item["command"] == "harr-mcp-run"
        assert item["args"] == ["grafana"]
        assert item["secret_env"]["GRAFANA_SERVICE_ACCOUNT_TOKEN"] == {"id": "mcp/grafana/default"}

with tempfile.TemporaryDirectory() as tmp:
    target = Path(tmp)
    args = type("Args", (), {"config_dir": str(target)})()
    manager.install_configs(args, manager.load_registry(REGISTRY_PATH))
    grafana_env = (target / "grafana.env").read_text(encoding="utf-8")
    assert "GRAFANA_URL=http://localhost:3000" in grafana_env
    assert "GRAFANA_SERVICE_ACCOUNT_TOKEN=" not in grafana_env

assert manager.memento_var("mcp/grafana/default") == "LEAN_CTX_SECRET_6D63702F67726166616E612F64656661756C74"
with patch.object(manager.shutil, "which", return_value="/tmp/uvx"):
    grafana_command = manager.runtime_command(grafana)
    assert grafana_command == ["/tmp/uvx", "mcp-grafana"]
    assert manager.runtime_maintenance_command(grafana, "prefetch_args") == ["/tmp/uvx", "mcp-grafana", "--version"]
    assert manager.runtime_maintenance_command(grafana, "probe_args") == ["/tmp/uvx", "--offline", "mcp-grafana", "--version"]
print("cross-platform MCP registry: PASS")
