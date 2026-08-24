#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def harr_config_dir() -> Path:
    override = os.environ.get("HARR_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return root / "harr"


def kube_dir() -> Path:
    return harr_config_dir() / "kubernetes"


def managed_config_path() -> Path:
    return kube_dir() / "config"


def metadata_path() -> Path:
    return kube_dir() / "meta.json"


def normalize_source(value: str | None) -> str:
    raw = value or os.environ.get("KUBECONFIG") or str(Path.home() / ".kube" / "config")
    parts = [item for item in raw.split(os.pathsep) if item]
    if not parts:
        fail("empty kubeconfig source")
    normalized = [str(Path(item).expanduser().resolve()) for item in parts]
    if not any(Path(item).is_file() for item in normalized):
        fail(f"no kubeconfig source file exists: {os.pathsep.join(normalized)}")
    return os.pathsep.join(normalized)


def resolve_kubectl(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("HARR_KUBECTL") or shutil.which("kubectl")
    if not candidate:
        fail("kubectl was not found; install kubectl or pass `harr kube configure --kubectl PATH`")
    path = Path(candidate).expanduser()
    if path.is_absolute() or path.parent != Path("."):
        resolved = path.resolve()
        if not resolved.is_file():
            fail(f"kubectl executable does not exist: {resolved}")
        return str(resolved)
    found = shutil.which(str(path))
    if not found:
        fail(f"kubectl executable was not found: {candidate}")
    return str(Path(found).resolve())


def run_capture(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def capture_config(kubectl: str, source: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["KUBECONFIG"] = source
    result = run_capture([kubectl, "config", "view", "--raw", "--flatten", "-o", "json"], env=env)
    if result.returncode != 0:
        detail = result.stderr.strip() or "kubectl config view failed"
        fail(detail)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"kubectl returned invalid kubeconfig JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("contexts"), list):
        fail("kubectl returned an invalid kubeconfig")
    return data


def named(items: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def context_info(data: dict[str, Any], context_name: str | None = None) -> dict[str, Any]:
    selected = context_name or str(data.get("current-context") or "")
    if not selected:
        fail("kubeconfig has no current context")
    context_row = named(data.get("contexts"), selected)
    if not context_row:
        fail(f"kubeconfig context not found: {selected}")
    context = context_row.get("context") or {}
    cluster_name = str(context.get("cluster") or "")
    user_name = str(context.get("user") or "")
    if not cluster_name:
        fail(f"kubeconfig context {selected!r} has no cluster")
    cluster_row = named(data.get("clusters"), cluster_name) or {}
    cluster = cluster_row.get("cluster") or {}
    user_row = named(data.get("users"), user_name) or {}
    user = user_row.get("user") or {}
    exec_cfg = user.get("exec") if isinstance(user, dict) else None
    exec_command = ""
    if isinstance(exec_cfg, dict):
        exec_command = str(exec_cfg.get("command") or "")
    return {
        "context": selected,
        "cluster": cluster_name,
        "user": user_name,
        "server": str(cluster.get("server") or ""),
        "exec_command": exec_command,
    }


def explicit_context(args: list[str]) -> str | None:
    skip = False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg == "--context":
            if index + 1 >= len(args):
                fail("--context requires a value")
            return args[index + 1]
        if arg.startswith("--context="):
            return arg.split("=", 1)[1]
    return None


def reject_kubeconfig_override(args: list[str]) -> None:
    for arg in args:
        if arg == "--kubeconfig" or arg.startswith("--kubeconfig="):
            fail("`harr kubectl` owns --kubeconfig; use `harr kube configure` or `harr kube sync` to change the managed source")


def secure_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    fd, temp_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    temp = Path(temp_raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        os.replace(temp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def check_cluster(kubectl: str, config: Path, timeout: int = 5) -> tuple[bool, str]:
    result = run_capture([
        kubectl,
        "--kubeconfig",
        str(config),
        "get",
        "--raw=/version",
        f"--request-timeout={timeout}s",
    ])
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr.strip() or result.stdout.strip() or "cluster check failed")


def write_snapshot(
    *,
    kubectl: str,
    source: str,
    data: dict[str, Any],
    allow_exec: bool,
    check: bool,
) -> None:
    info = context_info(data)
    if info["exec_command"] and not allow_exec:
        fail(
            f"current context {info['context']!r} uses exec credential helper {info['exec_command']!r}; "
            "a portable kubeconfig alone is insufficient. Re-run with --allow-exec only if that helper is reachable from Harr hosts."
        )

    root = kube_dir()
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass

    fd, candidate_raw = tempfile.mkstemp(prefix=".config-check.", dir=str(root), text=True)
    candidate = Path(candidate_raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        try:
            candidate.chmod(0o600)
        except OSError:
            pass
        if check:
            ok, detail = check_cluster(kubectl, candidate)
            if not ok:
                fail(f"managed kubeconfig cluster check failed: {detail}")
        config_text = candidate.read_text(encoding="utf-8")
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass

    metadata = {
        "schema": 1,
        "kubectl": kubectl,
        "source_kubeconfig": source,
        "configured_at": datetime.now(timezone.utc).isoformat(),
        "allow_exec": bool(allow_exec),
        "context": info["context"],
        "cluster": info["cluster"],
        "user": info["user"],
        "server": info["server"],
        "exec_command": info["exec_command"],
    }
    secure_write(managed_config_path(), config_text)
    secure_write(metadata_path(), json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")


def configure(args: argparse.Namespace) -> int:
    kubectl = resolve_kubectl(args.kubectl)
    source = normalize_source(args.source)
    data = capture_config(kubectl, source)
    write_snapshot(kubectl=kubectl, source=source, data=data, allow_exec=args.allow_exec, check=not args.no_check)
    info = context_info(data)
    print(f"Harr Kubernetes config stored: {managed_config_path()}")
    print(f"context: {info['context']}")
    print(f"cluster: {info['cluster']}")
    print(f"auth: {'exec-helper ' + info['exec_command'] if info['exec_command'] else 'portable kubeconfig'}")
    return 0


def load_metadata() -> dict[str, Any]:
    path = metadata_path()
    if not path.is_file():
        fail("Harr Kubernetes is not configured; run `harr kube configure` from a terminal where kubectl already works")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid Harr Kubernetes metadata: {exc}")
    if data.get("schema") != 1:
        fail("unsupported Harr Kubernetes metadata")
    return data


def load_managed_config() -> dict[str, Any]:
    path = managed_config_path()
    if not path.is_file():
        fail("Harr Kubernetes config is missing; run `harr kube configure`")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid Harr managed kubeconfig: {exc}")


def sync(args: argparse.Namespace) -> int:
    metadata = load_metadata()
    kubectl = resolve_kubectl(str(metadata.get("kubectl") or ""))
    source = normalize_source(str(metadata.get("source_kubeconfig") or ""))
    allow_exec = bool(args.allow_exec or metadata.get("allow_exec"))
    data = capture_config(kubectl, source)
    write_snapshot(kubectl=kubectl, source=source, data=data, allow_exec=allow_exec, check=not args.no_check)
    info = context_info(data)
    print(f"Harr Kubernetes config refreshed: {managed_config_path()}")
    print(f"context: {info['context']}")
    return 0


def status(args: argparse.Namespace) -> int:
    try:
        metadata = load_metadata()
        data = load_managed_config()
        kubectl = resolve_kubectl(str(metadata.get("kubectl") or ""))
    except RuntimeError as exc:
        print(f"kubernetes\tmissing\t{exc}")
        return 1

    info = context_info(data)
    target_exec = info["exec_command"]
    auth = f"exec-helper:{target_exec}" if target_exec else "portable"
    print(f"kubectl\tavailable\t{kubectl}")
    print(f"kubeconfig\tmanaged\t{managed_config_path()}")
    print(f"context\t{info['context']}")
    print(f"cluster\t{info['cluster']}")
    if info["server"]:
        print(f"server\t{info['server']}")
    print(f"auth\t{auth}")
    if args.no_check:
        return 0
    ok, detail = check_cluster(kubectl, managed_config_path())
    if ok:
        print("cluster\treachable")
        return 0
    print(f"cluster\tunreachable\t{detail}")
    return 1


def run(args: argparse.Namespace) -> int:
    metadata = load_metadata()
    data = load_managed_config()
    kubectl = resolve_kubectl(str(metadata.get("kubectl") or ""))
    kubectl_args = list(args.kubectl_args)
    if kubectl_args and kubectl_args[0] == "--":
        kubectl_args = kubectl_args[1:]
    reject_kubeconfig_override(kubectl_args)
    selected_context = explicit_context(kubectl_args)
    info = context_info(data, selected_context)
    if info["exec_command"] and not bool(metadata.get("allow_exec")):
        fail(
            f"context {info['context']!r} uses exec credential helper {info['exec_command']!r}; "
            "re-run `harr kube configure --allow-exec` only if that helper is reachable from Harr hosts"
        )

    command = [kubectl, "--kubeconfig", str(managed_config_path()), *kubectl_args]
    env = os.environ.copy()
    env["KUBECONFIG"] = str(managed_config_path())
    if os.name == "nt":
        return subprocess.call(command, env=env)
    os.execvpe(command[0], command, env)
    return 127


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harr portable kubectl bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    p_config = sub.add_parser("configure", help="capture a flattened portable kubeconfig")
    p_config.add_argument("--source", help="source KUBECONFIG path list; defaults to current KUBECONFIG or ~/.kube/config")
    p_config.add_argument("--kubectl", help="kubectl executable path; defaults to PATH")
    p_config.add_argument("--allow-exec", action="store_true", help="allow current context to depend on an external exec credential helper")
    p_config.add_argument("--no-check", action="store_true", help="skip live cluster reachability verification")

    p_sync = sub.add_parser("sync", help="refresh from the source recorded by configure")
    p_sync.add_argument("--allow-exec", action="store_true", help="allow exec credential helper if the refreshed current context requires one")
    p_sync.add_argument("--no-check", action="store_true", help="skip live cluster reachability verification")

    p_status = sub.add_parser("status", help="show managed context/auth state and test reachability")
    p_status.add_argument("--no-check", action="store_true", help="do not contact the Kubernetes API")

    p_run = sub.add_parser("run", help="execute real kubectl with the Harr-managed kubeconfig")
    p_run.add_argument("kubectl_args", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "configure":
        return configure(args)
    if args.command == "sync":
        return sync(args)
    if args.command == "status":
        return status(args)
    if args.command == "run":
        return run(args)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
