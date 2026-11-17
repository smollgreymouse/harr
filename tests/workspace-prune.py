#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "common" / "mcp" / "manager.py"
SPEC = importlib.util.spec_from_file_location("harr_manager", MANAGER_PATH)
assert SPEC and SPEC.loader
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def store_path(directory: Path, primary: Path) -> Path:
    digest = hashlib.sha256(str(primary.resolve()).encode("utf-8")).hexdigest()[:24]
    return directory / f"{digest}.json"


def write_store(
    directory: Path,
    primary: Path,
    *,
    workspace_id: str,
    git_dir: Path | None = None,
    additional: list[str] | None = None,
    metadata: bool = True,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = store_path(directory, primary)
    state = {
        "id": workspace_id,
        "revision": 1,
        "primary": str(primary.resolve()),
        "additional": additional or [],
    }
    store.write_text(json.dumps(state), encoding="utf-8")
    store.chmod(0o600)
    lock = Path(f"{store}.lock")
    lock.touch(mode=0o600)
    if metadata:
        binding = {"git_dir": str(git_dir)} if git_dir is not None else {}
        value = {
            "schema_version": 2,
            "versions": [{
                "workspace_id": workspace_id,
                "revision": 1,
                "checkout_bindings": {str(primary.resolve()): binding} if binding else {},
            }],
        }
        meta = Path(f"{store}.meta")
        meta.write_text(json.dumps(value), encoding="utf-8")
        meta.chmod(0o600)
    return store


def run_prune(config: Path, *, full_reset: bool, dry_run: bool = False) -> tuple[int, dict]:
    command = [
        sys.executable, str(MANAGER_PATH),
        "--registry", str(ROOT / "common" / "mcp" / "registry.json"),
        "workspace", "prune",
    ]
    if full_reset:
        command.append("--all")
    if dry_run:
        command.append("--dry-run")
    command.extend(["--real", sys.executable])
    env = os.environ.copy()
    env["HARR_CONFIG_DIR"] = str(config)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError((result.returncode, result.stdout, result.stderr)) from exc
    return result.returncode, payload


with tempfile.TemporaryDirectory(prefix="harr-workspace-prune-") as raw:
    base = Path(raw)
    config = base / "config"
    directory = config / "workspaces"
    directory.mkdir(parents=True, mode=0o700)
    os.environ["HARR_CONFIG_DIR"] = str(config)

    # A deleted checkout is pruned only when its saved Git admin directory is
    # gone too. Dry-run reports the candidate and leaves all three files intact.
    missing_primary = base / "deleted-worktree"
    missing_git_dir = base / "deleted-git-admin"
    stale = write_store(directory, missing_primary, workspace_id="stale", git_dir=missing_git_dir)
    code, preview = run_prune(config, full_reset=False, dry_run=True)
    assert code == 0
    stale_preview = next(item for item in preview["results"] if item["store"] == str(stale))
    assert stale_preview["status"] == "planned"
    assert stale_preview["reason"] == "primary-and-git-admin-missing"
    assert stale.exists() and Path(f"{stale}.meta").exists() and Path(f"{stale}.lock").exists()

    # A moved worktree's old path is absent while its Git administrative
    # directory remains; ordinary prune must preserve that registration.
    moved_primary = base / "moved-from-here"
    moved_git_dir = base / "still-live-git-admin"
    moved_git_dir.mkdir()
    moved = write_store(directory, moved_primary, workspace_id="moved", git_dir=moved_git_dir)
    active_primary = base / "same-path-new-filesystem-identity"
    active_primary.mkdir()
    stale_additional = base / "deleted-additional-root"
    active = write_store(
        directory, active_primary, workspace_id="active", git_dir=base / "old-git-admin",
        additional=[str(stale_additional)],
    )

    # Sidecars without a JSON authority record are safe orphan cleanup targets.
    orphan = "a" * 24 + ".json"
    orphan_meta = directory / f"{orphan}.meta"
    orphan_lock = directory / f"{orphan}.lock"
    orphan_meta.write_text("{}", encoding="utf-8")
    orphan_lock.touch(mode=0o600)
    unknown = directory / "keep-me.txt"
    unknown.write_text("not a managed store member", encoding="utf-8")

    code, result = run_prune(config, full_reset=False)
    assert code == 0, result
    results = {item["store"]: item for item in result["results"]}
    assert results[str(stale)]["status"] == "removed"
    assert results[str(moved)]["status"] == "retained"
    assert results[str(moved)]["reason"] == "git-admin-directory-present"
    assert results[str(active)]["status"] == "retained"
    assert results[str(active)]["reason"] == "primary-path-present"
    assert json.loads(active.read_text(encoding="utf-8"))["additional"] == [str(stale_additional)]
    assert results[str(directory / orphan)]["status"] == "removed"
    assert not stale.exists() and not Path(f"{stale}.meta").exists() and not Path(f"{stale}.lock").exists()
    assert not orphan_meta.exists() and not orphan_lock.exists()
    assert moved.exists() and active.exists() and unknown.exists()

    # If deletion stops after authority JSON is gone, the next prune finishes
    # the orphaned sidecar cleanup.
    partial = write_store(directory, base / "partially-removed", workspace_id="partial")
    original_unlink = Path.unlink
    def fail_meta_once(path: Path, *args, **kwargs):
        if path == Path(f"{partial}.meta"):
            raise PermissionError("simulated sidecar delete failure")
        return original_unlink(path, *args, **kwargs)
    Path.unlink = fail_meta_once
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            try:
                manager.workspace_prune_command(type("Args", (), {
                    "full_reset": False, "dry_run": False, "paths": [],
                })())
            except SystemExit as exc:
                assert exc.code == 1
    finally:
        Path.unlink = original_unlink
    partial_result = json.loads(output.getvalue())
    partial_row = next(item for item in partial_result["results"] if item["store"] == str(partial))
    assert partial_row["status"] == "blocked" and partial_row["files"] == [partial.name]
    assert not partial.exists() and Path(f"{partial}.meta").exists() and Path(f"{partial}.lock").exists()
    code, result = run_prune(config, full_reset=False)
    assert code == 0
    assert not Path(f"{partial}.meta").exists() and not Path(f"{partial}.lock").exists()

    # An invalid store is retained by ordinary prune but can be removed by an
    # explicit full reset. The full reset remains previewable without changes.
    malformed = directory / ("b" * 24 + ".json")
    malformed.write_text("not json", encoding="utf-8")
    malformed.chmod(0o600)
    malformed_meta = Path(f"{malformed}.meta")
    malformed_meta.write_text("{}", encoding="utf-8")
    malformed_meta.chmod(0o600)
    code, result = run_prune(config, full_reset=False)
    assert code == 1
    assert next(item for item in result["results"] if item["store"] == str(malformed))["status"] == "blocked"
    code, preview = run_prune(config, full_reset=True, dry_run=True)
    assert code == 0 and all(item["status"] == "planned" for item in preview["results"])
    assert malformed.exists() and malformed_meta.exists()

    # A managed-name symlink blocks the entire full reset during preflight;
    # neither it nor its target is followed or partially removed.
    if os.name == "posix":
        outside = base / "outside.json"
        outside.write_text("keep", encoding="utf-8")
        unsafe = directory / ("c" * 24 + ".json")
        unsafe.symlink_to(outside)
        code, result = run_prune(config, full_reset=True)
        assert code == 1
        assert unsafe.is_symlink() and outside.read_text(encoding="utf-8") == "keep"
        assert malformed.exists() and active.exists() and moved.exists()
        unsafe.unlink()

    # A competing prune fails closed while a lifecycle lease is held.
    with manager.workspace_lifecycle_lock():
        code, busy = run_prune(config, full_reset=True)
        assert code == 1
        assert busy["results"][0]["status"] == "blocked"
        assert busy["results"][0]["reason"] == "busy"

    # Harr-managed strict LeanCTX keeps the shared lease through exec and until
    # the MCP process exits. Use a small workspace-admin-compatible fake binary.
    if os.name == "posix":
        repo = base / "live-repo"
        repo.mkdir()
        git(repo, "init", "-q")
        fake = base / "fake-lean-ctx"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys, time\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "if args and args[0]=='workspace-admin':\n"
            " op=args[1]; store=Path(args[2])\n"
            " if op=='create':\n"
            "  primary=str(Path(args[3]).resolve()); state={'id':'live','revision':1,'primary':primary,'additional':[]}\n"
            "  store.parent.mkdir(parents=True,exist_ok=True); store.write_text(json.dumps(state)); store.chmod(0o600)\n"
            "  Path(str(store)+'.lock').touch(mode=0o600)\n"
            "  meta={'schema_version':2,'versions':[{'workspace_id':'live','revision':1,'checkout_bindings':{primary:{'git_dir':str(Path(primary)/'.git')}}}]}\n"
            "  Path(str(store)+'.meta').write_text(json.dumps(meta)); Path(str(store)+'.meta').chmod(0o600)\n"
            " elif op in ('reconcile','show'):\n"
            "  state=json.loads(store.read_text()); state['checkout_bindings']={state['primary']:{'git_dir':str(Path(state['primary'])/'.git')}}\n"
            "  if op=='show': print(json.dumps(state))\n"
            " sys.exit(0)\n"
            "if args and args[0]=='mcp':\n"
            " print('mcp-ready',flush=True); time.sleep(1.5); sys.exit(0)\n"
            "sys.exit(2)\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        env = os.environ.copy()
        env["HARR_CONFIG_DIR"] = str(config)
        env.pop("HARR_WORKSPACE_MODE", None)
        live = subprocess.Popen(
            [sys.executable, str(MANAGER_PATH), "--registry", str(ROOT / "common" / "mcp" / "registry.json"),
             "exec-leanctx", str(fake), "--", "mcp"],
            cwd=repo, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert live.stdout is not None
        assert live.stdout.readline().strip() == "mcp-ready"
        code, busy = run_prune(config, full_reset=True)
        assert code == 1 and busy["results"][0]["reason"] == "busy"
        assert live.wait(timeout=10) == 0

    # Full reset clears all managed registrations, including a changed checkout
    # identity and malformed JSON, without touching unrelated files.
    code, result = run_prune(config, full_reset=True)
    assert code == 0 and result["summary"]["removed"] >= 3
    assert list(directory.iterdir()) == [unknown]
    assert unknown.read_text(encoding="utf-8") == "not a managed store member"
    assert (config / "workspace-lifecycle.lock").is_file()

print("PASS: Workspace prune protects moved/active checkouts, coordinates lifecycle locks, and cleans managed triplets")
