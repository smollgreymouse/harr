"""Built-in Codex CLI adapter for Einherjar."""
from __future__ import annotations
import shutil
from common.executor.backends import (
    BackendAdapter, BackendCapabilities, BackendStartRequest, BackendResumeRequest,
    session_id_from_jsonl, text_candidates_from_jsonl,
)
from common.executor.protocol import is_worker_handoff_text

class CodexAdapter(BackendAdapter):
    def name(self) -> str:
        return "codex"

    def probe(self) -> BackendCapabilities:
        executable = shutil.which("codex")
        return BackendCapabilities(
            name="codex", source="builtin", found=bool(executable),
            resumable=True, structured_events=True, progress_messages=True,
            prompt_stdin=True, executable=executable,
            diagnostic=None if executable else "codex CLI not found in PATH",
        )

    def _global(self, workspace) -> list[str]:
        executable = shutil.which("codex")
        if not executable:
            raise FileNotFoundError("codex executable not found in PATH")
        return [
            executable, "--ask-for-approval", "never", "--sandbox", "workspace-write",
            "-C", str(workspace),
        ]

    def start_command(self, request: BackendStartRequest) -> list[str]:
        return [*self._global(request.workspace_root), "exec", "--json", "-"]

    def resume_command(self, request: BackendResumeRequest) -> list[str]:
        return [*self._global(request.workspace_root), "exec", "resume", "--json", request.vendor_session_id, "-"]

    def stdin_text(self, prompt: str) -> str | None:
        return prompt

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
