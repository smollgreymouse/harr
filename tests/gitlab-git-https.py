#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "common" / "gitlab" / "git_https.py"
spec = importlib.util.spec_from_file_location("harr_git_https", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

api = "https://gitlab.example.test/api/v4"
assert mod.remote_host_and_rewrite("git@gitlab.example.test:group/proj.git", api) == (
    "gitlab.example.test",
    "git@gitlab.example.test:",
    "https://gitlab.example.test/",
)
assert mod.remote_host_and_rewrite("ssh://git@gitlab.example.test/group/proj.git", api) == (
    "gitlab.example.test",
    "ssh://git@gitlab.example.test/",
    "https://gitlab.example.test/",
)
assert mod.remote_host_and_rewrite("https://gitlab.example.test/group/proj.git", api) == (
    "gitlab.example.test",
    None,
    None,
)
assert mod.first_remote_arg(["-u", "origin", "topic"]) == "origin"
assert mod.first_remote_arg(["--force-with-lease", "origin", "topic"]) == "origin"
assert mod.publish_refspec("ADSDSP-7737-final-prerank-cleanup") == "HEAD:refs/heads/ADSDSP-7737-final-prerank-cleanup"

try:
    mod.remote_host_and_rewrite("git@evil.example:group/proj.git", api)
except RuntimeError as exc:
    assert "refusing to send Harr GitLab credentials" in str(exc)
else:
    raise AssertionError("cross-host credential exfiltration guard missing")

# Regression: a feature branch may accidentally still track origin/master.
# MR publication must derive the source name from local HEAD, never upstream.
with tempfile.TemporaryDirectory() as tmp_raw:
    repo = Path(tmp_raw) / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/ADSDSP-7737-final-prerank-cleanup"], cwd=repo, check=True)
    subprocess.run(["git", "config", "branch.ADSDSP-7737-final-prerank-cleanup.remote", "origin"], cwd=repo, check=True)
    subprocess.run(["git", "config", "branch.ADSDSP-7737-final-prerank-cleanup.merge", "refs/heads/master"], cwd=repo, check=True)
    old_cwd = Path.cwd()
    os.chdir(repo)
    try:
        branch = mod.current_branch()
        assert branch == "ADSDSP-7737-final-prerank-cleanup"
        assert mod.publish_refspec(branch) == "HEAD:refs/heads/ADSDSP-7737-final-prerank-cleanup"
        assert subprocess.run(
            ["git", "config", "--get", f"branch.{branch}.merge"],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip() == "refs/heads/master"
    finally:
        os.chdir(old_cwd)

with tempfile.TemporaryDirectory() as tmp_raw:
    secret = Path(tmp_raw) / "pat"
    secret.write_text("glpat-test-secret\n", encoding="utf-8")
    old = os.environ.get("HARR_GITLAB_PAT_FILE")
    os.environ["HARR_GITLAB_PAT_FILE"] = str(secret)
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert mod.askpass("Username for 'https://gitlab.example.test':") == 0
        assert out.getvalue().strip() == "oauth2"

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert mod.askpass("Password for 'https://oauth2@gitlab.example.test':") == 0
        assert out.getvalue().strip() == "glpat-test-secret"
    finally:
        if old is None:
            os.environ.pop("HARR_GITLAB_PAT_FILE", None)
        else:
            os.environ["HARR_GITLAB_PAT_FILE"] = old

print("GitLab HTTPS Git transport: PASS")
