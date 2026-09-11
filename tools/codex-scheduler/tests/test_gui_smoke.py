#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HARR_CODEX_THEME"] = "dark"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from PyQt6.QtCore import QDateTime
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication
from main import MainWindow
from system_theme import install_system_theme


def main() -> int:
    app = QApplication.instance() or QApplication([])
    watcher = install_system_theme(app)
    window = MainWindow()
    assert window.model.currentText() == "Terra"
    assert window.reasoning.currentText() == "High"
    assert window.speed.currentText() == "Standard"
    assert window.session.text() == ""
    assert window.session.placeholderText() == "Session ID"
    assert window.when.text() == ""
    assert window.when.isReadOnly()
    assert "Run at" in window.when.placeholderText()
    assert window.prompt.placeholderText() == "Prompt"
    assert not hasattr(window, "cwd")
    assert not hasattr(window, "save")
    assert not hasattr(window, "save_path")
    assert window.project_button.text() == "⋮"
    assert window.project_path_action.text() == "Project: not resolved"
    assert not window.copy_project_action.isEnabled()
    assert window.save_button.isCheckable()
    assert not window.save_button.isChecked()
    assert window.save_button.text() == "Save final answer…"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = "01a08c7c-df16-74c3-9357-a6cac183895c"
        scheduled = QDateTime.currentDateTime().addSecs(3600)
        window.session.setText(session)
        window.set_scheduled_time(scheduled)
        window._resolved_cwd = root
        time_part = scheduled.toString("yyyyMMdd-HHmm")
        expected = root / f"codex-{session}-{time_part}.md"
        assert window.default_answer_path() == expected
        expected.touch()
        unique = root / f"codex-{session}-{time_part}-2.md"
        assert window.default_answer_path() == unique

        window.set_save_button_state(unique)
        assert window.save_button.isChecked()
        assert window._answer_path == unique
        assert unique.name in window.save_button.text()
        assert window.save_button.toolTip() == str(unique)
        window.set_save_button_state(None)
        assert not window.save_button.isChecked()
        assert window._answer_path is None

    palette = app.palette()
    assert palette.color(QPalette.ColorRole.Window).lightness() < palette.color(QPalette.ColorRole.WindowText).lightness()
    assert palette.color(QPalette.ColorRole.Base).lightness() < 128
    watcher.timer.stop()
    window._quitting = True; window.tray.hide(); window.close(); app.processEvents()
    print("GUI compact-controls + combined-save + unique filename + dark-theme smoke test passed")
    return 0


if __name__ == "__main__": raise SystemExit(main())
