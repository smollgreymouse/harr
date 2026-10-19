"""Backend abstraction and configuration for Harr Einherjar."""

from __future__ import annotations

import json
import os
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

BACKEND_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PLACEHOLDER_RE = re.compile(r"{([^{}]+)}")
KNOWN_PLACEHOLDERS = frozenset({"prompt", "prompt_file", "session_id", "workspace"})


@dataclass
class BackendCapabilities:
    name: str
    source: str
    found: bool
    resumable: bool
    structured_events: bool
    progress_messages: bool
    prompt_stdin: bool = False
    prompt_file: bool = False
    cancel: bool = True
    working_directory: bool = True
    executable: str | None = None
    diagnostic: str | None = None

    def public_dict(self) -> dict:
        value = asdict(self)
        # Never expose a home-directory-resolved executable path. The command
        # name plus found/diagnostic is enough for planner-facing discovery.
        value.pop("executable", None)
        return value


@dataclass
class BackendStartRequest:
    prompt: str
    workspace_root: Path
    timeout_sec: int = 0
    harr_session_id: str | None = None


@dataclass
class BackendResumeRequest:
    prompt: str
    workspace_root: Path
    vendor_session_id: str
    timeout_sec: int = 0
    harr_session_id: str | None = None


class BackendAdapter(ABC):
    """Vendor boundary. Core owns lifecycle; adapters own CLI syntax/parsing."""

    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def probe(self) -> BackendCapabilities: ...

    @abstractmethod
    def start_command(self, request: BackendStartRequest) -> list[str]: ...

    @abstractmethod
    def resume_command(self, request: BackendResumeRequest) -> list[str]: ...

    @abstractmethod
    def extract_vendor_session_id(self, stdout: str, stderr: str) -> str | None: ...

    def initial_vendor_session_id(self, request: BackendStartRequest) -> str | None:
        """Return a caller-assigned vendor id when start syntax supports one."""
        return None

    def prepare_prompt(self, prompt: str) -> str:
        """Wrap a task with the Harr worker contract unless the adapter has a native system-prompt route."""
        from common.executor.protocol import WORKER_CONTRACT
        return WORKER_CONTRACT + "\n\n# Delegated task\n\n" + prompt

    def stdin_text(self, prompt: str) -> str | None:
        return None

    def final_output(self, stdout: str, stderr: str) -> str:
        return stdout.strip()

    def progress_messages(self, stdout: str) -> list[str]:
        return []

    def cleanup(self) -> None:
        pass


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else Path.home() / ".config"


def harr_config_dir() -> Path:
    return Path(os.environ.get("HARR_CONFIG_DIR", _config_home() / "harr"))


def einherjar_config_path() -> Path:
    return harr_config_dir() / "einherjar.json"


def _validate_template(name: str, field: str, value: object, *, resume: bool) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
        return [f"{name}.{field} must be a non-empty argv array of strings"]
    executable = value[0].lower()
    if PLACEHOLDER_RE.search(value[0]):
        errors.append(f"{name}.{field} executable must not contain placeholders")
    if Path(executable).name in {"einherjar", "einherjar_server.py"} or "einherjar_server.py" in " ".join(value).lower():
        errors.append(f"{name}.{field} must not invoke Einherjar recursively")
    placeholders: set[str] = set()
    for arg in value:
        placeholders.update(PLACEHOLDER_RE.findall(arg))
    unknown = placeholders - KNOWN_PLACEHOLDERS
    if unknown:
        errors.append(f"{name}.{field} contains unknown placeholders: {', '.join(sorted(unknown))}")
    if resume and "session_id" not in placeholders:
        errors.append(f"{name}.{field} must contain {{session_id}}")
    return errors


def validate_custom_backend(name: str, cfg: object) -> list[str]:
    if not isinstance(name, str) or not BACKEND_NAME_RE.fullmatch(name):
        return [f"invalid backend name {name!r}"]
    if not isinstance(cfg, dict):
        return [f"{name} backend config must be an object"]
    errors: list[str] = []
    allowed_fields = {"adapter", "start", "resume", "stdin", "session_id", "events"}
    unknown_fields = set(cfg) - allowed_fields
    if unknown_fields:
        errors.append(f"{name} contains unsupported fields: {', '.join(sorted(unknown_fields))}")
    if cfg.get("adapter", "command-template") != "command-template":
        errors.append(f"{name}.adapter must be command-template")
    errors += _validate_template(name, "start", cfg.get("start"), resume=False)
    if "resume" in cfg:
        errors += _validate_template(name, "resume", cfg.get("resume"), resume=True)
    if "stdin" in cfg and not isinstance(cfg["stdin"], bool):
        errors.append(f"{name}.stdin must be boolean")
    start = cfg.get("start") if isinstance(cfg.get("start"), list) else []
    start_placeholders = set().union(*(set(PLACEHOLDER_RE.findall(x)) for x in start if isinstance(x, str))) if start else set()
    if not cfg.get("stdin", False) and not ({"prompt", "prompt_file"} & start_placeholders):
        errors.append(f"{name}.start must transport the prompt via {{prompt}}, {{prompt_file}}, or stdin=true")
    resume = cfg.get("resume") if isinstance(cfg.get("resume"), list) else []
    resume_placeholders = set().union(*(set(PLACEHOLDER_RE.findall(x)) for x in resume if isinstance(x, str))) if resume else set()
    if resume and not cfg.get("stdin", False) and not ({"prompt", "prompt_file"} & resume_placeholders):
        errors.append(f"{name}.resume must transport the prompt via {{prompt}}, {{prompt_file}}, or stdin=true")
    if resume and "session_id" not in cfg and "session_id" not in start_placeholders:
        errors.append(f"{name} resumable backend must extract a session id or assign one with {{session_id}} during start")
    sid = cfg.get("session_id")
    if sid is not None:
        if not isinstance(sid, dict):
            errors.append(f"{name}.session_id must be an object")
        else:
            if sid.get("source", "stdout-json") not in {
                "stdout-json", "stderr-json", "stdout-line", "stderr-line"
            }:
                errors.append(f"{name}.session_id.source is unsupported")
            keys = sid.get("keys", ["session_id"])
            if not isinstance(keys, list) or not keys or not all(isinstance(x, str) and x for x in keys):
                errors.append(f"{name}.session_id.keys must be a non-empty string array")
    events = cfg.get("events")
    if events is not None and (
        not isinstance(events, dict) or events.get("mode", "text") not in {"text", "jsonl"}
    ):
        errors.append(f"{name}.events.mode must be text or jsonl")
    return errors


def load_einherjar_config(path: Path | None = None) -> dict:
    path = path or einherjar_config_path()
    default = {"schema": 1, "default_backend": "gigacode", "backends": {}}
    if not path.is_file():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Einherjar config: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Einherjar config must be a schema=1 JSON object")
    backend = value.get("default_backend", "gigacode")
    if not isinstance(backend, str) or not BACKEND_NAME_RE.fullmatch(backend):
        raise ValueError("default_backend is invalid")
    custom = value.get("backends", {})
    if not isinstance(custom, dict):
        raise ValueError("backends must be an object")
    for name, cfg in custom.items():
        errors = validate_custom_backend(name, cfg)
        if errors:
            raise ValueError("; ".join(errors))
    if backend not in get_builtin_backend_names() and backend not in custom:
        raise ValueError(f"default_backend is not configured: {backend}")
    return {"schema": 1, "default_backend": backend, "backends": custom}


def get_builtin_backend_names() -> list[str]:
    return ["gigacode", "opencode", "codex"]


def get_backend_adapter(name: str, config: dict | None = None) -> BackendAdapter:
    if name == "gigacode":
        from common.executor.adapters.gigacode import GigaCodeAdapter
        return GigaCodeAdapter()
    if name == "opencode":
        from common.executor.adapters.opencode import OpenCodeAdapter
        return OpenCodeAdapter()
    if name == "codex":
        from common.executor.adapters.codex import CodexAdapter
        return CodexAdapter()
    if config is None:
        raise ValueError(f"unknown Einherjar backend: {name}")
    from common.executor.adapters.command_template import CommandTemplateAdapter
    return CommandTemplateAdapter(name, config)


def resolve_backend(name: str | None, config: dict | None = None) -> tuple[str, BackendAdapter]:
    config = config or load_einherjar_config()
    selected = name or config["default_backend"]
    if selected in get_builtin_backend_names():
        return selected, get_backend_adapter(selected)
    custom = config.get("backends", {}).get(selected)
    if custom is None:
        raise ValueError(f"unknown Einherjar backend: {selected}")
    return selected, get_backend_adapter(selected, custom)


def resolve_backend_name(requested: str | None, config: dict | None = None) -> str:
    config = config or load_einherjar_config()
    selected = requested or config["default_backend"]
    if selected not in get_builtin_backend_names() and selected not in config.get("backends", {}):
        raise ValueError(f"unknown Einherjar backend: {selected}")
    return selected


def probe_backend(name: str, user_config: dict | None = None) -> BackendCapabilities:
    if name in get_builtin_backend_names():
        return get_backend_adapter(name).probe()
    if user_config is None:
        return BackendCapabilities(name, "unknown", False, False, False, False, diagnostic="unknown backend")
    return get_backend_adapter(name, user_config).probe()


def list_available_backends(config: dict | None = None) -> list[BackendCapabilities]:
    config = config or load_einherjar_config()
    result = [probe_backend(name) for name in get_builtin_backend_names()]
    result.extend(probe_backend(name, cfg) for name, cfg in config.get("backends", {}).items())
    return result


def json_objects(text: str) -> Iterable[dict]:
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def nested_string_values(value: object, keys: set[str]) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item:
                yield item
            yield from nested_string_values(item, keys)
    elif isinstance(value, list):
        for item in value:
            yield from nested_string_values(item, keys)


def session_id_from_jsonl(text: str) -> str | None:
    keys = {"session_id", "sessionId", "sessionID", "thread_id", "threadId"}
    for obj in json_objects(text):
        for value in nested_string_values(obj, keys):
            return value
    return None


def _visible_assistant_strings(value: object) -> Iterable[str]:
    """Best-effort generic JSON-event filter; never surface reasoning/tool/user payloads."""
    if isinstance(value, dict):
        role = str(value.get("role", "")).lower()
        kind = str(value.get("type", "")).lower()
        if role in {"user", "system", "tool", "developer"}:
            return
        if any(marker in kind for marker in ("reason", "thinking", "tool", "function", "user", "input")):
            return
        allowed = {"text", "content", "message", "output_text", "final_output", "last_message"}
        for key, item in value.items():
            if key in allowed and isinstance(item, str) and item.strip():
                yield item
            elif isinstance(item, (dict, list)):
                yield from _visible_assistant_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _visible_assistant_strings(item)


def text_candidates_from_jsonl(text: str) -> list[str]:
    """Extract assistant-visible text while excluding reasoning, user, and tool event payloads."""
    result: list[str] = []
    for obj in json_objects(text):
        for value in _visible_assistant_strings(obj):
            value = value.strip()
            if value and value not in result:
                result.append(value)
    return result
