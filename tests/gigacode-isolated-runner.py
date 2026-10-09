#!/usr/bin/env python3
"""Isolated Harr/GigaCode streaming smoke. Does not modify active Harr/LeanCTX."""
import os, subprocess, sys, tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
# Explicit external build; do not use or overwrite the production LeanCTX binary.
binary=Path(os.environ.get("HARR_LEANCTX_TEST_BINARY", str(root/"_leanctx_fix/rust/target/debug/lean-ctx"))).resolve()
bridge=root/"common/mcp/gigacode_server.py"
smoke=root/"tests/gigacode-live-stream-smoke.py"
source=Path.home()/".config/lean-ctx/config.toml"
if not binary.is_file() or not bridge.is_file() or not source.is_file():
    raise SystemExit("missing dev binary, bridge or baseline config")
with tempfile.TemporaryDirectory(prefix="harr-gigacode-isolated-") as tmp:
    work=Path(tmp)
    cfg=work/"config/lean-ctx"
    cfg.mkdir(parents=True)
    original=source.read_text()
    config=original.split("[[gateway.servers]]")[0]
    config += f"""
[[gateway.servers]]
name = "gigacode"
transport = "stdio"
enabled = true
command = "python3"
args = ["{bridge}"]
url = ""
[gateway.servers.env]
[gateway.servers.headers]
"""
    (cfg/"config.toml").write_text(config)
    env=os.environ.copy()
    env.update({
        "XDG_CONFIG_HOME":str(work/"config"),
        "XDG_CACHE_HOME":str(work/"cache"),
        "XDG_DATA_HOME":str(work/"data"),
        "XDG_STATE_HOME":str(work/"state"),
        "LEANCTX_SMOKE_BINARY":str(binary),
        "LEANCTX_SMOKE_STDERR":str(work/"leanctx-stderr.log"),
    })
    result=subprocess.run([sys.executable,str(smoke)],cwd=root,env=env,timeout=300)
    print(f"isolated_smoke_exit={result.returncode}",flush=True)
    sys.exit(result.returncode)
