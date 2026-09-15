#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROTOCOL = "harr.executor.v1"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_REASONING = "low"


class CodexCliError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexCliResult:
    session_id: str
    packet: dict
    stdout_events: tuple[dict, ...]
    usage: dict[str, int]
    stderr: str


TERMINAL_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "protocol",
        "state",
        "current_step",
        "completed_steps",
        "summary",
        "changed_files",
        "validation",
        "blocker",
    ],
    "properties": {
        "protocol": {"const": PROTOCOL},
        "state": {"enum": ["DONE", "BLOCKED", "FAILED_EXECUTION", "FAILED_PROTOCOL", "CANCELLED"]},
        "current_step": {"type": ["string", "null"]},
        "completed_steps": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string", "maxLength": 4000},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "validation": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["check", "status", "detail"],
                "properties": {
                    "check": {"type": "string"},
                    "status": {"enum": ["PASS", "FAIL", "NOT_RUN"]},
                    "detail": {"type": "string", "maxLength": 1000},
                },
            },
        },
        "blocker": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["class", "step", "fact", "decision_needed", "evidence"],
                    "properties": {
                        "class": {"enum": ["PLAN_PRECONDITION_FALSE", "UNSPECIFIED_DESIGN_DECISION", "SCOPE_CONFLICT", "BUILD_FAILURE_OUTSIDE_PLAN", "TOOL_FAILURE", "PERMISSION", "OTHER"]},
                        "step": {"type": ["string", "null"]},
                        "fact": {"type": "string", "maxLength": 2000},
                        "decision_needed": {"type": "string", "maxLength": 2000},
                        "evidence": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 1000}},
                    },
                },
            ]
        },
    },
}


EXECUTOR_RULES = """\
You are the Harr execution worker. You are an executor, not a planner.
The execution contract below is authoritative.

Hard rules:
1. Never redesign, replan, broaden scope, or invent missing architecture.
2. Execute contract steps in order unless the contract explicitly says otherwise.
3. Do not ask the user questions. If a design/architecture/API/ownership decision is missing, return BLOCKED.
4. Do not spawn subagents. Do not use web search. Do not commit, push, publish, or make external writes.
5. Do not weaken tests to make them pass.
6. If a stated precondition is false, gather only minimal evidence and return BLOCKED.
7. Only fix obvious local syntax/type errors directly caused by the prescribed edit. Anything needing judgment => BLOCKED.
8. Never silently skip required validation.
9. Keep the final response compact. Return only the JSON object required by the output schema.
10. Do not repeat source files, full diffs, or long logs in the final response.
"""


class CodexCliAdapter:
    def __init__(self, *, command: str = "codex", model: str = DEFAULT_MODEL, reasoning_effort: str = DEFAULT_REASONING, extra_config: Iterable[str] = ()) -> None:
        self.command = command
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.extra_config = tuple(extra_config)

    def probe(self) -> dict:
        resolved = shutil.which(self.command)
        if not resolved:
            return {"available": False, "command": self.command, "model": self.model, "resume": True, "structured_output": True}
        proc = subprocess.run([resolved, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=15)
        return {"available": proc.returncode == 0, "command": resolved, "version": (proc.stdout or proc.stderr).strip(), "model": self.model, "resume": True, "structured_output": True}

    def start(self, *, repo_root: Path, execution_contract: str) -> CodexCliResult:
        return self._run(repo_root=repo_root, prompt=f"{EXECUTOR_RULES}\n\n{execution_contract.strip()}\n", session_id=None)

    def resume(self, *, repo_root: Path, session_id: str, resolution_delta: str) -> CodexCliResult:
        prompt = f"""\
Continue the same Harr execution run. The previous execution contract remains authoritative.
Apply only the planner resolution delta below, then continue from the blocked step.
Do not repeat completed work unless validation requires it.
Return only the JSON object required by the output schema.

{resolution_delta.strip()}
"""
        return self._run(repo_root=repo_root, prompt=prompt, session_id=session_id)

    def _run(self, *, repo_root: Path, prompt: str, session_id: str | None) -> CodexCliResult:
        root = repo_root.resolve()
        if not root.is_dir():
            raise CodexCliError(f"repository root does not exist: {root}")
        resolved = shutil.which(self.command) or self.command
        with tempfile.TemporaryDirectory(prefix="harr-codex-executor-") as tmp_raw:
            tmp = Path(tmp_raw)
            schema_file = tmp / "terminal-schema.json"
            last_message = tmp / "last-message.json"
            schema_file.write_text(json.dumps(TERMINAL_SCHEMA, indent=2) + "\n", encoding="utf-8")
            argv = [resolved, "exec", "--json", "--output-schema", str(schema_file), "--output-last-message", str(last_message), "--model", self.model, "--sandbox", "workspace-write", "--cd", str(root), "--config", f'model_reasoning_effort="{self.reasoning_effort}"', "--config", "features.multi_agent=false"]
            for item in self.extra_config:
                argv += ["--config", item]
            if session_id is not None:
                argv += ["resume", session_id]
            argv += ["-"]
            env = os.environ.copy()
            env["HARR_EXECUTOR_CHILD"] = "1"
            proc = subprocess.run(argv, input=prompt, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, env=env)
            events = tuple(self._parse_jsonl(proc.stdout))
            observed_session = self._thread_id(events)
            if session_id is None and not observed_session:
                raise CodexCliError(self._failure("codex did not emit thread.started", proc))
            if session_id is not None and observed_session and observed_session != session_id:
                raise CodexCliError(f"codex resumed unexpected session: expected {session_id}, got {observed_session}")
            effective_session = observed_session or session_id
            assert effective_session is not None
            if proc.returncode != 0:
                raise CodexCliError(self._failure(f"codex exec exited {proc.returncode}", proc))
            if not last_message.is_file():
                raise CodexCliError(self._failure("codex produced no --output-last-message file", proc))
            try:
                packet = json.loads(last_message.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CodexCliError(f"invalid Codex terminal JSON: {exc}") from exc
            self._validate_packet(packet)
            return CodexCliResult(session_id=effective_session, packet=packet, stdout_events=events, usage=self._usage(events), stderr=proc.stderr)

    @staticmethod
    def _parse_jsonl(text: str) -> Iterable[dict]:
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value

    @staticmethod
    def _usage(events: Iterable[dict]) -> dict[str, int]:
        latest: dict[str, int] = {}
        for event in events:
            if event.get("type") != "turn.completed":
                continue
            usage = event.get("usage")
            if isinstance(usage, dict):
                latest = {
                    key: int(usage.get(key, 0) or 0)
                    for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
                }
        return latest

    @staticmethod
    def _thread_id(events: Iterable[dict]) -> str | None:
        for event in events:
            if event.get("type") == "thread.started":
                value = event.get("thread_id")
                if isinstance(value, str) and value:
                    return value
        return None

    @staticmethod
    def _validate_packet(packet: object) -> None:
        if not isinstance(packet, dict):
            raise CodexCliError("terminal packet is not an object")
        if packet.get("protocol") != PROTOCOL:
            raise CodexCliError("terminal packet protocol mismatch")
        state = packet.get("state")
        if state not in {"DONE", "BLOCKED", "FAILED_EXECUTION", "FAILED_PROTOCOL", "CANCELLED"}:
            raise CodexCliError(f"invalid terminal packet state: {state!r}")
        if state == "BLOCKED" and not isinstance(packet.get("blocker"), dict):
            raise CodexCliError("BLOCKED terminal packet has no blocker object")
        if state != "BLOCKED" and packet.get("blocker") is not None:
            raise CodexCliError(f"{state} terminal packet must have blocker=null")
        for field in ("completed_steps", "changed_files", "validation"):
            if not isinstance(packet.get(field), list):
                raise CodexCliError(f"terminal packet field {field} must be an array")
        if not isinstance(packet.get("summary"), str):
            raise CodexCliError("terminal packet summary must be a string")

    @staticmethod
    def _failure(message: str, proc: subprocess.CompletedProcess[str]) -> str:
        tail = proc.stderr.strip().splitlines()[-20:]
        suffix = "\n".join(tail)
        return message if not suffix else f"{message}:\n{suffix}"


def _main() -> int:
    parser = argparse.ArgumentParser(description="Harr Codex CLI executor adapter")
    parser.add_argument("--command", default="codex")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=DEFAULT_REASONING)
    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("probe")
    p_start = sub.add_parser("start")
    p_start.add_argument("--repo", type=Path, required=True)
    p_start.add_argument("--contract", type=Path, required=True)
    p_resume = sub.add_parser("resume")
    p_resume.add_argument("--repo", type=Path, required=True)
    p_resume.add_argument("--session", required=True)
    p_resume.add_argument("--resolution", type=Path, required=True)
    args = parser.parse_args()
    adapter = CodexCliAdapter(command=args.command, model=args.model, reasoning_effort=args.reasoning_effort)
    if args.subcommand == "probe":
        print(json.dumps(adapter.probe(), indent=2))
        return 0
    if args.subcommand == "start":
        result = adapter.start(repo_root=args.repo, execution_contract=args.contract.read_text(encoding="utf-8"))
    else:
        result = adapter.resume(repo_root=args.repo, session_id=args.session, resolution_delta=args.resolution.read_text(encoding="utf-8"))
    print(json.dumps({"session_id": result.session_id, "usage": result.usage, "packet": result.packet}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
