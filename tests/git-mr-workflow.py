#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    remote = root / "remote.git"
    work = root / "work"
    remote.mkdir()
    work.mkdir()
    git(remote, "init", "--bare", "-q")
    git(work, "init", "-q")
    git(work, "symbolic-ref", "HEAD", "refs/heads/master")
    git(work, "config", "user.name", "Harr Test")
    git(work, "config", "user.email", "harr@example.invalid")

    tracked = work / "tracked.txt"
    tracked.write_text("master\n", encoding="utf-8")
    git(work, "add", "tracked.txt")
    git(work, "commit", "-q", "-m", "master")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/master")
    master_sha = git(work, "rev-parse", "HEAD")

    git(work, "checkout", "-q", "-b", "topic")
    tracked.write_text("topic\n", encoding="utf-8")
    git(work, "commit", "-q", "-am", "topic")
    topic_sha = git(work, "rev-parse", "HEAD")

    # Regression setup: the feature branch incorrectly tracks the target branch.
    git(work, "config", "branch.topic.remote", "origin")
    git(work, "config", "branch.topic.merge", "refs/heads/master")

    # This is the exact standard-Git sequence required by Harr policy.
    git(work, "push", "--set-upstream", "origin", "HEAD:refs/heads/topic")
    topic_remote = git(work, "ls-remote", "origin", "refs/heads/topic").split()[0]
    master_remote = git(work, "ls-remote", "origin", "refs/heads/master").split()[0]

    assert topic_remote == topic_sha
    assert master_remote == master_sha
    assert git(work, "config", "--get", "branch.topic.remote") == "origin"
    assert git(work, "config", "--get", "branch.topic.merge") == "refs/heads/topic"

print("GitLab MR Git workflow: PASS")
