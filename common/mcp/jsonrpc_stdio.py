"""Configure Python's text wrappers for UTF-8 JSON-RPC over stdio."""

from __future__ import annotations

import sys


def configure_jsonrpc_stdio() -> None:
    """Make redirected MCP stdin/stdout use the protocol's UTF-8 encoding."""
    for name in ("stdin", "stdout"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
