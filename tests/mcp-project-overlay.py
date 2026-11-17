#!/usr/bin/env python3
"""Project MCP overlay acceptance checks (execution plan stage 6).

Covers: fail-closed manifest validation, user-local trust, credential profile
store, effective-registry merge semantics, per-session gateway config rendering
with scoped secret export, run_server env sanitization, profile-based cache
invalidation, atomic secret rotation, and secret-free diagnostics.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "common" / "mcp" / "manager.py"
sys.path.insert(0, str(ROOT / "common" / "mcp"))

import project_overlay as overlay  # noqa: E402
import profiles as profiles_mod  # noqa: E402

spec = importlib.util.spec_from_file_location("harr_mcp_manager", MANAGER_PATH)
assert spec and spec.loader
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


def memento_env_var(secret_id: str) -> str:
    return "LEAN_CTX_SECRET_" + secret_id.encode("utf-8").hex().upper()


def expect_error(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__} from {fn.__name__}")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def run_manager(args: list[str], *, config_dir: Path, cwd: Path, registry: Path | None = None,
                extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HARR_CONFIG_DIR"] = str(config_dir)
    env.pop("LEAN_CTX_CONFIG_DIR", None)
    if extra_env:
        env.update(extra_env)
    cmd = [sys.executable, str(MANAGER_PATH)]
    if registry is not None:
        cmd += ["--registry", str(registry)]
    cmd += args
    return subprocess.run(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=60)


def base_servers() -> list[dict]:
    return [
        {
            "name": "alpha",
            "label": "Alpha",
            "transport": "stdio",
            "lifecycle": "on-demand",
            "runtime": {"kind": "path", "command": "alpha-upstream", "args": []},
            "secrets": [{
                "name": "alpha", "file": "alpha-token", "prompt": "Alpha token",
                "memento_id": "mcp/test/alpha",
                "target": {"kind": "env", "name": "ALPHA_TOKEN"},
            }],
        },
        {
            "name": "beta",
            "label": "Beta",
            "transport": "stdio",
            "lifecycle": "on-demand",
            "runtime": {"kind": "path", "command": "beta-upstream", "args": []},
            "secrets": [{
                "name": "beta", "file": "beta-token", "prompt": "Beta token",
                "memento_id": "mcp/test/beta",
                "target": {"kind": "env", "name": "BETA_TOKEN"},
            }],
        },
    ]


def http_providers() -> dict:
    return {
        "remote-alpha": {
            "label": "Remote Alpha",
            "transport": "http",
            "profile_endpoint": True,
            "lifecycle": "on-demand",
        },
    }


# ---------------------------------------------------------------------------
# 1. Manifest validation is fail-closed.

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    ok = root / ".harr" / "mcp.json"
    write_json(ok, {
        "schema": 1,
        "instances": {
            "remote-alpha": {"provider": "remote-alpha", "profile": "remote-alpha-prod"},
            "beta": {"enabled": False},
        },
        "extensions": {"company-search": {"transport": "http", "url": "https://mcp.example.com/search"}},
    })
    manifest = overlay.load_manifest(ok)
    assert manifest["instances"]["remote-alpha"]["profile"] == "remote-alpha-prod"
    assert manifest["instances"]["beta"] == {"name": "beta", "enabled": False, "provider": None, "profile": None}
    assert manifest["extensions"]["company-search"]["url"].startswith("https://")
    assert len(manifest["digest"]) == 64

    def bad_manifest(payload, note):
        path = root / "cases" / note / ".harr" / "mcp.json"
        write_json(path, payload)
        return expect_error(overlay.ProjectOverlayError, overlay.load_manifest, path)

    bad_manifest({"schema": 1, "instances": {"x": {"provider": "p", "command": "evil"}}}, "command")
    bad_manifest({"schema": 1, "instances": {"x": {"provider": "p", "secret": "inline"}}}, "inline-secret")
    bad_manifest({"schema": 1, "extensions": {"x": {"transport": "http", "url": "http://mcp.example.com/s"}}}, "plain-http")
    bad_manifest({"schema": 1, "extensions": {"x": {"transport": "http", "url": "https://user:pw@x.example.com"}}}, "userinfo")
    bad_manifest({"schema": 1, "instances": {"Bad_Name": {"provider": "p"}}}, "bad-name")
    bad_manifest({"schema": 2}, "bad-schema")
    bad_manifest({"schema": 1, "mystery": True}, "unknown-top-field")
    bad_manifest({"schema": 1, "instances": {"x": {"provider": "p", "extra": 1}}}, "unknown-instance-field")

    loopback = root / "cases" / "loopback" / ".harr" / "mcp.json"
    write_json(loopback, {"schema": 1, "extensions": {"dev": {"transport": "http", "url": "http://127.0.0.1:8123/mcp"}}})
    assert overlay.load_manifest(loopback)["extensions"]["dev"]["url"].startswith("http://127.0.0.1")

    raw = root / "cases" / "not-json" / ".harr" / "mcp.json"
    raw.parent.mkdir(parents=True)
    raw.write_text("{{{", encoding="utf-8")
    expect_error(overlay.ProjectOverlayError, overlay.load_manifest, raw)

    # find_manifest resolves symlinks (macOS /var -> /private/var), so compare
    # resolved paths on both sides.
    expected_manifest = (root / "cases" / "command" / ".harr" / "mcp.json").resolve()
    assert overlay.find_manifest(root / "cases" / "command") == expected_manifest
    with tempfile.TemporaryDirectory() as empty:
        assert overlay.find_manifest(Path(empty) / "deeper" / "dir") is None

# ---------------------------------------------------------------------------
# 2. Trust: user-local digest approval, digest change -> untrusted, revoke.

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "proj"
    manifest_path = root / ".harr" / "mcp.json"
    write_json(manifest_path, {"schema": 1, "instances": {"beta": {"enabled": False}}})
    manifest = overlay.load_manifest(manifest_path)
    config = Path(tmp) / "harr"
    assert not overlay.is_trusted(root, config, manifest["digest"])
    overlay.approve(root, config, manifest["digest"])
    trust_file = overlay.trust_path(root, config)
    assert trust_file.is_file() and stat.S_IMODE(trust_file.stat().st_mode) == 0o600
    assert overlay.is_trusted(root, config, manifest["digest"])
    write_json(manifest_path, {"schema": 1, "instances": {"beta": {"enabled": False}, "alpha": {"enabled": False}}})
    changed = overlay.load_manifest(manifest_path)
    assert not overlay.is_trusted(root, config, changed["digest"]), "digest change must invalidate trust"
    assert overlay.is_trusted(root, config, manifest["digest"])
    assert overlay.revoke(root, config)
    assert not overlay.is_trusted(root, config, manifest["digest"])
    assert not overlay.revoke(root, config)

# ---------------------------------------------------------------------------
# 3. Profile store: permissions, atomic write, fingerprint, validation.

with tempfile.TemporaryDirectory() as tmp:
    directory = profiles_mod.profiles_dir(Path(tmp) / "harr")
    assert directory.is_dir()
    profile = {
        "id": "remote-alpha-prod",
        "provider": "remote-alpha",
        "kind": "http",
        "endpoint": "https://alpha.example.com/mcp",
        "secret": {"file": "alpha-remote-token", "memento_id": "mcp/test/alpha-remote"},
        "state": "enabled",
        "bound_projects": [],
    }
    path = profiles_mod.write_profile(directory, profile)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, "profiles must be 0600"
    stored = profiles_mod.get_profile(directory, "remote-alpha-prod")
    assert stored["endpoint"].startswith("https://")

    first = profiles_mod.profile_fingerprint(directory)
    profiles_mod.set_state(directory, "remote-alpha-prod", "disabled")
    assert profiles_mod.profile_fingerprint(directory) != first, "state change must invalidate the session key"
    profiles_mod.set_state(directory, "remote-alpha-prod", "enabled")

    def bad_profile(mutate, note):
        broken = json.loads(json.dumps(profile))
        mutate(broken)
        return expect_error(overlay.ProjectOverlayError, profiles_mod.write_profile, directory, broken)

    bad_profile(lambda p: p.update({"endpoint": "http://alpha.example.com/mcp"}), "plain-http")
    bad_profile(lambda p: p.update({"endpoint": "https://user:pw@alpha.example.com/mcp"}), "userinfo")
    bad_profile(lambda p: p["secret"].update({"file": "../escape"}), "traversal")
    bad_profile(lambda p: p.update({"command": "evil"}), "command-field")
    bad_profile(lambda p: p.update({"state": "paused"}), "bad-state")
    bad_profile(lambda p: p["secret"].update({"memento_id": "not-mcp"}), "bad-memento")

    profiles_mod.remove_profile(directory, "remote-alpha-prod")
    assert profiles_mod.get_profile(directory, "remote-alpha-prod") is None

# ---------------------------------------------------------------------------
# 4. Effective registry merge: precedence, isolation, scoped secret refs.

with tempfile.TemporaryDirectory() as tmp:
    config = Path(tmp) / "harr"
    root = Path(tmp) / "proj"
    manifest_path = root / ".harr" / "mcp.json"
    write_json(manifest_path, {
        "schema": 1,
        "instances": {
            "remote-alpha": {"provider": "remote-alpha", "profile": "remote-alpha-prod"},
            "beta": {"enabled": False},
        },
        "extensions": {"ext-http": {"transport": "http", "url": "https://ext.example.com/mcp"}},
    })
    manifest = overlay.load_manifest(manifest_path)
    profiles_dir = profiles_mod.profiles_dir(config)
    profiles_mod.write_profile(profiles_dir, {
        "id": "remote-alpha-prod",
        "provider": "remote-alpha",
        "kind": "http",
        "endpoint": "https://alpha.example.com/mcp",
        "secret": {"file": "alpha-remote-token", "memento_id": "mcp/test/alpha-remote"},
        "state": "enabled",
        "bound_projects": [overlay.project_key(root)],
    })
    session = {"overlay": overlay, "manifest": manifest, "root": root}
    data = {"schema": 1, "servers": base_servers(), "providers": http_providers()}

    with patch.dict(manager.os.environ, {"HARR_CONFIG_DIR": str(config)}):
        entries, secret_refs = manager.effective_servers(data, session)
        names = [entry["name"] for entry in entries]
        assert "beta" not in names, "project disable must remove the global instance"
        assert "alpha" in names and "remote-alpha" in names and "ext-http" in names
        remote = next(entry for entry in entries if entry["name"] == "remote-alpha")
        assert remote["url"] == "https://alpha.example.com/mcp", "endpoint must come from the profile"
        assert remote["secret_headers"]["Authorization"] == {
        "id": "mcp/test/alpha-remote", "format": "Bearer {secret}",
        }
        ref_ids = sorted(ref["memento_id"] for ref in secret_refs)
        assert "mcp/test/alpha" in ref_ids and "mcp/test/alpha-remote" in ref_ids
        assert "mcp/test/beta" not in ref_ids, "disabled instance secret must not be exported"

        # Unbound profile is rejected.
        profiles_mod.write_profile(profiles_dir, {
        "id": "other-project",
        "provider": "remote-alpha",
        "kind": "http",
        "endpoint": "https://alpha.example.com/mcp",
        "state": "enabled",
        "bound_projects": ["0" * 16],
        })
        manifest2_path = root / "other" / ".harr" / "mcp.json"
        write_json(manifest2_path, {"schema": 1, "instances": {"remote-alpha": {"provider": "remote-alpha", "profile": "other-project"}}})
        manifest2 = overlay.load_manifest(manifest2_path)
        exc = expect_error(SystemExit, manager.effective_servers, data,
                       {"overlay": overlay, "manifest": manifest2, "root": manifest2_path.parent})
        assert "not bound to this project" in str(exc)

        # Disabled profile is rejected.
        profiles_mod.set_state(profiles_dir, "remote-alpha-prod", "disabled")
        exc = expect_error(SystemExit, manager.effective_servers, data, session)
        assert "is disabled" in str(exc)
        profiles_mod.set_state(profiles_dir, "remote-alpha-prod", "enabled")

        # OAuth provider with a profile secret is rejected: the gateway cannot
        # carry an OAuth flow and a wired Authorization header at once.
        oauth_providers = {
            "remote-oauth": {
                "label": "Remote OAuth",
                "transport": "http",
                "profile_endpoint": True,
                "oauth": True,
                "lifecycle": "on-demand",
            },
        }
        oauth_root = root / "oauth"
        profiles_mod.write_profile(profiles_dir, {
            "id": "oauth-prod",
            "provider": "remote-oauth",
            "kind": "http",
            "endpoint": "https://oauth.example.com/mcp",
            "secret": {"file": "oauth-token", "memento_id": "mcp/test/oauth"},
            "state": "enabled",
            "bound_projects": [overlay.project_key(oauth_root)],
        })
        oauth_manifest_path = oauth_root / ".harr" / "mcp.json"
        write_json(oauth_manifest_path, {
            "schema": 1,
            "instances": {"remote-oauth": {"provider": "remote-oauth", "profile": "oauth-prod"}},
        })
        oauth_manifest = overlay.load_manifest(oauth_manifest_path)
        oauth_data = {"schema": 1, "servers": base_servers(), "providers": oauth_providers}
        exc = expect_error(SystemExit, manager.effective_servers, oauth_data,
                           {"overlay": overlay, "manifest": oauth_manifest, "root": oauth_root})
        assert "uses OAuth" in str(exc)

        # Unknown provider and name conflicts fail closed.
        bad_manifest3_path = root / "unknown-provider" / ".harr" / "mcp.json"
        write_json(bad_manifest3_path, {"schema": 1, "instances": {"x": {"provider": "nope"}}})
        m3 = overlay.load_manifest(bad_manifest3_path)
        exc = expect_error(SystemExit, manager.effective_servers, data,
                       {"overlay": overlay, "manifest": m3, "root": bad_manifest3_path.parent})
        assert "unknown provider" in str(exc)

        conflict_path = root / "conflict" / ".harr" / "mcp.json"
        write_json(conflict_path, {"schema": 1, "instances": {"alpha": {"provider": "remote-alpha"}}})
        m4 = overlay.load_manifest(conflict_path)
        exc = expect_error(SystemExit, manager.effective_servers, data,
                       {"overlay": overlay, "manifest": m4, "root": conflict_path.parent})
        assert "conflicts" in str(exc)

# ---------------------------------------------------------------------------
# 5. exec-leanctx: scoped secret export, session config, trust fallback.

with tempfile.TemporaryDirectory() as tmp:
    config = Path(tmp) / "harr"
    secrets_dir = config / "secrets"
    secrets_dir.mkdir(parents=True)
    ALPHA_VALUE = "alpha-value-0123456789abcdef"
    BETA_VALUE = "beta-value-fedcba9876543210"
    (secrets_dir / "alpha-token").write_text(ALPHA_VALUE + "\n", encoding="utf-8")
    (secrets_dir / "beta-token").write_text(BETA_VALUE + "\n", encoding="utf-8")
    os.chmod(secrets_dir, 0o700)
    registry = Path(tmp) / "effective.json"
    write_json(registry, {"schema": 1, "servers": base_servers()})

    project = Path(tmp) / "proj"
    (project / "sub").mkdir(parents=True)

    # No manifest: legacy behavior — all registry secrets exported, no override.
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project / "sub", registry=registry)
    assert result.returncode == 0, result.stderr
    assert memento_env_var("mcp/test/alpha") in result.stdout
    assert memento_env_var("mcp/test/beta") in result.stdout
    assert "LEAN_CTX_CONFIG_DIR" not in result.stdout

    # Trusted manifest disabling beta: scoped export + session config.
    write_json(project / ".harr" / "mcp.json", {"schema": 1, "instances": {"beta": {"enabled": False}}})
    manifest = overlay.load_manifest(project / ".harr" / "mcp.json")
    overlay.approve(project, config, manifest["digest"])
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    assert memento_env_var("mcp/test/alpha") in result.stdout, result.stdout
    assert memento_env_var("mcp/test/beta") not in result.stdout, "disabled instance secret leaked"
    config_dir_line = next(line for line in result.stdout.splitlines() if line.startswith("LEAN_CTX_CONFIG_DIR="))
    session_dir = Path(config_dir_line.split("=", 1)[1])
    session_config = session_dir / "config.toml"
    assert session_config.is_file()
    assert stat.S_IMODE(session_config.stat().st_mode) == 0o600
    assert stat.S_IMODE(session_dir.stat().st_mode) == 0o700
    rendered = tomllib.loads(session_config.read_text(encoding="utf-8"))
    rendered_names = [entry["name"] for entry in rendered["gateway"]["servers"]]
    assert "alpha" in rendered_names and "beta" not in rendered_names

    # Stable cache key; profile state change invalidates it.
    first_key = session_dir.name
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project, registry=registry)
    second_line = next(line for line in result.stdout.splitlines() if line.startswith("LEAN_CTX_CONFIG_DIR="))
    assert Path(second_line.split("=", 1)[1]).name == first_key, "cache key must be stable"

    profiles_root = config / "mcp-profiles"
    profiles_mod.write_profile(profiles_root, {
        "id": "invalidation-probe",
        "provider": "remote-alpha",
        "kind": "stdio",
        "state": "enabled",
        "bound_projects": [overlay.project_key(project)],
    })
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project, registry=registry)
    third_line = next(line for line in result.stdout.splitlines() if line.startswith("LEAN_CTX_CONFIG_DIR="))
    assert Path(third_line.split("=", 1)[1]).name != first_key, "profile state change must change the session key"

    # Untrusted manifest: fail closed to global defaults with a hint.
    write_json(project / ".harr" / "mcp.json", {"schema": 1, "instances": {"alpha": {"enabled": False}}})
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project, registry=registry)
    assert memento_env_var("mcp/test/alpha") in result.stdout
    assert memento_env_var("mcp/test/beta") in result.stdout
    assert "untrusted" in result.stderr and "harr mcp project trust" in result.stderr

    # Invalid manifest: rejected, global defaults, safe error.
    write_json(project / ".harr" / "mcp.json", {"schema": 1, "instances": {"x": {"command": "evil"}}})
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project, registry=registry)
    assert memento_env_var("mcp/test/alpha") in result.stdout
    assert "rejected" in result.stderr
    assert "evil" not in result.stderr or "unknown fields" in result.stderr

# ---------------------------------------------------------------------------
# 6. Profile-bound http instance end-to-end (manager CLI + session render).

with tempfile.TemporaryDirectory() as tmp:
    config = Path(tmp) / "harr"
    secrets_dir = config / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "alpha-remote-token").write_text("remote-value-0123456789abcdef\n", encoding="utf-8")
    (secrets_dir / "alpha-token").write_text("alpha-value-0123456789abcdef\n", encoding="utf-8")
    (secrets_dir / "beta-token").write_text("beta-value-fedcba9876543210\n", encoding="utf-8")
    os.chmod(secrets_dir, 0o700)
    registry = Path(tmp) / "effective.json"
    write_json(registry, {"schema": 1, "servers": base_servers(), "providers": http_providers()})

    project = Path(tmp) / "proj"
    (project / ".harr").mkdir(parents=True)
    write_json(project / ".harr" / "mcp.json", {
        "schema": 1,
        "instances": {"remote-alpha": {"provider": "remote-alpha", "profile": "remote-alpha-prod"}},
    })
    result = run_manager(["profile", "set", "remote-alpha-prod",
                          "--provider", "remote-alpha",
                          "--endpoint", "https://alpha.example.com/mcp",
                          "--secret-file", "alpha-remote-token",
                          "--memento-id", "mcp/test/alpha-remote"],
                         config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    result = run_manager(["project", "trust"], config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config,
                         cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    config_dir_line = next(line for line in result.stdout.splitlines() if line.startswith("LEAN_CTX_CONFIG_DIR="))
    session_config = Path(config_dir_line.split("=", 1)[1]) / "config.toml"
    rendered = tomllib.loads(session_config.read_text(encoding="utf-8"))
    servers_rendered = {entry["name"]: entry for entry in rendered["gateway"]["servers"]}
    assert "remote-alpha" in servers_rendered
    assert servers_rendered["remote-alpha"]["url"] == "https://alpha.example.com/mcp"
    assert servers_rendered["remote-alpha"]["secret_headers"]["Authorization"]["format"] == "Bearer {secret}"
    assert servers_rendered["remote-alpha"]["secret_headers"]["Authorization"]["id"] == "mcp/test/alpha-remote"
    assert memento_env_var("mcp/test/alpha-remote") in result.stdout
    assert memento_env_var("mcp/test/beta") in result.stdout  # global instance still wired

    # Diagnostics list sources and never leak secret values.
    result = run_manager(["resolve"], config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    by_name = {row["name"]: row for row in report["instances"]}
    assert by_name["remote-alpha"]["source"] == "project-overlay"
    assert by_name["alpha"]["source"] == "global-selection"
    assert "remote-value-0123456789abcdef" not in result.stdout
    assert "mcp/test/alpha-remote" in report["secret_ids"]

    # Disabling the profile blocks new sessions.
    result = run_manager(["profile", "disable", "remote-alpha-prod"], config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    result = run_manager(["exec-leanctx", "/usr/bin/env", "printenv"], config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    assert "is disabled" in result.stderr, "disabled profile must fail closed"
    assert memento_env_var("mcp/test/alpha-remote") not in result.stdout

# ---------------------------------------------------------------------------
# 7. run_server strips gateway memento env vars from the upstream process.

with tempfile.TemporaryDirectory() as tmp:
    config = Path(tmp) / "harr"
    secrets_dir = config / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "probe-token").write_text("probe-value-0123456789abcdef\n", encoding="utf-8")
    os.chmod(secrets_dir, 0o700)
    registry = Path(tmp) / "effective.json"
    write_json(registry, {"schema": 1, "servers": [{
        "name": "probe",
        "label": "Probe",
        "transport": "stdio",
        "lifecycle": "on-demand",
        "runtime": {"kind": "path", "command": "env", "args": []},
        "secrets": [{
            "name": "probe", "file": "probe-token", "prompt": "Probe token",
            "memento_id": "mcp/test/probe",
            "target": {"kind": "env", "name": "PROBE_TOKEN"},
        }],
    }]})
    leaked = memento_env_var("mcp/test/probe")
    result = run_manager(["run", "probe"], config_dir=config, cwd=Path(tmp),
                         registry=registry, extra_env={leaked: "gateway-secret-value"})
    assert result.returncode == 0, result.stderr
    assert "PROBE_TOKEN=probe-value-0123456789abcdef" in result.stdout, "wired secret must reach the upstream"
    assert leaked not in result.stdout, "gateway memento vars must not leak into the upstream env"
    assert "LEAN_CTX_SECRET_" not in result.stdout

# ---------------------------------------------------------------------------
# 8. Atomic secret rotation (bash write_secret_file).

with tempfile.TemporaryDirectory() as tmp:
    secrets_dir = Path(tmp) / "secrets"
    secrets_dir.mkdir(mode=0o700)
    script = f"""
set -e
HARR_SECRETS_DIR={shlex.quote(str(secrets_dir))}
ensure_private_dir() {{ mkdir -p -- "$1"; chmod 0700 "$1"; }}
write_secret_file() {{
  local file="$1" value="$2"
  ensure_private_dir "$HARR_SECRETS_DIR"
  umask 077
  local tmp="$file.tmp.$$"
  printf '%s\\n' "$value" >"$tmp"
  chmod 0600 "$tmp"
  mv -f "$tmp" "$file"
  chmod 0600 "$file"
}}
write_secret_file "$HARR_SECRETS_DIR/rotate-token" "first-value-0123456789"
write_secret_file "$HARR_SECRETS_DIR/rotate-token" "second-value-fedcba98"
"""
    completed = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    token = secrets_dir / "rotate-token"
    assert token.read_text(encoding="utf-8").strip() == "second-value-fedcba98"
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    assert not list(secrets_dir.glob("*.tmp.*")), "rotation must not leave temporary files"

# ---------------------------------------------------------------------------
# 9. Trust CLI lifecycle round-trip.

with tempfile.TemporaryDirectory() as tmp:
    config = Path(tmp) / "harr"
    registry = Path(tmp) / "effective.json"
    write_json(registry, {"schema": 1, "servers": base_servers()})
    project = Path(tmp) / "proj"
    write_json(project / ".harr" / "mcp.json", {"schema": 1, "instances": {"beta": {"enabled": False}}})
    result = run_manager(["project", "status"], config_dir=config, cwd=project, registry=registry)
    assert json.loads(result.stdout)["status"] == "untrusted"
    result = run_manager(["project", "trust"], config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    result = run_manager(["project", "status"], config_dir=config, cwd=project, registry=registry)
    assert json.loads(result.stdout)["status"] == "trusted"
    result = run_manager(["project", "revoke"], config_dir=config, cwd=project, registry=registry)
    assert result.returncode == 0, result.stderr
    result = run_manager(["project", "status"], config_dir=config, cwd=project, registry=registry)
    assert json.loads(result.stdout)["status"] == "untrusted"

print("project MCP overlay acceptance: PASS")
