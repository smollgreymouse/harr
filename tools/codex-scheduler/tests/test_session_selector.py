#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtWidgets import QApplication

import session_selector as selector_module
from session_selector import SessionComboBox


def main() -> int:
    app = QApplication.instance() or QApplication([])
    combo = SessionComboBox()
    sessions = [
        {
            "id": "01-known",
            "name": "Implement worker pool",
            "preview": "Implement worker pool",
            "cwd": "/tmp/project-a",
        },
        {
            "id": "02-second",
            "name": None,
            "preview": "Audit terrain stage",
            "cwd": "/tmp/project-b",
        },
    ]

    combo.set_sessions(sessions, select_latest_if_empty=True)
    assert combo.session_id() == "01-known"
    assert combo.currentText() == "Implement worker pool"
    assert "Session ID: 01-known" in combo.toolTip()
    assert "01-known" not in combo.itemText(0)
    assert "Session ID: 01-known" in str(combo.itemData(0, combo.ItemDataRole.ToolTipRole) if hasattr(combo, "ItemDataRole") else combo.itemData(0, 3))

    combo.set_session_id("02-second")
    assert combo.session_id() == "02-second"
    assert combo.currentText() == "Audit terrain stage"
    assert "Session ID: 02-second" in combo.toolTip()

    # Pasting a known UUID immediately converts the visible field back to the
    # human-readable title while preserving the UUID internally.
    line = combo.lineEdit()
    assert line is not None
    line.setText("01-known")
    line.textEdited.emit("01-known")
    app.processEvents()
    assert combo.session_id() == "01-known"
    assert combo.currentText() == "Implement worker pool"

    # A custom UUID outside thread/list is resolved via documented thread/read.
    def fake_request(method: str, params: dict, **_kwargs):
        assert method == "thread/read"
        assert params["threadId"] == "03-custom"
        return {
            "thread": {
                "id": "03-custom",
                "name": "Recovered custom session",
                "preview": "Recovered custom session",
                "cwd": "/tmp/custom-project",
            }
        }

    selector_module._app_server_request = fake_request
    line.setText("03-custom")
    line.textEdited.emit("03-custom")
    line.editingFinished.emit()
    app.processEvents()
    assert combo.session_id() == "03-custom"
    assert combo.currentText() == "Recovered custom session"
    assert "Session ID: 03-custom" in combo.toolTip()
    assert "Project: /tmp/custom-project" in combo.toolTip()

    combo.close()
    print("named session selector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
