#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import tempfile
import tomllib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manager", ROOT / "common/mcp/manager.py")
assert spec and spec.loader
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)
registry = manager.load_registry(ROOT / "common/mcp/registry.json")
jira = manager.server_by_name(registry, "jira")
assert jira["transport"] == "stdio" and jira["lifecycle"] == "on-demand"
assert jira["runtime"]["args"] == ["mcp-atlassian"]
assert jira["secrets"][0]["target"] == {"kind": "env", "name": "JIRA_PERSONAL_TOKEN"}
with tempfile.TemporaryDirectory() as temp:
    tmp = Path(temp)
    manager.install_configs(type("Args", (), {"config_dir": str(tmp)})(), {"servers": [jira]})
    env_file = (tmp / "jira.env").read_text()
    assert "JIRA_URL=" in env_file and "JIRA_PERSONAL_TOKEN=" not in env_file
    output = tmp / "leanctx.toml"
    manager.render_leanctx(type("Args", (), {
        "base": str(ROOT / "common/leanctx/config.base.toml"),
        "output": str(output), "platform": "linux", "runner_command": "harr-mcp-run"
    })(), {"servers": [jira]})
    config = tomllib.loads(output.read_text())
    item = next(s for s in config["gateway"]["servers"] if s["name"] == "jira")
    assert item["transport"] == "stdio"
    assert item["command"] == "harr-mcp-run"
    assert item["secret_env"]["JIRA_PERSONAL_TOKEN"]["id"] == "mcp/jira/default"
    assert "JIRA_PERSONAL_TOKEN" not in item.get("env", {})
    (tmp / "secrets").mkdir()
    (tmp / "secrets/jira-personal-token").write_text("example-test-token")
    with patch.dict(manager.os.environ, {"HARR_CONFIG_DIR": str(tmp)}):
        assert manager.service_secret_env(jira) == {"JIRA_PERSONAL_TOKEN": "example-test-token"}
with patch.object(manager.shutil, "which", return_value="/usr/bin/uvx"):
    assert manager.runtime_command(jira) == ["/usr/bin/uvx", "mcp-atlassian"]
print("Jira MCP registry and secrets: PASS")
