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
assert set(("codegraph", "gitlab", "grafana", "kibana")) <= set(servers)
assert not {"gigacode", "einherjar"}.intersection(servers)

# The compatibility app source remains available to tests/migration code, but
# must never survive in the installed shared runtime on any supported OS.
linux_install = (ROOT / "linux/install.sh").read_text(encoding="utf-8")
macos_install = (ROOT / "macos/install.sh").read_text(encoding="utf-8")
windows_install = (ROOT / "windows/install.ps1").read_text(encoding="utf-8")
assert 'mcp/gigacode_app' in linux_install and 'rm -rf' in linux_install
assert 'mcp/gigacode_app' in macos_install and 'rm -rf' in macos_install
assert 'gigacode_app' in windows_install and 'Remove-Item' in windows_install

grafana = servers["grafana"]
assert grafana["transport"] == "stdio"
assert grafana["lifecycle"] == "on-demand"
assert "url" not in grafana
assert grafana["runtime"] == {
    "kind": "uvx",
    "package": "mcp-grafana",
    "command": "uvx",
    "args": ["--offline", "mcp-grafana", "--transport", "stdio"],
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

gitlab = servers["gitlab"]
assert gitlab["transport"] == "stdio"
assert gitlab["lifecycle"] == "on-demand"
assert "url" not in gitlab
assert gitlab["runtime"] == {
    "kind": "npm",
    "package": "@zereight/mcp-gitlab",
    "version": "2.1.48",
    "command": "zereight-mcp-gitlab",
    "args": [],
    "env": {
        "STREAMABLE_HTTP": "false",
        "SSE": "false",
        "REMOTE_AUTHORIZATION": "false",
    },
}
assert gitlab["secrets"] == [
    {
        "name": "gitlab",
        "file": "gitlab-pat",
        "prompt": "GitLab PAT",
        "memento_id": "mcp/gitlab/default",
        "target": {"kind": "env", "name": "GITLAB_PERSONAL_ACCESS_TOKEN"},
    }
]
assert "windows_task" not in gitlab

kibana = servers["kibana"]
assert kibana["transport"] == "stdio"
assert kibana["lifecycle"] == "on-demand"
assert kibana["runtime"]["kind"] == "uvx"
assert kibana["runtime"]["package"] == "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f"
assert kibana["runtime"]["version"] == "0.7.7 fork 73cb2aa"
assert kibana["runtime"]["args"] == ["--offline", "--from", "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f", "kibana-agent", "mcp"]
assert kibana["runtime"]["prefetch_args"] == ["--from", "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f", "kibana-agent", "--version"]
assert kibana["runtime"]["probe_args"] == ["--offline", "--from", "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f", "kibana-agent", "--version"]
assert kibana["secrets"] == [{"name":"kibana","file":"kibana-api-key","prompt":"Kibana API key","memento_id":"mcp/kibana/default","target":{"kind":"env","name":"KIBANA_API_KEY"}}]

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
        grafana_rendered = rendered["grafana"]
        assert grafana_rendered["transport"] == "stdio"
        assert grafana_rendered["command"] == "harr-mcp-run"
        assert grafana_rendered["args"] == ["grafana"]
        assert "secret_env" in grafana_rendered
        assert grafana_rendered["secret_env"]["GRAFANA_SERVICE_ACCOUNT_TOKEN"] == {"id": "mcp/grafana/default"}

        gitlab_rendered = rendered["gitlab"]
        assert gitlab_rendered["transport"] == "stdio"
        assert gitlab_rendered["command"] == "harr-mcp-run"
        assert gitlab_rendered["args"] == ["gitlab"]
        assert "secret_env" in gitlab_rendered
        assert gitlab_rendered["secret_env"]["GITLAB_PERSONAL_ACCESS_TOKEN"] == {"id": "mcp/gitlab/default"}

        kibana_rendered = rendered["kibana"]
        assert kibana_rendered["transport"] == "stdio"
        assert kibana_rendered["command"] == "harr-mcp-run"
        assert kibana_rendered["args"] == ["kibana"]
        assert kibana_rendered["secret_env"]["KIBANA_API_KEY"] == {"id": "mcp/kibana/default"}

        assert not {"gigacode", "einherjar"}.intersection(rendered)

with tempfile.TemporaryDirectory() as tmp:
    target = Path(tmp)
    args = type("Args", (), {"config_dir": str(target)})()
    manager.install_configs(args, manager.load_registry(REGISTRY_PATH))
    grafana_env = (target / "grafana.env").read_text(encoding="utf-8")
    assert "GRAFANA_URL=http://localhost:3000" in grafana_env
    assert "GRAFANA_SERVICE_ACCOUNT_TOKEN=" not in grafana_env
    gitlab_env = (target / "gitlab.env").read_text(encoding="utf-8")
    assert "GITLAB_API_URL" in gitlab_env
    assert "GITLAB_PERSONAL_ACCESS_TOKEN=" not in gitlab_env
    kibana_env = (target / "kibana.env").read_text(encoding="utf-8")
    assert "KIBANA_URL=https://kibana.example.com" in kibana_env
    assert "KIBANA_API_KEY=" not in kibana_env

assert manager.memento_var("mcp/grafana/default") == "LEAN_CTX_SECRET_6D63702F67726166616E612F64656661756C74"
assert manager.memento_var("mcp/kibana/default") == "LEAN_CTX_SECRET_6D63702F6B6962616E612F64656661756C74"
with patch.object(manager.shutil, "which", return_value="/tmp/uvx"):
    grafana_command = manager.runtime_command(grafana)
    assert grafana_command == ["/tmp/uvx", "--offline", "mcp-grafana", "--transport", "stdio"]
    assert manager.runtime_maintenance_command(grafana, "prefetch_args") == ["/tmp/uvx", "mcp-grafana", "--version"]
    assert manager.runtime_maintenance_command(grafana, "probe_args") == ["/tmp/uvx", "--offline", "mcp-grafana", "--version"]
with patch.object(manager.shutil, "which", return_value="/tmp/uvx"):
    assert manager.runtime_command(kibana) == ["/tmp/uvx", "--offline", "--from", "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f", "kibana-agent", "mcp"]
    assert manager.runtime_maintenance_command(kibana, "prefetch_args") == ["/tmp/uvx", "--from", "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f", "kibana-agent", "--version"]
    assert manager.runtime_maintenance_command(kibana, "probe_args") == ["/tmp/uvx", "--offline", "--from", "git+https://github.com/smollgreymouse/kibana-agent.git@73cb2aa03462c44616601d5299515ff45ed36d7f", "kibana-agent", "--version"]

# Executor instances are user-configured and expanded into the effective
# registry; neither the retired singleton nor the generic worker is cataloged.

with tempfile.TemporaryDirectory() as tmp:
    secret_dir = Path(tmp) / "secrets"
    secret_dir.mkdir()
    (secret_dir / "grafana-service-account-token").write_text("token-value\n", encoding="utf-8")
    (secret_dir / "gitlab-pat").write_text("pat-value\n", encoding="utf-8")
    (secret_dir / "kibana-api-key").write_text("kibana-value\n", encoding="utf-8")
    with patch.dict(manager.os.environ, {"HARR_CONFIG_DIR": tmp}):
        assert manager.service_secret_env(grafana) == {"GRAFANA_SERVICE_ACCOUNT_TOKEN": "token-value"}
        assert manager.service_secret_env(gitlab) == {"GITLAB_PERSONAL_ACCESS_TOKEN": "pat-value"}
        assert manager.service_secret_env(kibana) == {"KIBANA_API_KEY": "kibana-value"}
        assert manager.runtime_env(gitlab) == {"STREAMABLE_HTTP": "false", "SSE": "false", "REMOTE_AUTHORIZATION": "false"}
        assert manager.runtime_env(grafana) == {}

# Regression: runtime.env must override legacy STREAMABLE_HTTP=true from user .env
# but secret values must never be overridden by runtime.env.
with tempfile.TemporaryDirectory() as tmp:
    config_dir = Path(tmp) / "harr"
    mcp_dir = config_dir / "mcp"
    mcp_dir.mkdir(parents=True)
    secrets_dir = config_dir / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "gitlab-pat").write_text("secret-token\n", encoding="utf-8")
    # Simulate a preserved legacy env with STREAMABLE_HTTP=true
    (mcp_dir / "gitlab.env").write_text(
        "STREAMABLE_HTTP=true\nGITLAB_API_URL=https://gitlab.example.com/api/v4\n", encoding="utf-8"
    )
    effective = {"schema": 1, "servers": [gitlab]}
    eff_path = Path(tmp) / "effective.json"
    eff_path.write_text(json.dumps(effective), encoding="utf-8")
    eff_data = manager.load_registry(eff_path)
    server = manager.server_by_name(eff_data, "gitlab")
    forbidden = {
        secret.get("target", {}).get("name")
        for secret in server.get("secrets", [])
        if secret.get("target", {}).get("kind") == "env"
    }
    forbidden.discard(None)
    env_path = mcp_dir / "gitlab.env"
    env = {}
    env.update(manager.load_env_file(env_path, forbidden))
    env.update(manager.runtime_env(server))
    with patch.dict(manager.os.environ, {"HARR_CONFIG_DIR": str(config_dir)}):
        env.update(manager.service_secret_env(server))
    # runtime.env STREAMABLE_HTTP=false must override the legacy env's STREAMABLE_HTTP=true
    assert env["STREAMABLE_HTTP"] == "false", f"expected false, got {env['STREAMABLE_HTTP']}"
    assert env["GITLAB_API_URL"] == "https://gitlab.example.com/api/v4"
    assert env["GITLAB_PERSONAL_ACCESS_TOKEN"] == "secret-token"
    assert env["SSE"] == "false"
    assert env["REMOTE_AUTHORIZATION"] == "false"

# runtime.env with a secret target key must be rejected.
with tempfile.TemporaryDirectory() as tmp:
    bad_gitlab = dict(gitlab)
    bad_gitlab["runtime"] = dict(gitlab["runtime"])
    bad_gitlab["runtime"]["env"] = {"STREAMABLE_HTTP": "false", "GITLAB_PERSONAL_ACCESS_TOKEN": "leaked"}
    bad_eff = {"schema": 1, "servers": [bad_gitlab]}
    try:
        manager.runtime_env(bad_gitlab)
        assert False, "expected SystemExit for secret in runtime.env"
    except SystemExit as e:
        assert "GITLAB_PERSONAL_ACCESS_TOKEN" in str(e)

print("cross-platform MCP registry: PASS")
