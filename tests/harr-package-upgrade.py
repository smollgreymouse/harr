#!/usr/bin/env python3
"""Exercise source-to-deb setup and a subsequent package upgrade in an isolated HOME."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(args, env, *, check=True):
    result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=90)
    if check and result.returncode:
        raise AssertionError(f"{args}: exit {result.returncode}\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
    return result


def check_hosts(command, env):
    output = run([str(command), "hosts", "status"], env).stdout
    rows = {parts[0]: parts[1] for line in output.splitlines()[1:] if len(parts := line.split()) >= 2}
    assert rows == {"opencode": "managed", "codex": "managed"}, output
    # Doctor must use the invoking CLI and survive the libexec env it passes to children.
    result = run([str(command), "doctor", "--local", "--json"], env, check=False)
    if not result.stdout.startswith("{"):
        print("doctor exit:", result.returncode, flush=True)
        print("doctor stdout:", result.stdout, flush=True)
        print("doctor stderr:", result.stderr, flush=True)
        raise AssertionError("doctor did not return a JSON report")
    report = json.loads(result.stdout)
    host = next(item for item in report["checks"] if item["id"] == "host.codex")
    assert host["status"] == "PASS", host


with tempfile.TemporaryDirectory(prefix="harr-package-upgrade-") as td:
    tmp = Path(td)
    source = tmp / "source"
    source.mkdir()
    # Package only the known source inputs, never a developer's ignored worktrees or venv.
    for name in ("common", "linux"):
        shutil.copytree(ROOT / name, source / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("install.sh", "README.md", "harr.png"):
        shutil.copy2(ROOT / name, source / name)
    (source / "VERSION").write_text("0.0.1\n")

    home = tmp / "home"
    home.mkdir()
    fakebin = tmp / "bin"
    fakebin.mkdir()
    systemctl = fakebin / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 0\n")
    systemctl.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("HARR_", "LEAN_CTX_"))}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), CODEX_HOME=str(home / ".codex"),
               HARR_CODEX_DISABLE_CLI="1", PATH=f"{fakebin}:{home / '.local/bin'}:{env['PATH']}")

    # Start with a real standalone user installation, with config/secrets to preserve.
    run([str(source / "linux/install.sh"), "--clean", "--harr-only", "--mcp", "none"], env)
    local = home / ".local/bin/harr"
    # The fixture exercises CLI/host routing; no LeanCTX runtime is downloaded.
    leanctx = home / ".local/bin/lean-ctx"
    leanctx.write_text("#!/bin/sh\n# HARR_LEANCTX_WRAPPER=1\nexit 0\n")
    leanctx.chmod(0o755)
    assert run([str(local), "version"], env).stdout.strip() == "Harr 0.0.1"
    check_hosts(local, env)
    selection = home / ".config/harr/mcp-selection.json"
    selection_before = selection.read_bytes()
    secret = home / ".config/harr/secrets/preserve-me"
    secret.write_text("fixture-secret\n")
    secret.chmod(0o600)
    # Reproduce the retired app from the real machine, including child tables.
    config_path = home / ".codex/config.toml"
    with config_path.open("a") as config_file:
        config_file.write(
            '\n[mcp_servers.harr-gigacode-app]\ncommand = "/usr/bin/python3"\n'
            f'args = ["{home}/.local/libexec/harr/common/mcp/gigacode_app/server.py"]\n'
            '[mcp_servers.harr-gigacode-app.env]\nLEGACY_FIXTURE = "retired"\n'
            '[mcp_servers.harr-gigacode-app.tools.show_gigacode_live]\napproval_mode = "auto"\n'
        )

    output = tmp / "output"
    package_root = tmp / "package"
    arch = run(["dpkg", "--print-architecture"], env).stdout.strip()

    def install_package(version):
        (source / "VERSION").write_text(version + "\n")
        run(["cmake", f"-DHARR_SOURCE_DIR={source}", f"-DHARR_VERSION={version}", f"-DHARR_ARCH={arch}",
             f"-DHARR_OUTPUT_DIR={output}", f"-DHARR_TEMP_DIR={tmp / 'staging'}",
             "-P", str(ROOT / "packaging/package-harr.cmake")], env)
        run(["dpkg-deb", "-x", str(output / f"harr_{version}_{arch}.deb"), str(package_root)], env)

    install_package("0.0.2")
    package = package_root / "usr/bin/harr"
    assert not package.is_symlink(), "Exercise the actual shell entrypoint shipped by the deb"
    run([str(package), "setup", "--harr-only"], env)
    assert (home / ".local/libexec/harr/common").resolve() == package_root / "usr/lib/harr/common"
    assert (home / ".local/libexec/harr/cli").resolve() == package_root / "usr/lib/harr/linux/files/harr-cli"
    assert run(["harr", "version"], env).stdout.strip() == "Harr 0.0.2"
    check_hosts(local, env)
    assert selection.read_bytes() == selection_before
    assert secret.read_text() == "fixture-secret\n"
    assert secret.stat().st_mode & 0o777 == 0o600
    config = tomllib.loads(config_path.read_text())
    assert "harr-gigacode-app" not in config["mcp_servers"], config["mcp_servers"].keys()
    for agent_policy in (home / ".codex/AGENTS.md", home / ".config/opencode/AGENTS.md"):
        policy = agent_policy.read_text()
        assert policy.count("<!-- harr-tool-policy:start -->") == 1
        assert policy.count("<!-- harr-tool-policy:end -->") == 1
    expected_server = package_root / "usr/lib/harr/common/mcp/workspace_control/server.py"
    assert config["mcp_servers"]["harr-workspace"]["args"] == [str(expected_server)]
    config_before = config_path.read_bytes()

    # Upgrading the package must immediately update the CLI found through PATH,
    # without another setup and without making existing host registrations stale.
    install_package("0.0.3")
    assert run(["harr", "version"], env).stdout.strip() == "Harr 0.0.3"
    assert run([str(package), "version"], env).stdout.strip() == "Harr 0.0.3"
    check_hosts(local, env)
    assert config_path.read_bytes() == config_before
    assert selection.read_bytes() == selection_before
    assert secret.read_text() == "fixture-secret\n"

print("Harr source-to-package setup and package upgrade: PASS")
