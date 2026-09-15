#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"


def run_signal(sig: signal.Signals) -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["HARR_CODEX_THEME"] = "dark"
    env.pop("QT_QPA_PLATFORMTHEME", None)
    proc = subprocess.Popen(
        [sys.executable, str(MAIN)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        time.sleep(0.8)
        proc.send_signal(sig)
        stdout, stderr = proc.communicate(timeout=5)
    except Exception:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=2)
        raise
    assert proc.returncode == 0, (sig, proc.returncode, stdout, stderr)
    assert "KeyboardInterrupt" not in stderr, stderr
    assert "qgnomeplatform" not in stderr, stderr


def main() -> int:
    run_signal(signal.SIGINT)
    run_signal(signal.SIGTERM)
    print("single-signal GUI shutdown tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
