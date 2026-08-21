#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def load_gitlab(registry: Path) -> dict:
    data = json.loads(registry.read_text(encoding="utf-8"))
    for server in data.get("servers", []):
        if server.get("name") == "gitlab":
            return server
    fail("GitLab MCP is not enabled in the Harr effective registry")


def env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        fail(f"GitLab runtime config missing: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def gitlab_secret_path(server: dict, secrets_dir: Path) -> Path:
    secrets = server.get("secrets") or []
    for item in secrets:
        if item.get("name") == "gitlab" and item.get("file"):
            path = secrets_dir / str(item["file"])
            if not path.is_file() or path.stat().st_size == 0:
                fail(f"GitLab PAT is not configured; run `harr secret set gitlab` ({path})")
            return path
    fail("GitLab secret metadata is missing from the Harr registry")


def api_base(api_url: str) -> tuple[str, str]:
    parsed = urlsplit(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        fail(f"invalid GITLAB_API_URL: {api_url!r}")
    return parsed.scheme, parsed.netloc


def remote_host_and_rewrite(remote_url: str, api_url: str) -> tuple[str, str | None, str | None]:
    scheme, api_netloc = api_base(api_url)
    api_host = urlsplit(f"{scheme}://{api_netloc}").hostname
    assert api_host is not None

    if remote_url.startswith(("http://", "https://", "ssh://")):
        parsed = urlsplit(remote_url)
        host = parsed.hostname
        if not host:
            fail(f"cannot determine GitLab host from remote URL: {remote_url}")
        if host.lower() != api_host.lower():
            fail(f"refusing to send Harr GitLab credentials to remote host {host!r}; configured GitLab host is {api_host!r}")
        if parsed.scheme in {"http", "https"}:
            return host, None, None
        user = f"{parsed.username}@" if parsed.username else ""
        port = f":{parsed.port}" if parsed.port else ""
        old_prefix = f"ssh://{user}{host}{port}/"
        return host, old_prefix, f"{scheme}://{api_netloc}/"

    match = re.match(r"^(?:(?P<user>[^@/:]+)@)?(?P<host>[^:/]+):(?P<path>.+)$", remote_url)
    if not match:
        fail(f"unsupported Git remote URL for Harr HTTPS fallback: {remote_url}")
    host = match.group("host")
    if host.lower() != api_host.lower():
        fail(f"refusing to send Harr GitLab credentials to remote host {host!r}; configured GitLab host is {api_host!r}")
    user_prefix = f"{match.group('user')}@" if match.group("user") else ""
    return host, f"{user_prefix}{host}:", f"{scheme}://{api_netloc}/"


def first_remote_arg(push_args: list[str]) -> str | None:
    takes_value = {"--receive-pack", "--exec", "-o", "--push-option"}
    skip = False
    for arg in push_args:
        if skip:
            skip = False
            continue
        if arg == "--":
            continue
        if arg in takes_value:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.strip()


def resolve_remote(push_args: list[str]) -> str:
    candidate = first_remote_arg(push_args)
    if candidate:
        return candidate
    branch = git_output("branch", "--show-current")
    if branch:
        configured = subprocess.run(
            ["git", "config", "--get", f"branch.{branch}.remote"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if configured.returncode == 0 and configured.stdout.strip():
            return configured.stdout.strip()
    return "origin"


def make_askpass(script: Path, python: str, directory: Path) -> Path:
    if os.name == "nt":
        path = directory / "harr-gitlab-askpass.cmd"
        path.write_text(f'@echo off\r\n"{python}" "{script}" askpass %*\r\n', encoding="utf-8")
    else:
        path = directory / "harr-gitlab-askpass"
        path.write_text(f"#!/bin/sh\nexec {shlex.quote(python)} {shlex.quote(str(script))} askpass \"$@\"\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def askpass(prompt: str) -> int:
    secret_path = os.environ.get("HARR_GITLAB_PAT_FILE")
    if not secret_path:
        print("Harr GitLab askpass invoked without HARR_GITLAB_PAT_FILE", file=sys.stderr)
        return 2
    low = prompt.lower()
    if "username" in low:
        print("oauth2")
        return 0
    if "password" in low:
        token = Path(secret_path).read_text(encoding="utf-8").strip()
        if not token:
            return 2
        print(token)
        return 0
    print("Harr GitLab askpass received an unexpected prompt", file=sys.stderr)
    return 2


def push(args: argparse.Namespace) -> int:
    registry = Path(args.registry).expanduser()
    config_dir = Path(args.config_dir).expanduser()
    secrets_dir = Path(args.secrets_dir).expanduser()
    server = load_gitlab(registry)
    secret = gitlab_secret_path(server, secrets_dir)
    config = env_file(config_dir / "gitlab.env")
    api_url = config.get("GITLAB_API_URL")
    if not api_url:
        fail(f"GITLAB_API_URL is missing from {config_dir / 'gitlab.env'}")

    remote = resolve_remote(args.git_args)
    try:
        remote_url = git_output("remote", "get-url", remote)
    except subprocess.CalledProcessError as exc:
        fail(f"cannot resolve Git remote {remote!r}; pass a configured remote such as `origin`"); raise exc
    _host, old_prefix, https_prefix = remote_host_and_rewrite(remote_url, api_url)

    with tempfile.TemporaryDirectory(prefix="harr-gitlab-askpass-") as tmp_raw:
        tmp = Path(tmp_raw)
        askpass_path = make_askpass(Path(__file__).resolve(), sys.executable, tmp)
        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(askpass_path)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["HARR_GITLAB_PAT_FILE"] = str(secret)

        command = ["git", "-c", "credential.helper="]
        if old_prefix and https_prefix:
            command += ["-c", f"url.{https_prefix}.insteadOf={old_prefix}"]
        command += ["push", *args.git_args]
        result = subprocess.run(command, env=env)
        if result.returncode != 0:
            print(
                "Harr GitLab HTTPS push failed. Ensure the stored token is a personal token with `api` "
                "or another token with Git-over-HTTPS `write_repository` permission, and that the GitLab user can push this branch.",
                file=sys.stderr,
            )
        return result.returncode


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "askpass":
        return askpass(sys.argv[2] if len(sys.argv) > 2 else "")

    parser = argparse.ArgumentParser(description="Harr secure GitLab HTTPS Git transport")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("push")
    p.add_argument("--registry", required=True)
    p.add_argument("--config-dir", required=True)
    p.add_argument("--secrets-dir", required=True)
    p.add_argument("git_args", nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    if ns.command == "push":
        if ns.git_args and ns.git_args[0] == "--":
            ns.git_args = ns.git_args[1:]
        return push(ns)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
