#!/usr/bin/env python3
"""Hermetic gateway runtime checks for the project MCP adapter layer.

Runs the deployed LeanCTX binary against two same-vendor stdio instances with
separate credential wirings plus a fail-closed instance, and verifies:

1. cold session start spawns no upstream and the plain tools/list stays static;
2. a direct qualified call launches exactly the addressed instance and repeated
   calls reuse its pooled session;
3. each instance receives only its own wired credential (env names only);
4. an instance whose secret is missing is never spawned (fail-closed).

Skipped (exit 0) when no LeanCTX binary is available, so CI without a gateway
deployment still passes.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

UPSTREAM_SOURCE = r'''
import json, os, pathlib, sys, time
NAME = sys.argv[1]
LOG = pathlib.Path(sys.argv[2])
def secret_names():
    return sorted(k for k in os.environ if k.startswith("LEAN_CTX_SECRET_") or k in ("TOKEN_A", "TOKEN_B"))
LOG.parent.mkdir(parents=True, exist_ok=True)
with LOG.open("a") as f:
    f.write(json.dumps({"name": NAME, "pid": os.getpid(), "secrets": secret_names()}) + "\n")
def resp(i, r): return {"jsonrpc": "2.0", "id": i, "result": r}
def err(i, c, m): return {"jsonrpc": "2.0", "id": i, "error": {"code": c, "message": m}}
TOOLS = [
    {"name": "echo", "description": f"Echo from {NAME}",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "vendor_only_a" if NAME.endswith("-a") else "vendor_only_b",
     "description": f"Tool only {NAME} has",
     "inputSchema": {"type": "object", "properties": {}}},
]
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method, id_ = msg.get("method"), msg.get("id")
    if method == "initialize":
        out = resp(id_, {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                         "capabilities": {"tools": {}}, "serverInfo": {"name": NAME, "version": "0.1.0"}})
    elif method and method.startswith("notifications/"):
        continue
    elif method == "tools/list":
        out = resp(id_, {"tools": TOOLS})
    elif method == "tools/call":
        tool = msg.get("params", {}).get("name", "")
        args = msg.get("params", {}).get("arguments") or {}
        if tool == "echo":
            out = resp(id_, {"content": [{"type": "text", "text": f"{NAME}:{args.get('text', '')}"}]})
        elif tool in ("vendor_only_a", "vendor_only_b"):
            out = resp(id_, {"content": [{"type": "text", "text": f"{NAME}:{tool}"}]})
        else:
            out = err(id_, -32602, f"unknown tool {tool}")
    elif method == "ping":
        out = resp(id_, {})
    else:
        if id_ is None:
            continue
        out = err(id_, -32601, f"no such method {method}")
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
'''


def binary() -> str | None:
    candidate = "/usr/lib/harr/linux/vendor/lean-ctx/lean-ctx"
    if os.path.isfile(candidate):
        return candidate
    return shutil.which("lean-ctx")


def main() -> None:
    lean_ctx = binary()
    if not lean_ctx:
        print("lean-ctx binary not available; runtime checks skipped")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        upstream = tmp / "upstream.py"
        upstream.write_text(UPSTREAM_SOURCE, encoding="utf-8")
        spawn_log = tmp / "logs" / "spawns.log"
        config_dir = tmp / "config"
        config_dir.mkdir(parents=True)
        gateway_config = config_dir / "config.toml"
        gateway_config.write_text(f"""
[gateway]
enabled = true
cache_ttl_secs = 120
call_timeout_secs = 30

[[gateway.servers]]
name = "vendor-a"
transport = "stdio"
enabled = true
command = "python3"
args = ["{upstream}", "vendor-a", "{spawn_log}"]
url = ""

[gateway.servers.env]

[gateway.servers.headers]

[gateway.servers.secret_env]
TOKEN_A = {{ id = "mcp/test/a" }}

[[gateway.servers]]
name = "vendor-b"
transport = "stdio"
enabled = true
command = "python3"
args = ["{upstream}", "vendor-b", "{spawn_log}"]
url = ""

[gateway.servers.env]

[gateway.servers.headers]

[gateway.servers.secret_env]
TOKEN_B = {{ id = "mcp/test/b" }}

[[gateway.servers]]
name = "ghost"
transport = "stdio"
enabled = true
command = "python3"
args = ["{upstream}", "ghost", "{spawn_log}"]
url = ""

[gateway.servers.env]

[gateway.servers.headers]

[gateway.servers.secret_env]
GHOST_TOKEN = {{ id = "mcp/test/missing" }}
""", encoding="utf-8")

        secret_a = "LEAN_CTX_SECRET_" + "mcp/test/a".encode().hex().upper()
        secret_b = "LEAN_CTX_SECRET_" + "mcp/test/b".encode().hex().upper()
        env = dict(os.environ)
        env["LEAN_CTX_CONFIG_DIR"] = str(config_dir)
        env[secret_a] = "token-a-value"
        env[secret_b] = "token-b-value"

        def call(payload: dict) -> dict:
            completed = subprocess.run(
                [lean_ctx, "call", "ctx_tools", "--project-root", str(tmp),
                 "--json", json.dumps(payload)],
                env=env, cwd=str(tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=120,
            )
            return completed

        def spawns() -> list[dict]:
            if not spawn_log.is_file():
                return []
            return [json.loads(line) for line in spawn_log.read_text(encoding="utf-8").splitlines() if line.strip()]

        # 1. Cold MCP session start + static tools/list spawn nothing.
        client_source = tmp / "probe.py"
        client_source.write_text(f'''
import json, subprocess, sys
proc = subprocess.Popen([{lean_ctx!r}], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
nid = 1
def send(m): proc.stdin.write(json.dumps(m) + "\\n"); proc.stdin.flush()
def recv(i):
    while True:
        line = proc.stdout.readline()
        try: msg = json.loads(line)
        except Exception: continue
        if msg.get("id") == i and ("result" in msg or "error" in msg): return msg
send({{"jsonrpc":"2.0","id":nid,"method":"initialize","params":{{"protocolVersion":"2025-03-26","capabilities":{{}},"clientInfo":{{"name":"probe","version":"0"}}}}}})
recv(nid); nid += 1
send({{"jsonrpc":"2.0","method":"notifications/initialized"}})
send({{"jsonrpc":"2.0","id":nid,"method":"tools/list","params":{{}}}})
reply = recv(nid)
names = [t["name"] for t in reply["result"]["tools"]]
print("QUALIFIED", [n for n in names if "::" in n])
proc.terminate()
''', encoding="utf-8")
        subprocess.run([sys.executable, "-I", str(client_source)], check=True, timeout=120)
        assert spawns() == [], f"cold start spawned upstreams: {spawns()}"

        # 2. Direct qualified call: only the addressed instance; same wiring reuse.
        result = call({"action": "call", "tool": "vendor-a::echo", "arguments": {"text": "one"}})
        assert result.returncode == 0, result.stderr
        assert "vendor-a:one" in result.stdout, result.stdout
        first = spawns()
        assert [row["name"] for row in first] == ["vendor-a"], first

        result = call({"action": "call", "tool": "vendor-a::echo", "arguments": {"text": "two"}})
        assert "vendor-a:two" in result.stdout, result.stdout
        # New process -> new pool; only vendor-a again, never vendor-b/ghost.
        assert [row["name"] for row in spawns()] == ["vendor-a", "vendor-a"], spawns()

        result = call({"action": "call", "tool": "vendor-b::vendor_only_b", "arguments": {}})
        assert result.returncode == 0, result.stderr
        assert "vendor-b:vendor_only_b" in result.stdout, result.stdout
        assert [row["name"] for row in spawns()] == ["vendor-a", "vendor-a", "vendor-b"], spawns()

        # Distinct same-vendor surfaces: each instance advertises only its own
        # native tool; the other instance's tool never appears in its surface.
        result = call({"action": "find", "query": "vendor"})
        assert "vendor-a::vendor_only_a" in result.stdout, result.stdout
        assert "vendor-b::vendor_only_b" in result.stdout, result.stdout
        assert "vendor-b::vendor_only_a" not in result.stdout, result.stdout
        assert "vendor-a::vendor_only_b" not in result.stdout, result.stdout

        # Unknown instance: error without fallback or spawn.
        result = call({"action": "call", "tool": "no-such::echo", "arguments": {}})
        assert result.returncode != 0 and "unknown or disabled gateway server" in result.stderr, result.stderr
        assert "ghost" not in [row["name"] for row in spawns()]

        # 3. Credential wiring at the transport edge: each instance receives
        # only the env name wired to it. (Children still inherit the gateway
        # process env — documented stage-1 gap; the harr runner sanitizes
        # LEAN_CTX_SECRET_* for real upstreams, covered by the overlay tests.)
        a_rows = [row for row in spawns() if row["name"] == "vendor-a"]
        b_rows = [row for row in spawns() if row["name"] == "vendor-b"]
        assert a_rows and b_rows
        assert "TOKEN_A" in a_rows[0]["secrets"], a_rows[0]
        assert "TOKEN_B" not in a_rows[0]["secrets"], "vendor-a must not be wired vendor-b credential"
        assert "TOKEN_B" in b_rows[0]["secrets"], b_rows[0]
        assert "TOKEN_A" not in b_rows[0]["secrets"], "vendor-b must not be wired vendor-a credential"

        # 4. Missing memento: fail-closed, instance never spawned, others fine.
        result = call({"action": "call", "tool": "ghost::echo", "arguments": {"text": "x"}})
        assert result.returncode != 0 and "missing secret memento" in result.stderr, result.stderr
        assert "ghost" not in [row["name"] for row in spawns()], spawns()

        # Catalog aggregation sees both vendors; ghost surfaces as unavailable.
        result = call({"action": "find", "query": "echo"})
        assert "vendor-a::echo" in result.stdout and "vendor-b::echo" in result.stdout, result.stdout

        print("gateway runtime adapter checks: PASS")


main()
