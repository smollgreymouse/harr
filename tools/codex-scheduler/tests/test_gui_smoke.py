#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from PyQt6.QtWidgets import QApplication
from main import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.model.currentText() == "Terra"
    assert window.reasoning.currentText() == "High"
    assert window.speed.currentText() == "Standard"
    assert window.prompt.isEnabled()
    window._quitting = True; window.tray.hide(); window.close(); app.processEvents()
    print("GUI smoke test passed")
    return 0


if __name__ == "__main__": raise SystemExit(main())
