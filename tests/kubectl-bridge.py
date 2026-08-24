#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "common" / "kubernetes" / "kubectl.py"
spec = importlib.util.spec_from_file_location("harr_kubectl", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def kube_config(current: str = "static") -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": current,
        "clusters": [
            {"name": "cluster-a", "cluster": {"server": "https://cluster.example.test", "certificate-authority-data": "Y2E="}},
        ],
        "contexts": [
            {"name": "static", "context": {"cluster": "cluster-a", "user": "static-user", "namespace": "default"}},
            {"name": "exec", "context": {"cluster": "cluster-a", "user": "exec-user", "namespace": "default"}},
        ],
        "users": [
            {"name": "static-user", "user": {"token": "secret-token"}},
            {"name": "exec-user", "user": {"exec": {"apiVersion": "client.authentication.k8s.io/v1", "command": "cloud-login", "args": ["token"]}}},
        ],
    }


info = mod.context_info(kube_config())
assert info == {
    "context": "static",
    "cluster": "cluster-a",
    "user": "static-user",
    "server": "https://cluster.example.test",
    "exec_command": "",
}
assert mod.context_info(kube_config(), "exec")["exec_command"] == "cloud-login"
assert mod.explicit_context(["get", "pods", "--context", "exec"]) == "exec"
assert mod.explicit_context(["--context=exec", "get", "pods"]) == "exec"
assert mod.explicit_context(["get", "pods"]) is None

for args in (["--kubeconfig", "/tmp/other"], ["get", "pods", "--kubeconfig=/tmp/other"]):
    try:
        mod.reject_kubeconfig_override(list(args))
    except RuntimeError as exc:
        assert "owns --kubeconfig" in str(exc)
    else:
        raise AssertionError("managed kubeconfig override was not rejected")

with tempfile.TemporaryDirectory() as tmp_raw:
    tmp = Path(tmp_raw)
    old_config = os.environ.get("HARR_CONFIG_DIR")
    os.environ["HARR_CONFIG_DIR"] = str(tmp / "harr")
    try:
        # Static credentials produce a private self-contained Harr snapshot.
        mod.write_snapshot(
            kubectl=sys.executable,
            source=str(tmp / "source-config"),
            data=kube_config(),
            allow_exec=False,
            check=False,
        )
        managed = mod.managed_config_path()
        meta_path = mod.metadata_path()
        assert managed.is_file()
        assert meta_path.is_file()
        saved = json.loads(managed.read_text(encoding="utf-8"))
        assert saved["users"][0]["user"]["token"] == "secret-token"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["context"] == "static"
        assert meta["allow_exec"] is False
        if os.name != "nt":
            assert managed.stat().st_mode & 0o777 == 0o600
            assert managed.parent.stat().st_mode & 0o777 == 0o700

        # The bridge always inserts its managed kubeconfig in the real kubectl invocation.
        captured: dict[str, object] = {}
        if os.name == "nt":
            original_call = mod.subprocess.call
            def fake_call(command, env=None):
                captured["command"] = list(command)
                captured["env"] = dict(env or {})
                return 0
            mod.subprocess.call = fake_call
            try:
                assert mod.run(SimpleNamespace(kubectl_args=["--", "get", "pods", "-n", "default"])) == 0
            finally:
                mod.subprocess.call = original_call
        else:
            original_exec = mod.os.execvpe
            def fake_exec(file, command, env):
                captured["command"] = list(command)
                captured["env"] = dict(env)
            mod.os.execvpe = fake_exec
            try:
                assert mod.run(SimpleNamespace(kubectl_args=["--", "get", "pods", "-n", "default"])) == 127
            finally:
                mod.os.execvpe = original_exec

        command = captured["command"]
        assert isinstance(command, list)
        assert command[0] == sys.executable
        assert command[1:3] == ["--kubeconfig", str(managed)]
        assert command[3:] == ["get", "pods", "-n", "default"]
        env = captured["env"]
        assert isinstance(env, dict)
        assert env["KUBECONFIG"] == str(managed)

        # An exec-backed selected context is blocked unless explicitly opted in.
        try:
            mod.run(SimpleNamespace(kubectl_args=["--", "--context", "exec", "get", "pods"]))
        except RuntimeError as exc:
            assert "exec credential helper" in str(exc)
        else:
            raise AssertionError("exec credential context was allowed without opt-in")

        try:
            mod.write_snapshot(
                kubectl=sys.executable,
                source=str(tmp / "source-config"),
                data=kube_config("exec"),
                allow_exec=False,
                check=False,
            )
        except RuntimeError as exc:
            assert "portable kubeconfig alone is insufficient" in str(exc)
        else:
            raise AssertionError("configure accepted current exec credential helper without opt-in")

        mod.write_snapshot(
            kubectl=sys.executable,
            source=str(tmp / "source-config"),
            data=kube_config("exec"),
            allow_exec=True,
            check=False,
        )
        assert json.loads(mod.metadata_path().read_text(encoding="utf-8"))["allow_exec"] is True
    finally:
        if old_config is None:
            os.environ.pop("HARR_CONFIG_DIR", None)
        else:
            os.environ["HARR_CONFIG_DIR"] = old_config

print("Harr kubectl bridge: PASS")
