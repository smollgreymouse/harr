#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
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
    assert window.prompt.isEnabled()
    palette = app.palette()
    assert palette.color(QPalette.ColorRole.Window).lightness() < palette.color(QPalette.ColorRole.WindowText).lightness()
    assert palette.color(QPalette.ColorRole.Base).lightness() < 128
    watcher.timer.stop()
    window._quitting = True; window.tray.hide(); window.close(); app.processEvents()
    print("GUI dark-theme smoke test passed")
    return 0


if __name__ == "__main__": raise SystemExit(main())
