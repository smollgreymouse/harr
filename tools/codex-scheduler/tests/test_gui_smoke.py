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
    assert "Run at" in window.when.placeholderText()
    assert window.prompt.placeholderText() == "Prompt"
    assert not hasattr(window, "cwd")
    assert window.project_button.text() == "⋮"
    assert window.project_path_action.text() == "Project: not resolved"
    assert not window.copy_project_action.isEnabled()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session = "01a08c7c-df16-74c3-9357-a6cac183895c"
        window.session.setText(session)
        window.when.setText("2026-09-11 10:19")
        window._resolved_cwd = root
        expected = root / f"codex-{session}-20260911-1019.md"
        assert window.default_answer_path() == expected
        expected.touch()
        assert window.default_answer_path() == root / f"codex-{session}-20260911-1019-2.md"

    palette = app.palette()
    assert palette.color(QPalette.ColorRole.Window).lightness() < palette.color(QPalette.ColorRole.WindowText).lightness()
    assert palette.color(QPalette.ColorRole.Base).lightness() < 128
    watcher.timer.stop()
    window._quitting = True; window.tray.hide(); window.close(); app.processEvents()
    print("GUI compact-controls + unique filename + dark-theme smoke test passed")
    return 0


if __name__ == "__main__": raise SystemExit(main())
