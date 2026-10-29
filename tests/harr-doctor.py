#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harr_doctor", ROOT / "common" / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
assert spec.loader is not None
import sys
sys.modules[spec.name] = doctor
spec.loader.exec_module(doctor)

registry = json.loads((ROOT / "common" / "mcp" / "registry.json").read_text(encoding="utf-8"))
for server in registry["servers"]:
    doctor.validate_doctor_metadata(server)
    meta = server["doctor"]
    assert meta["repair"]["credential_auto_repair"] is False
    probe = meta["probe"]
    assert probe["kind"] in {"catalog-only", "mcp-ping", "tool"}
    if probe["kind"] == "tool":
        assert probe["tool"] in meta["required_tools"]

bad = {"name": "bad", "doctor": {"probe": {"kind": "tool", "tool": "destroy_all", "timeout_sec": 500}}}
try:
    doctor.validate_doctor_metadata(bad)
except ValueError:
    pass
else:
    raise AssertionError("invalid doctor metadata was accepted")

secret = "very-private-token-value"
redacted = doctor.redact_value(
    {"stderr": f"Authorization={secret}", "nested": [f"token={secret}", "safe"]},
    [secret],
)
dumped = json.dumps(redacted)
assert secret not in dumped
assert "<redacted>" in dumped

checks = [
    doctor.Check("leanctx.launcher", "core", "FAIL", "broken", repair="restore_launcher"),
    doctor.Check("host.codex", "codex", "FAIL", "stale", repair="apply_hosts"),
    doctor.Check("runtime.gitlab", "gitlab", "FAIL", "missing", repair="install_mcp"),
    doctor.Check("live.processes", "core", "WARN", "stale", repair="refresh_stale"),
]
effective = {
    "schema": 1,
    "servers": [
        {
            "name": "gitlab",
            "doctor": {"repair": {"runtime_reinstall": True, "credential_auto_repair": False}},
        }
    ],
}
without_manifest = doctor.plan_repairs(checks, manifest=None, stale_pids=[123], effective=effective)
by_id = {item.id: item for item in without_manifest}
assert by_id["restore_launcher"].status == "BLOCKED"
assert by_id["apply_hosts"].status == "PLANNED"
assert by_id["install_mcp"].status == "BLOCKED"
assert by_id["refresh_stale"].status == "BLOCKED"
assert by_id["refresh_stale"].evidence["pids"] == [123]

with_manifest = doctor.plan_repairs(checks, manifest={"schema": 1}, stale_pids=[123], effective=effective)
assert {item.id: item.status for item in with_manifest}["restore_launcher"] == "PLANNED"

ein_checks = [doctor.Check("runtime.worker", "worker", "FAIL", "missing", repair="install_mcp")]
ein_effective = {"schema": 1, "servers": [{"name": "worker", "ein_instance": "worker"}]}
ein_plan = doctor.plan_repairs(ein_checks, manifest={"schema": 1}, stale_pids=[], effective=ein_effective)
assert ein_plan[0].status == "BLOCKED"

skill = (ROOT / "common" / "skills" / "harr" / "SKILL.md").read_text(encoding="utf-8")
assert "Never run `harr doctor --repair` merely because doctor reports a failure." in skill
assert "explicitly asks to repair, restore, fix, recover" in skill
assert "harr doctor NAME" in skill

assert doctor.exit_code([doctor.Check("x", "core", "PASS", "ok")], strict=False) == 0
assert doctor.exit_code([doctor.Check("x", "core", "WARN", "warn")], strict=False) == 0
assert doctor.exit_code([doctor.Check("x", "core", "WARN", "warn")], strict=True) == 1
assert doctor.exit_code([doctor.Check("x", "core", "FAIL", "fail")], strict=False) == 1

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    home = root / "home"
    libexec = home / ".local" / "libexec" / "harr"
    wrapper_source = libexec / "leanctx" / "lean-ctx-wrapper"
    wrapper_source.parent.mkdir(parents=True)
    wrapper_source.write_text("#!/bin/sh\n# HARR_LEANCTX_WRAPPER=1\necho repaired\n", encoding="utf-8")
    launcher = home / ".local" / "bin" / "lean-ctx"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("not a wrapper\n", encoding="utf-8")
    paths = doctor.Paths(
        platform="linux",
        home=home,
        config_home=home / ".config",
        harr_config=home / ".config" / "harr",
        libexec=libexec,
        common=libexec / "common",
        bin_dir=launcher.parent,
        leanctx=launcher,
        lean_config=home / ".config" / "lean-ctx" / "config.toml",
        effective=home / ".config" / "harr" / "mcp-registry.json",
        catalog=libexec / "common" / "mcp" / "registry.json",
        secrets=home / ".config" / "harr" / "secrets",
        npm_prefix=home / ".local" / "share" / "harr" / "npm",
        runner=home / ".local" / "bin" / "harr-mcp-run",
        manifest=libexec / "install-manifest.json",
        repair_root=home / ".local" / "share" / "harr" / "doctor-repairs",
        codex_home=home / ".codex",
        opencode_home=home / ".config" / "opencode",
        harr_command=home / ".local" / "bin" / "harr",
    )
    manifest = {
        "schema": 1,
        "managed_files": {
            "leanctx_wrapper_source": {
                "sha256": doctor.sha256_file(wrapper_source),
            }
        },
    }
    action = doctor.RepairAction(
        "restore_launcher",
        ["leanctx.launcher"],
        "R1",
        "restore wrapper",
    )
    repaired, snapshot, journal = doctor.execute_repairs(paths, [action], manifest)
    assert repaired[0].status == "REPAIRED"
    assert "HARR_LEANCTX_WRAPPER=1" in launcher.read_text(encoding="utf-8")
    assert snapshot is not None and journal is not None
    doctor.restore_snapshot(snapshot, journal)
    assert launcher.read_text(encoding="utf-8") == "not a wrapper\n"


# Legacy effective registries predate doctor metadata; the installed catalog
# must supply probe/required-tool policy without mutating the registry.
legacy = doctor.overlay_doctor_metadata(
    [{"name": "gitlab", "runtime": {"kind": "npm"}}],
    {"servers": [{"name": "gitlab", "doctor": {"required_tools": ["health_check"], "probe": {"kind": "catalog-only"}}}]},
)
assert legacy[0]["doctor"]["required_tools"] == ["health_check"]

# Mandatory regression: a raw ELF/unmanaged launcher is restored from the
# exact wrapper source recorded by provenance, and the safety snapshot can
# restore the pre-repair bytes.
import os
import tempfile
from types import SimpleNamespace

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    home = root / "home"
    libexec = home / ".local" / "libexec" / "harr"
    paths = doctor.Paths(
        platform="linux",
        home=home,
        config_home=home / ".config",
        harr_config=home / ".config" / "harr",
        libexec=libexec,
        common=ROOT / "common",
        bin_dir=home / ".local" / "bin",
        leanctx=home / ".local" / "bin" / "lean-ctx",
        lean_config=home / ".config" / "lean-ctx" / "config.toml",
        effective=home / ".config" / "harr" / "mcp-registry.json",
        catalog=ROOT / "common" / "mcp" / "registry.json",
        secrets=home / ".config" / "harr" / "secrets",
        npm_prefix=home / ".local" / "share" / "harr" / "npm",
        runner=home / ".local" / "bin" / "harr-mcp-run",
        manifest=libexec / "install-manifest.json",
        repair_root=home / ".local" / "share" / "harr" / "doctor-repairs",
        codex_home=home / ".codex",
        opencode_home=home / ".config" / "opencode",
        harr_command=home / ".local" / "bin" / "harr",
    )
    wrapper = libexec / "leanctx" / "lean-ctx-wrapper"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text("#!/usr/bin/env bash\n# HARR_LEANCTX_WRAPPER=1\n", encoding="utf-8")
    wrapper.chmod(0o755)
    paths.leanctx.parent.mkdir(parents=True, exist_ok=True)
    original = b"\\x7fELFraw-unmanaged-launcher"
    paths.leanctx.write_bytes(original)
    manifest = {
        "schema": 1,
        "managed_files": {
            "leanctx_wrapper_source": {
                "sha256": doctor.sha256_file(wrapper),
            }
        },
    }
    action = doctor.RepairAction(
        "restore_launcher",
        ["leanctx.launcher"],
        "R1",
        "restore wrapper",
        status="PLANNED",
    )
    repaired, snapshot, journal = doctor.execute_repairs(paths, [action], manifest)
    assert repaired[0].status == "REPAIRED"
    assert doctor.launcher_marker_ok(paths)
    assert snapshot is not None and journal is not None
    doctor.restore_snapshot(snapshot, journal)
    assert paths.leanctx.read_bytes() == original

# Package provenance must still be writable when a Harr-only harness has not
# installed the real LeanCTX binary yet; Doctor diagnoses that component later.
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    home = root / "home"
    libexec = home / ".local" / "libexec" / "harr"
    paths = doctor.Paths(
        platform="linux",
        home=home,
        config_home=home / ".config",
        harr_config=home / ".config" / "harr",
        libexec=libexec,
        common=ROOT / "common",
        bin_dir=home / ".local" / "bin",
        leanctx=home / ".local" / "bin" / "lean-ctx",
        lean_config=home / ".config" / "lean-ctx" / "config.toml",
        effective=home / ".config" / "harr" / "mcp-registry.json",
        catalog=ROOT / "common" / "mcp" / "registry.json",
        secrets=home / ".config" / "harr" / "secrets",
        npm_prefix=home / ".local" / "share" / "harr" / "npm",
        runner=home / ".local" / "bin" / "harr-mcp-run",
        manifest=libexec / "install-manifest.json",
        repair_root=home / ".local" / "share" / "harr" / "doctor-repairs",
        codex_home=home / ".codex",
        opencode_home=home / ".config" / "opencode",
        harr_command=home / ".local" / "bin" / "harr",
    )
    saved = {key: os.environ.get(key) for key in ("HARR_LEANCTX_BUILD", "HARR_LEANCTX_ID", "HARR_LEANCTX_VERSION")}
    os.environ["HARR_LEANCTX_BUILD"] = "test-build"
    os.environ["HARR_LEANCTX_ID"] = "test-build-id"
    os.environ["HARR_LEANCTX_VERSION"] = "3.11.0"
    try:
        rc = doctor.write_manifest(
            paths,
            SimpleNamespace(source_root=None, harr_version="0.test", install_type="package"),
        )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    assert rc == 0
    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert payload["install_type"] == "package"
    assert payload["leanctx"]["build"] == "test-build"
    assert payload["leanctx"]["identity"] == "test-build-id"
    assert Path(payload["leanctx"]["real_path"]).parts[-4:] == ("vendor", "lean-ctx", "test-build", "lean-ctx")

linux_harr = (ROOT / "linux" / "harr").read_text(encoding="utf-8")
linux_install = (ROOT / "linux" / "install.sh").read_text(encoding="utf-8")
assert 'HARR_INSTALL_TYPE="$setup_install_type"' in linux_harr
assert 'local install_type="${HARR_INSTALL_TYPE:-source}"' in linux_install

print("Harr doctor contract: PASS")
