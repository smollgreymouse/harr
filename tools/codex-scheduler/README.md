# Codex Scheduler

Linux-only helpers for scheduling a turn in an existing Codex CLI session. The three model selector scripts always use **High reasoning** and **Standard speed** (`service_tier="default"`), never Fast:

```bash
sol   02:05 SESSION_ID "Продолжай"
terra 02:05 SESSION_ID "Продолжай"
luna  02:05 SESSION_ID "Продолжай"
```

The selectors may be run from any directory. Before creating the `at` job, the scheduler asks the installed Codex binary for the thread through the documented **Codex App Server** stdio API (`initialize` → `initialized` → `thread/read`) and reads public `thread.cwd`. It verifies that directory and the Git worktree, then emits an `at` job that starts with `cd <session-cwd>`.

The scheduler does **not** inspect `~/.codex`, SQLite databases, rollout JSONL files, or any other private Codex state format. An explicit `--cwd DIR` exists as a fail-closed manual fallback.

`--timestamp CCYYMMDDhhmm` schedules an absolute local date/time through `at -t`, so GUI tasks can be scheduled days or weeks ahead. CLI `--at` remains available for normal `at(1)` expressions.

## Desktop app

`app/main.py` is a Qt 6 / PyQt6 front end for Ubuntu 24.04+.

The UI is task-oriented rather than single-job:

- every open tab is one scheduler task;
- `+` sits directly after the last tab;
- closing a tab only closes the view; a non-empty task remains in persistent history;
- the left tasks sidebar can be shown/hidden from the tab strip;
- **Active** and **History** are independently collapsible;
- the sidebar/task menu can reopen closed tasks, cancel scheduled/running jobs, delete scheduler state/logs, or explicitly delete the exported answer too;
- scheduled/running/completed/failed/cancelled state lives under `$XDG_STATE_HOME/harr-codex-scheduler` (normally `~/.local/state/harr-codex-scheduler`) and is updated by the external job runner even while the GUI is closed.

Codex session selection is an editable dropdown. It is filled through the documented App Server `thread/list` API, newest activity first. A fresh task automatically selects the newest session when available, while Ctrl+V/manual session IDs continue to work. Reading the session list does not start a model turn.

The schedule picker defaults to **current local time + 05:02**, rounded to whole-minute `at` precision. It uses standard Qt widgets: a `QDateEdit` with native calendar popup and click-first hour/minute steppers built from `QSpinBox`/`QToolButton`. The popup calendar uses the system locale and Monday as the first day of the week. Past times are rejected inside the picker; `codex-schedule` independently validates absolute timestamps before invoking `at` so CLI use remains protected too.

Model/reasoning/speed selectors are Sol/Terra/Luna, Minimal/Low/Medium/High/Extra High and Standard/Fast. The selector chrome is intentionally flat until hover/focus; the standard widgets themselves are still drawn by the active Qt platform style.

Answer export is one checkable `Save final answer…` button. Choosing a file enables export; clicking the enabled button again disables it. Default names are unique and include session ID plus schedule time, e.g. `codex-SESSION-20260911-1019.md`.

### Theme and desktop integration

On GNOME the launcher prefers Ubuntu's `qt6-gtk-platformtheme` when it is installed. Standard controls, menus and native dialogs are then drawn through the platform Qt style rather than reimplemented by application CSS. Application QSS is deliberately limited to structural chrome such as sidebar/tabs/message bubbles and flat selector hover states.

If GNOME reports `prefer-dark` but Qt still exposes a light palette, `system_theme.py` applies a dark fallback palette. `HARR_CODEX_THEME=dark|light|system` is available for diagnostics.

The app supports close/minimize-to-tray through `QSystemTrayIcon`. The actual timer is still owned by `at`, so a scheduled task does not depend on the GUI staying open.

Ubuntu dependencies:

```bash
sudo apt install at python3-pyqt6 qt6-gtk-platformtheme
sudo systemctl enable --now atd
```

Run without installation:

```bash
python3 tools/codex-scheduler/app/main.py
```

Install user launchers and the desktop entry:

```bash
./tools/codex-scheduler/install-ubuntu.sh
```

Then run `codex-scheduler-ui` or start **Harr Codex Scheduler** from the application menu.

## Tests

The tests do not spend Codex quota. Fake Codex/App Server and fake `at` binaries exercise cwd resolution, recent-session listing, scheduler argv, High/Standard selector contracts, timestamp validation and state lifecycle. Qt smoke tests run offscreen on Ubuntu 24.04.

```bash
bash tools/codex-scheduler/tests/test_cli.sh
python3 tools/codex-scheduler/tests/test_session_cwd.py
python3 tools/codex-scheduler/tests/test_task_store.py
python3 tools/codex-scheduler/tests/test_core.py
QT_QPA_PLATFORM=offscreen python3 tools/codex-scheduler/tests/test_gui_smoke.py
python3 -m py_compile tools/codex-scheduler/app/*.py tools/codex-scheduler/tests/*.py
```
