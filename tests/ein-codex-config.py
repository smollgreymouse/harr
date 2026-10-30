#!/usr/bin/env python3
"""Codex direct Ein MCP reconciliation preserves ownership and nested TOML."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import tomllib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="harr-ein-codex-config-") as raw:
    home = Path(raw) / "home"
    config_root = home / ".config" / "harr"
    codex_home = home / ".codex"
    config_root.mkdir(parents=True)
    codex_home.mkdir(parents=True)
    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "HARR_CONFIG_DIR": str(config_root),
        "CODEX_HOME": str(codex_home),
    }
    with patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location(
            "harr_codex_config_contract", ROOT / "common/hosts/codex-config.py"
        )
        assert spec and spec.loader
        codex = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(codex)
        from common.mcp import ein_instances

        codex.CONFIG = codex_home / "config.toml"
        codex.CONFIG.write_text(
            '[mcp_servers.external]\ncommand = "external"\n'
            '[mcp_servers.external.nested]\nvalue = "keep"\n',
            encoding="utf-8",
        )

        enabled = {"instances": [{"id": "review", "enabled": True}]}
        disabled = {"instances": [{"id": "review", "enabled": False}]}
        with patch.object(ein_instances, "read", return_value=enabled):
            codex.apply_named_ein_apps()
        parsed = tomllib.loads(codex.CONFIG.read_text(encoding="utf-8"))
        servers = parsed["mcp_servers"]
        assert set(servers) == {"external", "review", "harr-ein-ui"}, servers
        direct = servers["review"]
        assert direct["args"] == [str(codex.ein_direct_path()), "review"]
        assert direct["env"]["HARR_EIN_DIRECT_MANAGED"] == "1"
        assert servers["external"]["nested"]["value"] == "keep"

        # Exact managed ownership permits removal of the complete TOML subtree,
        # including nested tables outside the generated schema.
        text = codex.CONFIG.read_text(encoding="utf-8")
        text += '\n[mcp_servers.review.tools.user_extension]\nvalue = "owned subtree"\n'
        codex.CONFIG.write_text(text, encoding="utf-8")
        with patch.object(ein_instances, "read", return_value=enabled):
            codex.apply_named_ein_apps()
        assert "[mcp_servers.review.tools.user_extension]" not in codex.CONFIG.read_text(encoding="utf-8")

        with patch.object(ein_instances, "read", return_value=disabled):
            codex.apply_named_ein_apps()
        parsed = tomllib.loads(codex.CONFIG.read_text(encoding="utf-8"))
        assert set(parsed["mcp_servers"]) == {"external"}, parsed

        # A user-owned server that collides with a configured Ein must fail
        # closed and leave the full source text byte-for-byte unchanged.
        codex.CONFIG.write_text(
            '[mcp_servers.review]\ncommand = "my-server"\nargs = ["custom"]\n'
            '[mcp_servers.review.extra]\nvalue = "untouched"\n',
            encoding="utf-8",
        )
        before = codex.CONFIG.read_text(encoding="utf-8")
        try:
            with patch.object(ein_instances, "read", return_value=enabled):
                codex.apply_named_ein_apps()
        except RuntimeError as exc:
            assert "collision" in str(exc)
        else:
            raise AssertionError("same-named user MCP collision was accepted")
        assert codex.CONFIG.read_text(encoding="utf-8") == before

        # The shared panel is also a reserved user namespace and is never
        # replaced or removed when another server already owns its name.
        codex.CONFIG.write_text(
            '[mcp_servers.harr-ein-ui]\ncommand = "my-panel"\nargs = ["custom"]\n'
            '[mcp_servers.harr-ein-ui.extra]\nvalue = "untouched"\n',
            encoding="utf-8",
        )
        before = codex.CONFIG.read_text(encoding="utf-8")
        try:
            with patch.object(ein_instances, "read", return_value=enabled):
                codex.apply_named_ein_apps()
        except RuntimeError as exc:
            assert "harr-ein-ui" in str(exc)
        else:
            raise AssertionError("same-named panel collision was accepted")
        assert codex.CONFIG.read_text(encoding="utf-8") == before

print("Codex named Ein config reconciliation: PASS")
