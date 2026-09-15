#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QComboBox, QWidget

from session_cwd import SessionResolutionError, _app_server_request


class SessionComboBox(QComboBox):
    """Editable Codex session selector with human-readable titles.

    The UUID is kept as internal state and is never replaced by the visible
    session title.  A manually pasted UUID stays valid even when it is not in
    the current recent-session list; on editingFinished we resolve that UUID
    through documented codex app-server thread/read and replace the visible
    text with the thread name/preview when available.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(18)
        self._session_id = ""
        self._sessions: dict[str, dict[str, Any]] = {}
        self._updating = False

        line = self.lineEdit()
        assert line is not None
        line.setPlaceholderText("Session")
        line.textEdited.connect(self._user_edited)
        line.editingFinished.connect(self._resolve_custom_session)
        self.currentIndexChanged.connect(self._index_changed)
        self.activated.connect(self._session_activated)
        self._refresh_field_tooltip()

    @staticmethod
    def _normalized_session(raw: dict[str, Any]) -> dict[str, Any] | None:
        session_id = str(raw.get("id") or "").strip()
        if not session_id:
            return None
        name = " ".join(str(raw.get("name") or raw.get("preview") or "Codex session").split())
        cwd = str(raw.get("cwd") or "").strip()
        return {
            "id": session_id,
            "name": name or "Codex session",
            "cwd": cwd,
            "preview": " ".join(str(raw.get("preview") or "").split()),
        }

    @staticmethod
    def _display_name(session: dict[str, Any]) -> str:
        name = str(session.get("name") or session.get("preview") or "Codex session").strip()
        return name if len(name) <= 64 else name[:63] + "…"

    @staticmethod
    def _tooltip(session: dict[str, Any]) -> str:
        parts = [f"Session ID: {session['id']}"]
        cwd = str(session.get("cwd") or "").strip()
        if cwd:
            parts.append(f"Project: {cwd}")
        preview = str(session.get("preview") or "").strip()
        name = str(session.get("name") or "").strip()
        if preview and preview != name:
            parts.append(preview)
        return "\n".join(parts)

    def _set_visible_text(self, text: str) -> None:
        self._updating = True
        try:
            self.setCurrentIndex(-1)
            self.setEditText(text)
        finally:
            self._updating = False

    def _show_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            self._set_visible_text(session_id)
        else:
            self._set_visible_text(self._display_name(session))
        self._refresh_field_tooltip()

    def _refresh_field_tooltip(self) -> None:
        session = self._sessions.get(self._session_id)
        if session is not None:
            tooltip = self._tooltip(session)
        elif self._session_id:
            tooltip = f"Session ID: {self._session_id}\nCustom / unresolved session"
        else:
            tooltip = "Recent Codex sessions; paste any session ID with Ctrl+V"
        self.setToolTip(tooltip)
        line = self.lineEdit()
        if line is not None:
            line.setToolTip(tooltip)

    def _index_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        session_id = self.itemData(index, Qt.ItemDataRole.UserRole)
        if isinstance(session_id, str) and session_id:
            self._session_id = session_id
            self._refresh_field_tooltip()

    def _session_activated(self, index: int) -> None:
        session_id = self.itemData(index, Qt.ItemDataRole.UserRole)
        if not isinstance(session_id, str) or not session_id:
            return
        self._session_id = session_id
        self._show_session(session_id)
        line = self.lineEdit()
        if line is not None:
            line.setCursorPosition(len(line.text()))

    def _user_edited(self, text: str) -> None:
        if self._updating:
            return
        value = text.strip()
        self._session_id = value
        self._refresh_field_tooltip()
        if value in self._sessions:
            # Defer replacement until the paste/key event has finished.
            QTimer.singleShot(0, lambda sid=value: self._show_session(sid) if self._session_id == sid else None)

    def _resolve_custom_session(self) -> None:
        session_id = self._session_id.strip()
        if not session_id or session_id in self._sessions:
            if session_id:
                self._show_session(session_id)
            return
        try:
            result = _app_server_request(
                "thread/read",
                {"threadId": session_id, "includeTurns": False},
                timeout=5.0,
            )
        except SessionResolutionError:
            self._refresh_field_tooltip()
            return
        thread = result.get("thread")
        if not isinstance(thread, dict):
            return
        normalized = self._normalized_session(thread)
        if normalized is None or normalized["id"] != session_id:
            return
        self._sessions[session_id] = normalized
        # Keep old/custom sessions discoverable in the dropdown too.
        if self.findData(session_id, Qt.ItemDataRole.UserRole) < 0:
            self.addItem(self._display_name(normalized), session_id)
            index = self.count() - 1
            self.setItemData(index, self._tooltip(normalized), Qt.ItemDataRole.ToolTipRole)
        self._show_session(session_id)

    def session_id(self) -> str:
        return self._session_id.strip()

    def set_session_id(self, value: str) -> None:
        self._session_id = value.strip()
        self._show_session(self._session_id)

    def set_sessions(self, sessions: list[dict[str, Any]], *, select_latest_if_empty: bool = False) -> None:
        current = self.session_id()
        normalized_sessions: list[dict[str, Any]] = []
        for raw in sessions:
            normalized = self._normalized_session(raw)
            if normalized is not None:
                normalized_sessions.append(normalized)

        self._sessions = {str(item["id"]): item for item in normalized_sessions}
        self._updating = True
        self.blockSignals(True)
        try:
            self.clear()
            for session in normalized_sessions:
                session_id = str(session["id"])
                self.addItem(self._display_name(session), session_id)
                index = self.count() - 1
                self.setItemData(index, self._tooltip(session), Qt.ItemDataRole.ToolTipRole)
            target = current
            if not target and select_latest_if_empty and normalized_sessions:
                target = str(normalized_sessions[0]["id"])
            self._session_id = target
            self.setCurrentIndex(-1)
            if target in self._sessions:
                self.setEditText(self._display_name(self._sessions[target]))
            else:
                self.setEditText(target)
        finally:
            self.blockSignals(False)
            self._updating = False
        self._refresh_field_tooltip()
        if self._session_id != current:
            self.editTextChanged.emit(self.currentText())
