#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import Iterator, NoReturn
from urllib.parse import urlsplit


def fail(message: str) -> NoReturn:
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
        fail(f"unsupported Git remote URL for Harr HTTPS transport: {remote_url}")
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
    branch = current_branch(allow_detached=True)
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


def current_branch(*, allow_detached: bool = False) -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    branch = result.stdout.strip() if result.returncode == 0 else ""
    if branch:
        return branch
    if allow_detached:
        return ""
    fail("cannot publish an MR source branch from detached HEAD; check out a named local branch first")


def publish_refspec(branch: str) -> str:
    if not branch:
        fail("empty local branch name")
    check = subprocess.run(["git", "check-ref-format", "--branch", branch], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if check.returncode != 0:
        fail(f"invalid local branch name for publish: {branch!r}")
    return f"HEAD:refs/heads/{branch}"


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


@contextlib.contextmanager
def gitlab_transport(registry: Path, config_dir: Path, secrets_dir: Path, remote: str) -> Iterator[tuple[list[str], dict[str, str]]]:
    server = load_gitlab(registry)
    secret = gitlab_secret_path(server, secrets_dir)
    config = env_file(config_dir / "gitlab.env")
    api_url = config.get("GITLAB_API_URL")
    if not api_url:
        fail(f"GITLAB_API_URL is missing from {config_dir / 'gitlab.env'}")

    try:
        remote_url = git_output("remote", "get-url", remote)
    except subprocess.CalledProcessError:
        fail(f"cannot resolve Git remote {remote!r}; pass a configured remote such as `origin`")
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
        yield command, env


def common_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return (
        Path(args.registry).expanduser(),
        Path(args.config_dir).expanduser(),
        Path(args.secrets_dir).expanduser(),
    )


def push(args: argparse.Namespace) -> int:
    registry, config_dir, secrets_dir = common_paths(args)
    remote = resolve_remote(args.git_args)
    with gitlab_transport(registry, config_dir, secrets_dir, remote) as (base, env):
        result = subprocess.run([*base, "push", *args.git_args], env=env)
    if result.returncode != 0:
        print(
            "Harr GitLab HTTPS push failed. Ensure the stored token has Git-over-HTTPS write permission "
            "and that the GitLab user can push this branch.",
            file=sys.stderr,
        )
    return result.returncode


def publish(args: argparse.Namespace) -> int:
    registry, config_dir, secrets_dir = common_paths(args)
    remote = args.remote or "origin"
    branch = current_branch()
    refspec = publish_refspec(branch)
    local_sha = git_output("rev-parse", "HEAD")

    with gitlab_transport(registry, config_dir, secrets_dir, remote) as (base, env):
        result = subprocess.run([*base, "push", "-u", remote, refspec], env=env)
        if result.returncode != 0:
            print(
                "Harr GitLab branch publish failed. The current local branch was not published; "
                "check PAT repository-write permission and protected-branch policy.",
                file=sys.stderr,
            )
            return result.returncode

        probe = subprocess.run(
            [*base, "ls-remote", remote, f"refs/heads/{branch}"],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if probe.returncode != 0:
            print(probe.stderr, end="", file=sys.stderr)
            fail(f"published branch {remote}/{branch} but could not verify its remote SHA")

    remote_line = probe.stdout.strip().splitlines()
    remote_sha = remote_line[0].split()[0] if remote_line and remote_line[0].split() else ""
    if remote_sha != local_sha:
        fail(f"remote branch verification failed: local HEAD {local_sha} != {remote}/{branch} {remote_sha or '<missing>'}")

    # Never inherit a stale target-branch upstream (for example origin/master)
    # after publishing an MR source branch. Keep local tracking aligned with the
    # exact same-named remote branch that was just verified.
    subprocess.run(["git", "config", f"branch.{branch}.remote", remote], check=True)
    subprocess.run(["git", "config", f"branch.{branch}.merge", f"refs/heads/{branch}"], check=True)

    print(f"Published {branch} -> {remote}/{branch} at {local_sha}; upstream set to {remote}/{branch}.")
    return 0


def add_transport_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", required=True)
    parser.add_argument("--config-dir", required=True)
    parser.add_argument("--secrets-dir", required=True)


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "askpass":
        return askpass(sys.argv[2] if len(sys.argv) > 2 else "")

    parser = argparse.ArgumentParser(description="Harr secure GitLab HTTPS Git transport")
    sub = parser.add_subparsers(dest="command", required=True)

    p_push = sub.add_parser("push")
    add_transport_args(p_push)
    p_push.add_argument("git_args", nargs=argparse.REMAINDER)

    p_publish = sub.add_parser("publish")
    add_transport_args(p_publish)
    p_publish.add_argument("remote", nargs="?", default="origin")

    ns = parser.parse_args()
    if ns.command == "push":
        if ns.git_args and ns.git_args[0] == "--":
            ns.git_args = ns.git_args[1:]
        return push(ns)
    if ns.command == "publish":
        return publish(ns)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
