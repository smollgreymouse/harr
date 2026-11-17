"""Project MCP overlay: untrusted repository manifest plus user-local trust.

Fail-closed by construction: only the whitelisted fields below exist, so a
manifest can never carry secrets, commands, args, or environment overrides.
Endpoints are HTTPS-only (explicit loopback HTTP exception), so repository
input cannot silently retarget a credential. Trust is a user-local digest
approval; a changed manifest is untrusted again by definition.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

MANIFEST_NAME = ".harr/mcp.json"
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
MEMENTO_ID_RE = re.compile(r"^mcp/[A-Za-z0-9][A-Za-z0-9/_.-]{0,127}$")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
TRUST_FILE_NAME = "mcp-trust.json"


class ProjectOverlayError(Exception):
    """Manifest/trust failure. Messages carry safe ids only — never secrets."""


def find_manifest(start: Path) -> Path | None:
    """Nearest ancestor manifest, or None. No Git commands; cwd-affine."""
    start = Path(start).resolve()
    for candidate in (start, *start.parents):
        path = candidate / MANIFEST_NAME
        if path.is_file():
            return path
    return None


def project_key(root: Path) -> str:
    """Stable, non-reversible key of the resolved project root."""
    return hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:16]


def _require_object(value: object, where: str) -> dict:
    if not isinstance(value, dict):
        raise ProjectOverlayError(f"{where} must be an object")
    return value


def _reject_unknown_fields(mapping: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ProjectOverlayError(f"{where} has unknown fields: {', '.join(unknown)}")


def _require_name(name: object, where: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ProjectOverlayError(f"{where} has an invalid name: {name!r}")
    return name


def validate_url(url: object, where: str) -> str:
    """HTTPS required; explicit loopback HTTP is the only exception."""
    if not isinstance(url, str) or not url:
        raise ProjectOverlayError(f"{where} endpoint is missing")
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise ProjectOverlayError(f"{where} endpoint must not embed credentials")
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and host:
        return url
    if parts.scheme == "http" and host in LOOPBACK_HOSTS:
        return url
    raise ProjectOverlayError(f"{where} endpoint must be HTTPS (loopback HTTP exception): rejected")


def load_manifest(path: Path) -> dict:
    """Parse and validate the manifest. Any deviation is fail-closed."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProjectOverlayError(f"manifest is unreadable: {exc}") from exc
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectOverlayError(f"manifest is not valid JSON: {exc}") from exc
    doc = _require_object(doc, "manifest")
    _reject_unknown_fields(doc, {"schema", "instances", "extensions"}, "manifest")
    if doc.get("schema") != 1 or isinstance(doc.get("schema"), bool):
        raise ProjectOverlayError("manifest schema must be 1")

    instances: dict[str, dict] = {}
    for name, entry in _require_object(doc.get("instances", {}), "instances").items():
        _require_name(name, "instances")
        where = f"instance {name}"
        entry = _require_object(entry, where)
        _reject_unknown_fields(entry, {"provider", "enabled", "profile"}, where)
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ProjectOverlayError(f"{where} enabled must be a boolean")
        provider = entry.get("provider")
        profile = entry.get("profile")
        if profile is not None and (not isinstance(profile, str) or not PROFILE_ID_RE.match(profile)):
            raise ProjectOverlayError(f"{where} has an invalid profile id: {profile!r}")
        if provider is None:
            if not enabled:
                # Disable-only entry: turn off an inherited instance.
                instances[name] = {"name": name, "enabled": False, "provider": None, "profile": None}
                continue
            raise ProjectOverlayError(f"{where} must select a provider")
        if not isinstance(provider, str) or not NAME_RE.match(provider):
            raise ProjectOverlayError(f"{where} has an invalid provider: {provider!r}")
        instances[name] = {
            "name": name,
            "enabled": enabled,
            "provider": provider,
            "profile": profile,
        }

    extensions: dict[str, dict] = {}
    for name, entry in _require_object(doc.get("extensions", {}), "extensions").items():
        _require_name(name, "extensions")
        where = f"extension {name}"
        entry = _require_object(entry, where)
        _reject_unknown_fields(entry, {"transport", "url"}, where)
        if entry.get("transport") != "http":
            raise ProjectOverlayError(f"{where}: only http extensions are supported in v1")
        extensions[name] = {
            "name": name,
            "transport": "http",
            "url": validate_url(entry.get("url"), where),
        }

    overlap = sorted(set(instances) & set(extensions))
    if overlap:
        raise ProjectOverlayError(f"instance/extension name conflict: {', '.join(overlap)}")
    # The manifest lives in <project>/.harr/mcp.json; the project root is one
    # level above the .harr directory (defensive fallback for other layouts).
    manifest_root = path.parent.parent if path.parent.name == ".harr" else path.parent
    return {
        "schema": 1,
        "instances": instances,
        "extensions": extensions,
        "path": str(path),
        "root": str(manifest_root),
        "digest": hashlib.sha256(raw).hexdigest(),
    }


def trust_path(root: Path, harr_config: Path) -> Path:
    return Path(harr_config) / "projects" / project_key(root) / TRUST_FILE_NAME


def read_trust(root: Path, harr_config: Path) -> dict | None:
    path = trust_path(root, harr_config)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def trusted_digest(root: Path, harr_config: Path) -> str | None:
    doc = read_trust(root, harr_config)
    if not doc:
        return None
    digest = doc.get("digest")
    if isinstance(digest, str) and len(digest) == 64:
        return digest
    return None


def is_trusted(root: Path, harr_config: Path, manifest_digest: str) -> bool:
    return trusted_digest(root, harr_config) == manifest_digest


def approve(root: Path, harr_config: Path, digest: str) -> None:
    """Record a user-local approval for exactly this manifest digest."""
    if not isinstance(digest, str) or len(digest) != 64:
        raise ProjectOverlayError("refusing to approve without a manifest digest")
    path = trust_path(root, harr_config)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.parent / f".{TRUST_FILE_NAME}.tmp"
    payload = {"schema": 1, "digest": digest, "project": project_key(root)}
    tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def revoke(root: Path, harr_config: Path) -> bool:
    path = trust_path(root, harr_config)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
