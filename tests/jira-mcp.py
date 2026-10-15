#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import tempfile
import tomllib
import ssl
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manager", ROOT / "common/mcp/manager.py")
assert spec and spec.loader
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)
registry = manager.load_registry(ROOT / "common/mcp/registry.json")
jira = manager.server_by_name(registry, "jira")
assert jira["transport"] == "stdio" and jira["lifecycle"] == "on-demand"
assert jira["trust_store"] == "system"
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

# Verify that a locally generated trust bundle uses system CAs and NSS TLS anchors.
# No authentication tokens or confidential endpoints are stored in the test.
if manager.sys.platform == "linux":
    bundle = manager.system_trust_bundle()
    assert bundle is not None and bundle.is_file()
    context = ssl.create_default_context(cafile=str(bundle))
    assert context.cert_store_stats()["x509_ca"] > 0
print("system trust bundle: PASS")

# Basic credential translation and fail-closed validation.
basic = manager.prepare_jira_env({
    "JIRA_URL": "https://jira.example.test/jira",
    "JIRA_HOST": "jira.example.test",
    "JIRA_AUTH_MODE": "basic",
    "JIRA_USER_NAME": "example",
    "JIRA_USER_PASS": "test-password",
    "JIRA_PERSONAL_TOKEN": "unused-pat",
})
assert basic["JIRA_USERNAME"] == "example"
assert basic["JIRA_API_TOKEN"] == "test-password"
assert "JIRA_PERSONAL_TOKEN" not in basic
assert "JIRA_USER_PASS" not in basic
pat = manager.prepare_jira_env({"JIRA_URL":"https://jira.example.test/jira","JIRA_PERSONAL_TOKEN":"pat"})
assert pat["JIRA_PERSONAL_TOKEN"] == "pat"
for invalid in (
    {"JIRA_URL":"http://jira.example.test","JIRA_PERSONAL_TOKEN":"pat"},
    {"JIRA_URL":"https://jira.example.test","JIRA_HOST":"other.example.test","JIRA_PERSONAL_TOKEN":"pat"},
    {"JIRA_URL":"https://jira.example.test","JIRA_AUTH_MODE":"basic","JIRA_USER_NAME":"example"},
):
    try: manager.prepare_jira_env(invalid)
    except SystemExit: pass
    else: raise AssertionError("invalid Jira authentication config accepted")
print("Jira auth modes: PASS")

# The preflight sends mode-specific Authorization with TLS validation enabled.
from unittest.mock import MagicMock
from urllib.error import HTTPError
from io import BytesIO
with patch.object(manager, "system_trust_bundle", return_value=None):
    pass
with patch("urllib.request.urlopen") as urlopen:
    resp = MagicMock()
    resp.status = 200
    resp.__enter__.return_value = resp
    urlopen.return_value = resp
    assert manager.jira_preflight(basic) == 200
    request = urlopen.call_args.args[0]
    assert request.get_header("Authorization").startswith("Basic ")
with patch("urllib.request.urlopen", side_effect=HTTPError(
    "https://jira.example.test/jira/rest/api/2/myself", 401, "Unauthorized", {}, BytesIO()
)):
    assert manager.jira_preflight(pat) == 401
print("Jira preflight: PASS")
