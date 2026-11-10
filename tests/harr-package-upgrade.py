#!/usr/bin/env python3
"""Exercise source-to-deb setup and a subsequent package upgrade in an isolated HOME."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
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


def configure_packaged_leanctx(source: Path, fixture: Path, build: str, tag: str, sha: str) -> str:
    build_id = f"{tag}@{sha}"
    components = source / "linux/files/harr-cli/components.sh"
    text = components.read_text()
    text = re.sub(r'^readonly HARR_LEANCTX_BUILD="[^"]+"$', f'readonly HARR_LEANCTX_BUILD="{build}"', text, flags=re.M)
    text = re.sub(r'^readonly HARR_LEANCTX_ID="[^"]+"$', f'readonly HARR_LEANCTX_ID="{build_id}"', text, flags=re.M)
    text = re.sub(r'^readonly HARR_LEANCTX_RELEASE_TAG="[^"]+"$', f'readonly HARR_LEANCTX_RELEASE_TAG="{tag}"', text, flags=re.M)
    components.write_text(text)
    wrapper = source / "linux/files/leanctx/lean-ctx-wrapper"
    wrapper_text = re.sub(
        r'^readonly HARR_LEANCTX_BUILD="[^"]+"$',
        f'readonly HARR_LEANCTX_BUILD="{build}"',
        wrapper.read_text(),
        flags=re.M,
    )
    wrapper.write_text(wrapper_text)
    fixture.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = --version ]; then\n"
        f"  echo 'lean-ctx 3.11.0 (Harr build {build_id}, https://github.com/yvgude/lean-ctx)'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'fake packaged LeanCTX only supports --version' >&2\n"
        "exit 2\n"
    )
    fixture.chmod(0o755)
    return build_id


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
    bundled_leanctx = tmp / "lean-ctx-fixture"
    arch = run(["dpkg", "--print-architecture"], env).stdout.strip()

    def install_package(version):
        (source / "VERSION").write_text(version + "\n")
        run(["cmake", f"-DHARR_SOURCE_DIR={source}", f"-DHARR_VERSION={version}", f"-DHARR_ARCH={arch}",
             f"-DHARR_OUTPUT_DIR={output}", f"-DHARR_TEMP_DIR={tmp / 'staging'}",
             f"-DHARR_BUNDLED_LEANCTX={bundled_leanctx}",
             "-P", str(ROOT / "packaging/package-harr.cmake")], env)
        run(["dpkg-deb", "-x", str(output / f"harr_{version}_{arch}.deb"), str(package_root)], env)

    old_build = "3.11.0-harr-test.1"
    old_tag = "harr-v3.11.0-test.1"
    old_id = configure_packaged_leanctx(source, bundled_leanctx, old_build, old_tag, "111111111111")
    install_package("0.0.2")
    package = package_root / "usr/bin/harr"
    assert not package.is_symlink(), "Exercise the actual shell entrypoint shipped by the deb"

    # Merely installing/running the package before setup must not take over an
    # unrelated user LeanCTX. Auto-sync is migration-only for an existing
    # Harr-managed launcher.
    fresh_home = tmp / "fresh-home"
    fresh_bin = fresh_home / ".local/bin"
    fresh_bin.mkdir(parents=True)
    foreign_leanctx = fresh_bin / "lean-ctx"
    foreign_leanctx.write_text("#!/bin/sh\necho foreign-leanctx\n")
    foreign_leanctx.chmod(0o755)
    foreign_before = foreign_leanctx.read_bytes()
    fresh_env = dict(env)
    fresh_env.update(HOME=str(fresh_home), XDG_CONFIG_HOME=str(fresh_home / ".config"),
                     CODEX_HOME=str(fresh_home / ".codex"),
                     PATH=f"{fakebin}:{fresh_bin}:{env['PATH']}")
    assert run([str(package), "version"], fresh_env).stdout.strip() == "Harr 0.0.2"
    assert foreign_leanctx.read_bytes() == foreign_before
    assert not (fresh_home / ".local/libexec/harr/vendor/lean-ctx").exists()

    # A package upgrade may encounter only the old Harr-managed launcher before
    # any setup state is available in this HOME. The migration must produce a
    # self-contained package launcher whose --version path does not require the
    # MCP registry, and whose normal path points at the package-owned manager.
    migration_home = tmp / "migration-home"
    migration_bin = migration_home / ".local/bin"
    migration_bin.mkdir(parents=True)
    migration_launcher = migration_bin / "lean-ctx"
    migration_launcher.write_text("#!/bin/sh\n# HARR_LEANCTX_WRAPPER=1\nexit 99\n")
    migration_launcher.chmod(0o755)
    migration_env = dict(env)
    migration_env.update(HOME=str(migration_home), XDG_CONFIG_HOME=str(migration_home / ".config"),
                         CODEX_HOME=str(migration_home / ".codex"),
                         PATH=f"{fakebin}:{migration_bin}:{env['PATH']}")
    assert run([str(package), "version"], migration_env).stdout.strip() == "Harr 0.0.2"
    launcher_text = migration_launcher.read_text()
    assert "HARR_PACKAGE_LEANCTX_LAUNCHER=1" in launcher_text
    assert f"export HARR_MCP_MANAGER={package_root}/usr/lib/harr/common/mcp/manager.py" in launcher_text
    assert old_id in run([str(migration_launcher), "--version"], migration_env).stdout
    assert not (migration_home / ".config/harr/mcp-registry.json").exists()

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
    package_launcher = home / ".local/bin/lean-ctx"
    assert "HARR_PACKAGE_LEANCTX_LAUNCHER=1" in package_launcher.read_text()
    assert not (home / ".local/libexec/harr/leanctx/lean-ctx-wrapper").exists(), \
        "package setup retained the obsolete user-owned full wrapper"
    assert old_id in run([str(package_root / "usr/lib/harr/linux/vendor/lean-ctx/lean-ctx"), "--version"], env).stdout
    assert not (home / ".local/libexec/harr/vendor/lean-ctx" / old_build).exists(), \
        "package mode must not copy the Harr-owned LeanCTX binary into HOME"

    # Reproduce the pre-fix package state from a real Harr 0.3.7 installation:
    # a copied full wrapper plus a copied user-vendor binary. The next package
    # invocation must migrate only the launcher; the old binary may remain as
    # inert rollback/history data but must never be selected again.
    legacy_dir = home / ".local/libexec/harr/vendor/lean-ctx" / old_build
    legacy_dir.mkdir(parents=True)
    shutil.copy2(bundled_leanctx, legacy_dir / "lean-ctx")
    legacy_wrapper = package_root / "usr/lib/harr/linux/files/leanctx/lean-ctx-wrapper"
    shutil.copy2(legacy_wrapper, package_launcher)
    package_launcher.chmod(0o755)
    assert old_id in run([str(package_launcher), "--version"], env).stdout

    # Upgrading the package must immediately update the CLI found through PATH,
    # without another setup and without making existing host registrations stale.
    new_build = "3.11.0-harr-test.2"
    new_tag = "harr-v3.11.0-test.2"
    new_id = configure_packaged_leanctx(source, bundled_leanctx, new_build, new_tag, "222222222222")
    install_package("0.0.3")
    # The first Harr command after dpkg upgrade performs only the one-time
    # launcher migration. The package-owned LeanCTX binary is already current.
    assert run(["harr", "version"], env).stdout.strip() == "Harr 0.0.3"
    assert run([str(package), "version"], env).stdout.strip() == "Harr 0.0.3"
    assert "HARR_PACKAGE_LEANCTX_LAUNCHER=1" in package_launcher.read_text()
    launcher_version = run([str(package_launcher), "--version"], env).stdout.strip()
    assert new_id in launcher_version, launcher_version
    assert not (home / ".local/libexec/harr/vendor/lean-ctx" / new_build).exists(), \
        "package upgrade copied the new LeanCTX binary into HOME"
    status = run([str(package), "status"], env).stdout
    lean_line = next(line for line in status.splitlines() if line.lstrip().startswith("leanctx"))
    assert new_build in lean_line and "ok" in lean_line, lean_line
    check_hosts(local, env)
    assert config_path.read_bytes() == config_before
    assert selection.read_bytes() == selection_before
    assert secret.read_text() == "fixture-secret\n"

print("Harr source-to-package setup and package upgrade: PASS")
