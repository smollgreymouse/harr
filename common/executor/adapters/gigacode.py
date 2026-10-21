"""Built-in GigaCode adapter for Einherjar."""
from __future__ import annotations
import shutil
import os
from common.executor.backends import BackendAdapter, BackendCapabilities, BackendStartRequest, BackendResumeRequest
from common.executor.protocol import WORKER_CONTRACT

class GigaCodeAdapter(BackendAdapter):
    def name(self) -> str:
        return "gigacode"

    def probe(self) -> BackendCapabilities:
        executable = shutil.which(os.environ.get("HARR_EIN_EXECUTABLE", "gigacode"))
        return BackendCapabilities(
            name="gigacode", source="builtin", found=bool(executable),
            resumable=True, structured_events=False, progress_messages=False,
            executable=executable,
            diagnostic=None if executable else "gigacode CLI not found in PATH",
        )

    def prepare_prompt(self, prompt: str) -> str:
        # GigaCode receives WORKER_CONTRACT via --append-system-prompt.
        return prompt

    def start_command(self, request: BackendStartRequest) -> list[str]:
        executable = shutil.which(os.environ.get("HARR_EIN_EXECUTABLE", "gigacode"))
        if not executable:
            raise FileNotFoundError("gigacode executable not found in PATH")
        if not request.harr_session_id:
            raise ValueError("GigaCode start requires Harr session id")
        return [
            executable, "--chat-recording", "--session-id", request.harr_session_id,
            "--approval-mode", "auto-edit", "--append-system-prompt", WORKER_CONTRACT,
            "--output-format", "text", request.prompt,
        ]

    def resume_command(self, request: BackendResumeRequest) -> list[str]:
        executable = shutil.which(os.environ.get("HARR_EIN_EXECUTABLE", "gigacode"))
        if not executable:
            raise FileNotFoundError("gigacode executable not found in PATH")
        return [
            executable, "--chat-recording", "--resume", request.vendor_session_id,
            "--approval-mode", "auto-edit", "--append-system-prompt", WORKER_CONTRACT,
            "--output-format", "text", request.prompt,
        ]

    def initial_vendor_session_id(self, request: BackendStartRequest) -> str | None:
        # GigaCode accepts an explicit session id; reuse Harr's UUID internally.
        return request.harr_session_id

    def extract_vendor_session_id(self, stdout: str, stderr: str) -> str | None:
        return None
