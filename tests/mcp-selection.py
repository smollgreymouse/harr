#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "common" / "mcp" / "selector.py"
MANAGER = ROOT / "common" / "mcp" / "manager.py"
ASSETS = ROOT / "common" / "mcp" / "assets.py"
CATALOG = ROOT / "common" / "mcp" / "registry.json"
BASE = ROOT / "common" / "leanctx" / "config.base.toml"
POLICY = ROOT / "common" / "policy" / "tool-routing.template.md"
SKILL = ROOT / "common" / "skills" / "harr"


def output(*args: object) -> str:
    return subprocess.run(
        [sys.executable, *map(str, args)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


def run(*args: object) -> None:
    output(*args)


def names(path: Path) -> list[str]:
    return [item["name"] for item in json.loads(path.read_text(encoding="utf-8"))["servers"]]


def check(spec: str, expected: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        selection = tmp / "selection.json"
        effective = tmp / "effective.json"
        run(SELECTOR, "--catalog", CATALOG, "--selection", selection, "--effective", effective, "--spec", spec)
        assert names(effective) == expected, (spec, names(effective))
        saved = json.loads(selection.read_text(encoding="utf-8"))
        assert saved == {"schema": 1, "enabled": expected}

        package = json.loads(output(MANAGER, "--registry", effective, "npm-package-json"))
        dependencies = package["dependencies"]
        assert ("@colbymchenry/codegraph" in dependencies) is True
        assert ("@zereight/mcp-gitlab" in dependencies) == ("gitlab" in expected)

        secret_rows = [json.loads(line) for line in output(MANAGER, "--registry", effective, "secrets").splitlines() if line]
        secret_names = [row["name"] for row in secret_rows]
        assert ("gitlab" in secret_names) == ("gitlab" in expected)
        assert ("grafana" in secret_names) == ("grafana" in expected)

        config_dir = tmp / "mcp-config"
        run(MANAGER, "--registry", effective, "install-configs", "--config-dir", config_dir)
        assert (config_dir / "gitlab.env").exists() == ("gitlab" in expected)
        assert (config_dir / "grafana.env").exists() == ("grafana" in expected)

        for platform in ("linux", "windows", "macos"):
            lean = tmp / f"lean-{platform}.toml"
            run(MANAGER, "--registry", effective, "render-leanctx", "--base", BASE, "--output", lean, "--platform", platform, "--runner-command", "harr-mcp-run")
            parsed = tomllib.loads(lean.read_text(encoding="utf-8"))
            assert parsed["gateway"]["top_n"] == 3
            assert "harr" in parsed["shell_allowlist_extra"]
            assert [item["name"] for item in parsed["gateway"]["servers"]] == expected

        filtered_policy = tmp / "policy.md"
        run(ASSETS, "filter-text", "--catalog", CATALOG, "--registry", effective, "--input", POLICY, "--output", filtered_policy)
        policy = filtered_policy.read_text(encoding="utf-8")
        assert "codegraph::codegraph_explore" in policy
        assert ("GitLab API operations" in policy) == ("gitlab" in expected)
        assert ("gitlab::create_merge_request" in policy) == ("gitlab" in expected)
        assert ("Creating a GitLab MR is a combined Git + GitLab workflow" in policy) == ("gitlab" in expected)
        assert ("harr git push [git-push-options] [remote] [refspec...]" in policy) == ("gitlab" in expected)
        assert ("host-independent secure HTTPS bridge" in policy) == ("gitlab" in expected)
        assert ("Only if both normal Git transport and `harr git push` are unavailable" in policy) == ("gitlab" in expected)
        assert ("MR author is the authenticated GitLab identity" in policy) == ("gitlab" in expected)
        assert ("Grafana dashboard work" in policy) == ("grafana" in expected)
        assert "<!-- harr-mcp:" not in policy

        filtered_skill = tmp / "harr-skill"
        run(ASSETS, "filter-skill", "--catalog", CATALOG, "--registry", effective, "--source", SKILL, "--output", filtered_skill)
        skill = (filtered_skill / "SKILL.md").read_text(encoding="utf-8")
        assert ("harr secret set gitlab" in skill) == ("gitlab" in expected)
        assert ("harr secret set grafana" in skill) == ("grafana" in expected)
        gitlab_ref = filtered_skill / "references" / "gitlab.md"
        assert gitlab_ref.exists() == ("gitlab" in expected)
        if gitlab_ref.exists():
            gitlab_text = gitlab_ref.read_text(encoding="utf-8")
            assert "gitlab::create_merge_request" in gitlab_text
            assert "harr git push -u <remote> <branch>" in gitlab_text
            assert "host-independent Harr capability" in gitlab_text
            assert "GIT_ASKPASS" in gitlab_text
            assert "repository-file deletion is not exposed" in gitlab_text
            assert "GitLab MR author is the authenticated GitLab identity" in gitlab_text
            assert "GITLAB_PERMISSION_MODE=full" in gitlab_text
        assert (filtered_skill / "references" / "grafana.md").exists() == ("grafana" in expected)
        assert "<!-- harr-mcp:" not in skill


catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
servers = {item["name"]: item for item in catalog["servers"]}
assert servers["codegraph"]["required"] is True
assert servers["gitlab"]["required"] is False
assert servers["grafana"]["required"] is False

check("none", ["codegraph"])
check("gitlab", ["codegraph", "gitlab"])
check("all", ["codegraph", "gitlab", "grafana"])
print("cross-platform MCP selection: PASS")
