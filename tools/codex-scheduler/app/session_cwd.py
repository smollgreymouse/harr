#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


class SessionResolutionError(RuntimeError):
    pass


def _codex_home(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _session_meta(path: Path, session: str) -> tuple[Path, str | None] | None:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            for index, line in enumerate(fh):
                if index >= 128:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    return None
                nested = payload.get("meta")
                meta = nested if isinstance(nested, dict) else payload
                ids = {str(meta[key]) for key in ("id", "session_id") if meta.get(key) is not None}
                if ids and session not in ids:
                    return None
                cwd = meta.get("cwd")
                if not isinstance(cwd, str) or not cwd.strip():
                    raise SessionResolutionError(f"session metadata has no cwd: {path}")
                candidate = Path(cwd).expanduser()
                if not candidate.is_absolute():
                    raise SessionResolutionError(
                        f"session cwd is relative and cannot be resumed safely: {cwd!r} ({path})"
                    )
                version = meta.get("cli_version")
                return candidate, str(version) if version is not None else None
    except OSError as exc:
        raise SessionResolutionError(f"cannot read session rollout {path}: {exc}") from exc
    return None


def validate_git_worktree(cwd: Path) -> Path:
    try:
        resolved = cwd.resolve(strict=True)
    except OSError as exc:
        raise SessionResolutionError(f"saved session cwd does not exist: {cwd}") from exc
    if not resolved.is_dir():
        raise SessionResolutionError(f"saved session cwd is not a directory: {resolved}")
    try:
        probe = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SessionResolutionError("git executable not found; cannot verify saved session cwd") from exc
    if probe.returncode != 0:
        detail = probe.stderr.strip() or "not inside a Git worktree"
        raise SessionResolutionError(f"saved session cwd is not a usable Git worktree: {resolved}: {detail}")
    return resolved


def resolve_session_cwd(
    session: str,
    *,
    codex_home: Path | None = None,
    require_git: bool = True,
) -> Path:
    session = session.strip()
    if not session or "/" in session or "\\" in session:
        raise SessionResolutionError(f"invalid session id: {session!r}")

    home = _codex_home(codex_home)
    roots = [home / "sessions", home / "archived_sessions"]
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(root.rglob(f"*-{session}.jsonl"))
    if not candidates:
        raise SessionResolutionError(
            f"cannot find local rollout for session {session} under {home}; "
            "Codex may have changed its local session format"
        )

    found: list[tuple[Path, Path, str | None]] = []
    for rollout in sorted(set(candidates)):
        result = _session_meta(rollout, session)
        if result is None:
            continue
        raw_cwd, version = result
        try:
            canonical = raw_cwd.resolve(strict=True)
        except OSError as exc:
            raise SessionResolutionError(
                f"session {session} points to missing cwd {raw_cwd} in {rollout}"
            ) from exc
        found.append((rollout, canonical, version))

    if not found:
        raise SessionResolutionError(
            f"rollout file(s) for session {session} were found, but compatible session_meta.cwd was not; "
            "refusing to guess after a possible Codex format change"
        )

    unique = {str(cwd) for _, cwd, _ in found}
    if len(unique) != 1:
        details = "; ".join(f"{rollout}: {cwd}" for rollout, cwd, _ in found)
        raise SessionResolutionError(f"conflicting cwd values for session {session}: {details}")

    cwd = found[0][1]
    return validate_git_worktree(cwd) if require_git else cwd


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and validate the saved cwd of a local Codex session")
    parser.add_argument("--session", required=True)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--no-git-check", action="store_true")
    args = parser.parse_args()
    try:
        cwd = resolve_session_cwd(
            args.session,
            codex_home=args.codex_home,
            require_git=not args.no_git_check,
        )
    except SessionResolutionError as exc:
        print(f"codex-session-cwd: {exc}", file=sys.stderr)
        return 2
    print(cwd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
