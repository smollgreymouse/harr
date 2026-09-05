#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, NoReturn


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3336
MAX_REQUEST_BYTES = 1024 * 1024
COMMAND_TIMEOUT_SECONDS = 3600


def config_home() -> Path:
    configured = os.environ.get("HARR_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg).expanduser() / "harr" if xdg else Path.home() / ".config" / "harr"


def default_secret_file() -> Path:
    return config_home() / "secrets" / "git-host-capability"


def endpoint() -> str:
    return os.environ.get("HARR_GIT_HOST_ENDPOINT", f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")


def fail(message: str, code: int = 2) -> NoReturn:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def ensure_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return load_secret(path)
    token = secrets.token_urlsafe(32)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return token


def load_secret(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Git host capability is missing: {path}; reinstall Harr")
    info = path.stat()
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise RuntimeError(f"Git host capability is not owned by the current user: {path}")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError(f"Git host capability permissions must be 0600: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"Git host capability is empty: {path}; reinstall Harr")
    return token


def validate_agent_socket(raw: str | None) -> str:
    if not raw:
        raise ValueError("SSH_AUTH_SOCK is not set in the Git host service")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("SSH_AUTH_SOCK must be an absolute path")
    try:
        info = path.stat()
    except OSError as exc:
        raise ValueError(f"SSH_AUTH_SOCK is unavailable to the host service: {path}: {exc.strerror}") from exc
    if not stat.S_ISSOCK(info.st_mode):
        raise ValueError(f"SSH_AUTH_SOCK is not a Unix socket: {path}")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError(f"SSH_AUTH_SOCK is not owned by the current user: {path}")
    return str(path)


def validate_request(value: Any) -> tuple[Path, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    raw_cwd = value.get("cwd")
    raw_args = value.get("args")
    if not isinstance(raw_cwd, str) or not raw_cwd:
        raise ValueError("cwd must be a non-empty string")
    cwd = Path(raw_cwd)
    if not cwd.is_absolute() or not cwd.is_dir():
        raise ValueError(f"cwd must be an existing absolute directory: {cwd}")
    if not isinstance(raw_args, list) or not raw_args or not all(isinstance(item, str) for item in raw_args):
        raise ValueError("args must be a non-empty string array")
    if any("\x00" in item for item in raw_args):
        raise ValueError("args must not contain NUL bytes")
    return cwd, raw_args


def run_git(cwd: Path, args: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + f"Git host command timed out after {COMMAND_TIMEOUT_SECONDS}s\n",
        }


class GitHostServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str):
        super().__init__(address, GitHostHandler)
        self.token = token


class GitHostHandler(BaseHTTPRequestHandler):
    server: GitHostServer

    def log_message(self, format: str, *args: object) -> None:
        print(f"git-host: {format % args}", file=sys.stderr)

    def send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.token}"
        return hmac.compare_digest(supplied, expected)

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_json(404, {"error": "not found"})
            return
        try:
            validate_agent_socket(os.environ.get("SSH_AUTH_SOCK"))
            agent_state = "available"
        except ValueError:
            agent_state = "unavailable"
        self.send_json(200, {"status": "ready", "ssh_agent": agent_state})

    def do_POST(self) -> None:
        if self.path != "/v1/git":
            self.send_json(404, {"error": "not found"})
            return
        if not self.authorized():
            self.send_json(403, {"error": "invalid Git host capability"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length))
            cwd, args = validate_request(payload)
            result = run_git(cwd, args)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})
            return
        self.send_json(200, result)


def request_json(url: str, token: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=COMMAND_TIMEOUT_SECONDS + 30) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError("Git host returned an invalid response")
    return value


def client_git(args: argparse.Namespace) -> int:
    git_args = list(args.git_args)
    if git_args and git_args[0] == "--":
        git_args = git_args[1:]
    if not git_args:
        fail("usage: harr git <git-arguments>")
    secret_file = Path(args.secret_file).expanduser()
    try:
        token = load_secret(secret_file)
        result = request_json(
            endpoint().rstrip("/") + "/v1/git",
            token,
            {"cwd": str(Path.cwd()), "args": git_args},
        )
    except urllib.error.URLError as exc:
        fail(f"Harr Git host service is unavailable at {endpoint()}: {exc.reason}; reinstall/start Harr from a terminal")
    except RuntimeError as exc:
        fail(str(exc))
    if "error" in result:
        fail(str(result["error"]))
    sys.stdout.write(str(result.get("stdout", "")))
    sys.stderr.write(str(result.get("stderr", "")))
    return int(result.get("exit_code", 1))


def client_health(args: argparse.Namespace) -> int:
    try:
        result = request_json(endpoint().rstrip("/") + "/health", None)
    except (urllib.error.URLError, RuntimeError, json.JSONDecodeError):
        print("unreachable")
        return 1
    status = str(result.get("status", "invalid"))
    agent = str(result.get("ssh_agent", "unknown"))
    print(f"{status} (ssh-agent: {agent})")
    return 0 if result.get("status") == "ready" else 1


def serve(args: argparse.Namespace) -> int:
    token = load_secret(Path(args.secret_file).expanduser())
    server = GitHostServer((args.host, args.port), token)
    print(f"Harr Git host service listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Harr host Git execution bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--secret-file", default=str(default_secret_file()))

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--host", default=DEFAULT_HOST)
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_serve.add_argument("--secret-file", default=str(default_secret_file()))

    p_client = sub.add_parser("client")
    p_client.add_argument("--secret-file", default=str(default_secret_file()))
    p_client.add_argument("git_args", nargs=argparse.REMAINDER)

    sub.add_parser("health")

    args = parser.parse_args()
    if args.command == "init":
        ensure_secret(Path(args.secret_file).expanduser())
        return 0
    if args.command == "serve":
        return serve(args)
    if args.command == "client":
        return client_git(args)
    if args.command == "health":
        return client_health(args)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        fail(str(exc))
