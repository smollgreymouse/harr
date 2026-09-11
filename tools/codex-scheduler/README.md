# Codex Scheduler

Linux-only helpers for scheduling a turn in an existing Codex CLI session. The three model selector scripts always use **High reasoning** and **Standard speed** (`service_tier="default"`), never Fast:

```bash
sol   02:05 SESSION_ID "Продолжай"
terra 02:05 SESSION_ID "Продолжай"
luna  02:05 SESSION_ID "Продолжай"
```

The selectors may be run from any directory. Before creating the `at` job, the scheduler resolves the saved working directory from that session's local Codex rollout (`$CODEX_HOME/sessions/.../rollout-...-SESSION_ID.jsonl`), reads `session_meta.cwd`, canonicalizes it, verifies that it still exists and is inside a Git worktree, and then emits an `at` job that starts with `cd <saved-session-cwd>`. It does **not** depend on Codex's internal SQLite schema.

This is deliberately fail-closed. If a Codex update changes the local rollout layout or `session_meta` shape, the scheduler refuses to create a job instead of guessing a directory. An explicit `--cwd DIR` can be used as a manual fallback; when automatic resolution still works, the explicit directory must exactly match the saved session cwd. The explicit fallback is itself required to be inside a Git worktree.

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

`app/main.py` is a native Qt 6 desktop front end using the Ubuntu-packaged PyQt6 bindings. It provides model (Sol/Terra/Luna), reasoning (Minimal/Low/Medium/High/Extra High), speed (Standard/Fast), session ID, prompt and exact local run time. The working directory is read-only in the UI and is resolved/validated from the saved session. Output is rendered as a user/Codex transcript from `codex exec --json`, with optional clean final-answer export to Markdown/text.

The app follows the system Qt palette and supports minimize/close-to-tray via `QSystemTrayIcon`, with Show/Quit actions. The scheduled job remains external to the GUI: `at` starts Codex at the requested time, so quota exhaustion in Codex App does not prevent the timer from existing. Per-job JSONL is stored under `$XDG_STATE_HOME/harr-codex-scheduler/jobs` (normally `~/.local/state/...`) and tailed while the app is running or hidden. If "Save final answer" is enabled, the scheduled job itself writes the clean answer, so saving does not depend on the GUI remaining open.

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

The tests do not spend Codex quota. They inject fake `at` and `codex` executables, inspect the generated `at` job, execute it, and verify the exact model/reasoning/service-tier argv. Resolver tests build temporary Git worktrees and synthetic Codex rollout files and verify correct cwd resolution, subdirectory preservation, conflicting-cwd refusal, non-Git refusal, and explicit-cwd mismatch refusal. The Python tests also cover JSONL parsing and clean-answer export.

```bash
bash tools/codex-scheduler/tests/test_cli.sh
python3 tools/codex-scheduler/tests/test_session_cwd.py
python3 tools/codex-scheduler/tests/test_core.py
python3 -m py_compile tools/codex-scheduler/app/*.py
```
