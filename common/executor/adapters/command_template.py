"""Declarative argv-only backend adapter for simple external agents."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from common.executor.backends import (
    BackendAdapter, BackendCapabilities, BackendStartRequest, BackendResumeRequest,
    json_objects, nested_string_values, text_candidates_from_jsonl,
)
from common.executor.protocol import is_worker_handoff_text


class CommandTemplateAdapter(BackendAdapter):
    def __init__(self, name: str, config: dict) -> None:
        self._name = name
        self._config = config
        self._prompt_files: list[Path] = []

    def name(self) -> str:
        return self._name

    def probe(self) -> BackendCapabilities:
        start = self._config["start"]
        executable = shutil.which(start[0])
        mode = (self._config.get("events") or {}).get("mode", "text")
        templates = [self._config["start"]]
        if isinstance(self._config.get("resume"), list):
            templates.append(self._config["resume"])
        uses_prompt_file = any("{prompt_file}" in arg for template in templates for arg in template)
        return BackendCapabilities(
            name=self._name, source="config", found=bool(executable),
            resumable="resume" in self._config,
            structured_events=mode == "jsonl", progress_messages=mode == "jsonl",
            prompt_stdin=bool(self._config.get("stdin", False)),
            prompt_file=uses_prompt_file,
            executable=executable,
            diagnostic=None if executable else f"command not found in PATH: {start[0]}",
        )

    def _prompt_file(self, prompt: str) -> str:
        root = Path(os.environ.get(
            "XDG_RUNTIME_DIR",
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "harr",
        )) / "harr-einherjar-prompts"
        root.mkdir(parents=True, exist_ok=True)
        try:
            root.chmod(0o700)
        except OSError:
            pass
        fd, raw = tempfile.mkstemp(prefix="prompt-", suffix=".txt", dir=root)
        path = Path(raw)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prompt)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        self._prompt_files.append(path)
        return str(path)

    def _render(self, template: list[str], *, prompt: str, session_id: str, workspace: Path) -> list[str]:
        prompt_file: str | None = None
        result: list[str] = []
        for arg in template:
            if "{prompt_file}" in arg and prompt_file is None:
                prompt_file = self._prompt_file(prompt)
            replacements = {
                "{prompt}": prompt,
                "{prompt_file}": prompt_file or "",
                "{session_id}": session_id,
                "{workspace}": str(workspace),
            }
            value = arg
            for key, replacement in replacements.items():
                value = value.replace(key, replacement)
            result.append(value)
        return result

    def start_command(self, request: BackendStartRequest) -> list[str]:
        return self._render(
            self._config["start"], prompt=request.prompt,
            session_id=request.harr_session_id or "",
            workspace=request.workspace_root,
        )

    def initial_vendor_session_id(self, request: BackendStartRequest) -> str | None:
        if any("{session_id}" in arg for arg in self._config["start"]):
            return request.harr_session_id
        return None

    def resume_command(self, request: BackendResumeRequest) -> list[str]:
        template = self._config.get("resume")
        if not template:
            raise ValueError(f"backend {self._name} does not support resume")
        return self._render(
            template, prompt=request.prompt, session_id=request.vendor_session_id,
            workspace=request.workspace_root,
        )

    def stdin_text(self, prompt: str) -> str | None:
        return prompt if self._config.get("stdin", False) else None

    def extract_vendor_session_id(self, stdout: str, stderr: str) -> str | None:
        cfg = self._config.get("session_id")
        if not cfg:
            return None
        source = cfg.get("source", "stdout-json")
        keys = set(cfg.get("keys", ["session_id"]))
        text = stdout if source.startswith("stdout") else stderr
        if source.endswith("-json"):
            for obj in json_objects(text):
                for value in nested_string_values(obj, keys):
                    return value
            return None
        for raw in text.splitlines():
            line = raw.strip()
            for key in keys:
                if line.startswith(key + "="):
                    return line[len(key) + 1 :].strip()
                if line.startswith(key + ":"):
                    return line[len(key) + 1 :].strip()
        return None

    def final_output(self, stdout: str, stderr: str) -> str:
        mode = (self._config.get("events") or {}).get("mode", "text")
        if mode != "jsonl":
            return stdout.strip()
        candidates = text_candidates_from_jsonl(stdout)
        for text in reversed(candidates):
            if is_worker_handoff_text(text):
                return text
        return candidates[-1] if candidates else stdout.strip()

    def progress_messages(self, stdout: str) -> list[str]:
        mode = (self._config.get("events") or {}).get("mode", "text")
        if mode != "jsonl":
            return []
        return [x for x in text_candidates_from_jsonl(stdout) if not is_worker_handoff_text(x)]

    def cleanup(self) -> None:
        for path in self._prompt_files:
            try:
                path.unlink()
            except OSError:
                pass
        self._prompt_files.clear()
