# Codex Scheduler

Linux-only helpers for scheduling a turn in an existing Codex CLI session. The three model selector scripts always use **High reasoning** and **Standard speed** (`service_tier="default"`), never Fast:

```bash
sol   02:05 SESSION_ID "Продолжай"
terra 02:05 SESSION_ID "Продолжай"
luna  02:05 SESSION_ID "Продолжай"
```

The selectors may be run from any directory. Before creating the `at` job, the scheduler asks the installed Codex binary for the thread through the documented **Codex App Server** stdio API (`initialize` → `initialized` → `thread/read`) and reads the returned public `thread.cwd` field. It then canonicalizes that path, verifies that it still exists and is inside a Git worktree, and emits an `at` job that starts with `cd <session-cwd>`.

The scheduler does **not** inspect `~/.codex`, SQLite databases, rollout JSONL files, or any other private Codex state format. This keeps the integration behind Codex's documented external protocol. If a future Codex version changes that protocol incompatibly, the scheduler fails closed instead of guessing a directory.

An explicit `--cwd DIR` is available as a manual fallback. When the App Server lookup succeeds, an explicit `--cwd` must exactly match the public `thread.cwd`; when the lookup itself is unavailable, the explicit fallback is still required to exist and be inside a Git worktree.

When launched from a terminal, the future Codex process writes back to the TTY from which the selector was scheduled, matching the manual `TTY=$(tty); ... | at 02:05` pattern. The terminal must still exist when the job starts.

For a file instead, use the common runner directly:

```bash
codex-schedule \
  --model gpt-5.6-terra \
  --reasoning high \
  --speed standard \
  --at 02:05 \
  --session SESSION_ID \
  --prompt "Продолжай" \
  --output ~/codex-resume.log
```

`--speed standard` maps to `service_tier="default"`; `--speed fast` maps to the Codex `fast` service-tier request. Fast availability and whether the backend honors it for headless `codex exec` depend on the installed Codex build/account.

## Desktop app

`app/main.py` is a native Qt 6 desktop front end using the Ubuntu-packaged PyQt6 bindings. It provides model (Sol/Terra/Luna), reasoning (Minimal/Low/Medium/High/Extra High), speed (Standard/Fast), session ID, prompt and exact local run time. Session ID and run time share one compact row and use placeholders instead of side labels. The resolved Codex project directory is not shown as a permanent field; the small `⋮` menu on that row shows it on demand and can copy or refresh it. Output is rendered as a user/Codex transcript from `codex exec --json`, with optional clean final-answer export to Markdown/text.

The app follows the desktop light/dark preference. Qt's native `QStyleHints.colorScheme()` is used where the platform plugin exposes it; on GNOME, where distro Qt can remain light while GTK/libadwaita applications are dark, the app falls back to the public `org.gnome.desktop.interface color-scheme` GSettings key and applies a dark Qt palette while retaining the platform accent highlight. The preference is rechecked while the app is running, so switching GNOME between light and dark does not require a restart. `HARR_CODEX_THEME=dark|light|system` is available as a diagnostic override.

The app supports minimize/close-to-tray via `QSystemTrayIcon`, with Show/Quit actions. The scheduled job remains external to the GUI: `at` starts Codex at the requested time, so quota exhaustion in Codex App does not prevent the timer from existing. Per-job JSONL is stored under `$XDG_STATE_HOME/harr-codex-scheduler/jobs` (normally `~/.local/state/...`) and tailed while the app is running or hidden. If "Save final answer" is enabled, the scheduled job itself writes the clean answer, so saving does not depend on the GUI remaining open.

Ubuntu 24.04 dependencies:

```bash
sudo apt install at python3-pyqt6
sudo systemctl enable --now atd
```

Install user launchers and the desktop entry from a checkout:

```bash
./tools/codex-scheduler/install-ubuntu.sh
```

Then start `Harr Codex Scheduler` from the application menu or run `codex-scheduler-ui`.

Ubuntu's default GNOME session includes AppIndicator integration; on a custom GNOME session without a StatusNotifier/AppIndicator host, Qt cannot expose a tray icon and the window falls back to normal window behavior.

## Tests

The tests do not spend Codex quota. They use a fake Codex executable that implements the documented App Server handshake and `thread/read`, plus fake `at`; they inspect the generated job, execute it, and verify the exact model/reasoning/service-tier argv. Resolver tests verify successful cwd lookup, nested cwd preservation, missing-thread failure, and non-Git refusal. The Python tests also cover JSONL parsing, clean-answer export, the compact form, and a Qt dark-theme smoke test.

```bash
bash tools/codex-scheduler/tests/test_cli.sh
python3 tools/codex-scheduler/tests/test_session_cwd.py
python3 tools/codex-scheduler/tests/test_core.py
python3 -m py_compile tools/codex-scheduler/app/*.py
```
