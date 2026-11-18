"""Built-in Z.ai ZCode Agent CLI adapter for Einherjar."""
from __future__ import annotations

import os
import shutil

from common.executor.backends import (
    BackendAdapter, BackendCapabilities, BackendStartRequest, BackendResumeRequest,
    json_objects,
)


class ZCodeAdapter(BackendAdapter):
    def name(self) -> str:
        return "zcode"

    def probe(self) -> BackendCapabilities:
        executable = shutil.which(os.environ.get("HARR_EIN_EXECUTABLE", "zcode"))
        return BackendCapabilities(
            name="zcode", source="builtin", found=bool(executable),
            resumable=True, structured_events=True, progress_messages=False,
            executable=executable,
            diagnostic=None if executable else "zcode Agent CLI not found in PATH",
        )

    def _base(self, workspace) -> list[str]:
        executable = shutil.which(os.environ.get("HARR_EIN_EXECUTABLE", "zcode"))
        if not executable:
            raise FileNotFoundError("zcode Agent CLI executable not found in PATH")
        return [
            executable, "--cwd", str(workspace), "--mode", "yolo",
            "--output-format", "stream-json", "--no-color",
        ]

    def start_command(self, request: BackendStartRequest) -> list[str]:
        return [*self._base(request.workspace_root), "--prompt", request.prompt]

    def resume_command(self, request: BackendResumeRequest) -> list[str]:
        return [
            *self._base(request.workspace_root), "--resume", request.vendor_session_id,
            "--prompt", request.prompt,
        ]

    @staticmethod
    def _result(stdout: str) -> dict:
        # The final NDJSON result is authoritative. Do not recursively search
        # events: user/tool/reasoning payloads may contain handoff-shaped JSON.
        result = {}
        for event in json_objects(stdout):
            if event.get("type") == "result":
                result = event
        return result

    def extract_vendor_session_id(self, stdout: str, stderr: str) -> str | None:
        session_id = self._result(stdout).get("sessionId")
        return session_id if isinstance(session_id, str) and session_id.strip() else None

    def final_output(self, stdout: str, stderr: str) -> str:
        response = self._result(stdout).get("response")
        return response.strip() if isinstance(response, str) else ""
