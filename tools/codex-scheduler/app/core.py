from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "\n".join(p for p in parts if p)
    return ""


def parse_codex_json_line(line: str) -> list[TranscriptEvent]:
    line = line.strip()
    if not line:
        return []
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return [TranscriptEvent("status", line)]

    event_type = str(payload.get("type", ""))
    events: list[TranscriptEvent] = []

    item = payload.get("item")
    if isinstance(item, dict):
        item_type = str(item.get("type", ""))
        if item_type in {"agent_message", "assistant_message", "message"}:
            text = _text_from_content(item.get("text") or item.get("content"))
            if text:
                events.append(TranscriptEvent("assistant", text))
                return events
        if item_type in {"reasoning", "analysis"}:
            text = _text_from_content(item.get("text") or item.get("content"))
            if text:
                events.append(TranscriptEvent("status", text))
                return events

    if event_type in {"error", "turn.failed"}:
        value = payload.get("message") or payload.get("error")
        if isinstance(value, dict):
            value = value.get("message") or value.get("code") or json.dumps(value, ensure_ascii=False)
        if value:
            events.append(TranscriptEvent("error", str(value)))
            return events

    if event_type in {"turn.completed", "thread.completed"}:
        events.append(TranscriptEvent("done", "Completed"))
        return events

    message = payload.get("message")
    if isinstance(message, str) and message:
        events.append(TranscriptEvent("status", message))
    return events


def extract_assistant_answer(lines: list[str]) -> str:
    messages: list[str] = []
    for line in lines:
        for event in parse_codex_json_line(line):
            if event.kind == "assistant":
                messages.append(event.text)
    return "\n\n".join(messages).strip()
