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
assert set(("codegraph", "gitlab", "grafana", "elasticsearch")) <= set(servers)

grafana = servers["grafana"]
assert grafana["transport"] == "http"
assert grafana["lifecycle"] == "service"
assert grafana["url"] == "http://127.0.0.1:3335/mcp"
assert grafana["runtime"] == {
    "kind": "uvx",
    "package": "mcp-grafana",
    "command": "uvx",
    "args": ["mcp-grafana", "--transport", "streamable-http", "--address", "127.0.0.1:3335"],
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

elasticsearch = servers["elasticsearch"]
assert elasticsearch["transport"] == "stdio"
assert elasticsearch["lifecycle"] == "on-demand"
assert elasticsearch["runtime"] == {
    "kind": "path",
    "command": "docker",
    "args": [
        "run", "-i", "--rm",
        "-e", "ES_URL",
        "-e", "ES_API_KEY",
        "docker.elastic.co/mcp/elasticsearch:0.4.6",
        "stdio",
    ],
    "prefetch_args": ["pull", "docker.elastic.co/mcp/elasticsearch:0.4.6"],
    "install_hint": "Docker is required for Elasticsearch MCP; install Docker and run `harr install mcp`",
}
assert elasticsearch["secrets"] == [
    {
        "name": "elasticsearch",
        "file": "elasticsearch-api-key",
        "prompt": "Elasticsearch API key",
        "memento_id": "mcp/elasticsearch/default",
        "target": {"kind": "env", "name": "ES_API_KEY"},
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
        assert item["transport"] == "http"
        assert item["url"] == "http://127.0.0.1:3335/mcp"
        assert "secret_env" not in item
        assert "secret_headers" not in item

        item = rendered["elasticsearch"]
        assert item["transport"] == "stdio"
        assert item["command"] == "harr-mcp-run"
        assert item["args"] == ["elasticsearch"]
        assert item["secret_env"]["ES_API_KEY"] == {"id": "mcp/elasticsearch/default"}
        assert "secret_headers" not in item

with tempfile.TemporaryDirectory() as tmp:
    target = Path(tmp)
    args = type("Args", (), {"config_dir": str(target)})()
    manager.install_configs(args, manager.load_registry(REGISTRY_PATH))
    grafana_env = (target / "grafana.env").read_text(encoding="utf-8")
    assert "GRAFANA_URL=http://localhost:3000" in grafana_env
    assert "GRAFANA_SERVICE_ACCOUNT_TOKEN=" not in grafana_env
    elasticsearch_env = (target / "elasticsearch.env").read_text(encoding="utf-8")
    assert "ES_URL=https://elasticsearch.example.com:9200" in elasticsearch_env
    assert "ES_API_KEY=" not in elasticsearch_env

assert manager.memento_var("mcp/grafana/default") == "LEAN_CTX_SECRET_6D63702F67726166616E612F64656661756C74"
assert manager.memento_var("mcp/elasticsearch/default") == "LEAN_CTX_SECRET_6D63702F656C61737469637365617263682F64656661756C74"

with patch.object(manager.shutil, "which", side_effect=lambda command: f"/tmp/{command}"):
    grafana_command = manager.runtime_command(grafana)
    assert grafana_command == ["/tmp/uvx", "mcp-grafana", "--transport", "streamable-http", "--address", "127.0.0.1:3335"]
    assert manager.runtime_maintenance_command(grafana, "prefetch_args") == ["/tmp/uvx", "mcp-grafana", "--version"]
    assert manager.runtime_maintenance_command(grafana, "probe_args") == ["/tmp/uvx", "--offline", "mcp-grafana", "--version"]

    elasticsearch_command = manager.runtime_command(elasticsearch)
    assert elasticsearch_command == [
        "/tmp/docker",
        "run", "-i", "--rm",
        "-e", "ES_URL",
        "-e", "ES_API_KEY",
        "docker.elastic.co/mcp/elasticsearch:0.4.6",
        "stdio",
    ]
    assert manager.runtime_maintenance_command(elasticsearch, "prefetch_args") == [
        "/tmp/docker", "pull", "docker.elastic.co/mcp/elasticsearch:0.4.6"
    ]

with tempfile.TemporaryDirectory() as tmp:
    secret_dir = Path(tmp) / "secrets"
    secret_dir.mkdir()
    (secret_dir / "grafana-service-account-token").write_text("token-value\n", encoding="utf-8")
    (secret_dir / "elasticsearch-api-key").write_text("elastic-value\n", encoding="utf-8")
    with patch.dict(manager.os.environ, {"HARR_CONFIG_DIR": tmp}):
        assert manager.service_secret_env(grafana) == {"GRAFANA_SERVICE_ACCOUNT_TOKEN": "token-value"}
        assert manager.service_secret_env(elasticsearch) == {"ES_API_KEY": "elastic-value"}

print("cross-platform MCP registry: PASS")
