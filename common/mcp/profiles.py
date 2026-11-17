"""User-local credential profiles for provider instances.

A profile is a binding record — stable id, provider, approved endpoint, secret
reference (never the bytes), state, and the explicit list of projects allowed
to use it. Rotation happens in the secret store (`harr secret set`); the
reference stays stable, so a rotated value invalidates downstream sessions
without touching this record. `disable` blocks new sessions from using the
profile (fail-closed at render time).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import project_overlay

PROJECT_KEY_RE = re.compile(r"^[0-9a-f]{16}$")


class ProfileError(project_overlay.ProjectOverlayError):
    """Profile store failure. Messages carry safe ids only — never secrets."""


def profiles_dir(harr_config: Path) -> Path:
    path = Path(harr_config) / "mcp-profiles"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def profile_path(directory: Path, profile_id: str) -> Path:
    if not isinstance(profile_id, str) or not project_overlay.PROFILE_ID_RE.match(profile_id):
        raise ProfileError(f"invalid profile id: {profile_id!r}")
    return Path(directory) / f"{profile_id}.json"


def _validate_profile(profile: dict) -> None:
    profile_id = profile.get("id")
    if not isinstance(profile_id, str) or not project_overlay.PROFILE_ID_RE.match(profile_id):
        raise ProfileError(f"invalid profile id: {profile_id!r}")
    if not isinstance(profile.get("provider"), str) or not project_overlay.NAME_RE.match(profile["provider"]):
        raise ProfileError(f"profile {profile_id}: provider must be a Harr provider id")
    kind = profile.get("kind")
    if kind not in {"http", "stdio"}:
        raise ProfileError(f"profile {profile_id}: kind must be http or stdio")
    endpoint = profile.get("endpoint")
    if kind == "http":
        project_overlay.validate_url(endpoint, f"profile {profile_id}")
    elif endpoint is not None:
        raise ProfileError(f"profile {profile_id}: stdio profiles must not carry an endpoint")
    state = profile.get("state")
    if state not in {"enabled", "disabled"}:
        raise ProfileError(f"profile {profile_id}: state must be enabled or disabled")
    secret = profile.get("secret")
    if secret is not None:
        if not isinstance(secret, dict):
            raise ProfileError(f"profile {profile_id}: secret must be an object")
        unknown = sorted(set(secret) - {"file", "memento_id"})
        if unknown:
            raise ProfileError(f"profile {profile_id}: secret has unknown fields: {', '.join(unknown)}")
        filename = secret.get("file")
        if (
            not isinstance(filename, str)
            or not filename
            or filename in {".", ".."}
            or os.sep in filename
            or (os.altsep or "/") in filename
        ):
            raise ProfileError(f"profile {profile_id}: secret file must be a plain store file name")
        memento_id = secret.get("memento_id")
        if not isinstance(memento_id, str) or not project_overlay.MEMENTO_ID_RE.match(memento_id):
            raise ProfileError(f"profile {profile_id}: invalid memento id")
    bound = profile.get("bound_projects", [])
    if not isinstance(bound, list) or not all(isinstance(item, str) and PROJECT_KEY_RE.match(item) for item in bound):
        raise ProfileError(f"profile {profile_id}: bound_projects must be project keys")
    unknown = sorted(set(profile) - {"schema", "id", "provider", "kind", "endpoint", "secret", "state", "bound_projects"})
    if unknown:
        raise ProfileError(f"profile {profile_id} has unknown fields: {', '.join(unknown)}")


def write_profile(directory: Path, profile: dict) -> Path:
    """Validate + atomically store one profile (0600, same-dir tmp+rename)."""
    _validate_profile(profile)
    profile = dict(profile, schema=1)
    path = profile_path(directory, profile["id"])
    Path(directory).mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(profile, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def get_profile(directory: Path, profile_id: str) -> dict | None:
    path = profile_path(directory, profile_id)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict) or doc.get("id") != profile_id:
        return None
    return doc


def list_profiles(directory: Path) -> dict[str, dict]:
    directory = Path(directory)
    result: dict[str, dict] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("id"), str):
            result[doc["id"]] = doc
    return result


def set_state(directory: Path, profile_id: str, state: str) -> dict:
    if state not in {"enabled", "disabled"}:
        raise ProfileError("state must be enabled or disabled")
    profile = get_profile(directory, profile_id)
    if profile is None:
        raise ProfileError(f"unknown profile: {profile_id}")
    profile["state"] = state
    write_profile(directory, profile)
    return profile


def remove_profile(directory: Path, profile_id: str) -> bool:
    path = profile_path(directory, profile_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def profile_fingerprint(directory: Path) -> str:
    """Digest of (id, state) pairs — any state change invalidates the session."""
    pairs = sorted((pid, doc.get("state")) for pid, doc in list_profiles(directory).items())
    payload = json.dumps(pairs, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
