"""Built-in OpenCode adapter for Einherjar."""
from __future__ import annotations
import shutil
from common.executor.backends import (
    BackendAdapter, BackendCapabilities, BackendStartRequest, BackendResumeRequest,
    session_id_from_jsonl, text_candidates_from_jsonl,
)
from common.executor.protocol import is_worker_handoff_text

class OpenCodeAdapter(BackendAdapter):
    def name(self) -> str:
        return "opencode"

    def probe(self) -> BackendCapabilities:
        executable = shutil.which("opencode")
        return BackendCapabilities(
            name="opencode", source="builtin", found=bool(executable),
            resumable=True, structured_events=True, progress_messages=True,
            executable=executable,
            diagnostic=None if executable else "opencode CLI not found in PATH",
        )

    def _base(self, workspace) -> list[str]:
        executable = shutil.which("opencode")
        if not executable:
            raise FileNotFoundError("opencode executable not found in PATH")
        return [executable, "run", "--format", "json", "--auto", "--pure", "--dir", str(workspace)]

    def start_command(self, request: BackendStartRequest) -> list[str]:
        return [*self._base(request.workspace_root), request.prompt]

    def resume_command(self, request: BackendResumeRequest) -> list[str]:
        # OpenCode resumes through `run --session`; there is no `opencode resume` command.
        return [*self._base(request.workspace_root), "--session", request.vendor_session_id, request.prompt]

    def extract_vendor_session_id(self, stdout: str, stderr: str) -> str | None:
        return session_id_from_jsonl(stdout) or session_id_from_jsonl(stderr)

    def final_output(self, stdout: str, stderr: str) -> str:
        candidates = text_candidates_from_jsonl(stdout)
        for text in reversed(candidates):
            if is_worker_handoff_text(text):
                return text
        return candidates[-1] if candidates else stdout.strip()

    def progress_messages(self, stdout: str) -> list[str]:
        return [x for x in text_candidates_from_jsonl(stdout) if not is_worker_handoff_text(x)]
