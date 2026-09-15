# Codex Scheduler

Native Linux desktop scheduler for existing OpenAI Codex CLI sessions. The scheduler is implemented entirely in **C++20 + Qt 6 Widgets**; there is no Python/PyQt runtime or Python scheduler code.

The three convenience selectors always use **High reasoning** and **Standard speed** (`service_tier="default"`), never Fast:

```bash
sol   02:05 SESSION_ID "Продолжай"
terra 02:05 SESSION_ID "Продолжай"
luna  02:05 SESSION_ID "Продолжай"
```

The selectors may be run from any directory. Before creating an `at` job, the native scheduler asks the installed Codex binary for the thread through the documented **Codex App Server** stdio API (`initialize` → `initialized` → `thread/read`) and reads `thread.cwd`. It verifies that directory and its Git worktree, then emits an `at` job beginning with `cd <session-cwd>`.

The scheduler never inspects `~/.codex`, SQLite databases, rollout JSONL files, or other private Codex state formats. `--cwd DIR` is available only as a fail-closed explicit fallback and must agree with App Server metadata when both are available.

`--timestamp CCYYMMDDhhmm` schedules an absolute local date/time through `at -t`, so GUI tasks can be scheduled days or weeks ahead. CLI `--at` remains available for ordinary `at(1)` expressions.

## One native executable

`harr-codex-scheduler` is both the desktop application and the execution backend. It has internal command modes for scheduling, job execution and Codex metadata lookup:

```text
harr-codex-scheduler                 # GUI + tray
harr-codex-scheduler schedule ...
harr-codex-scheduler job-runner ...
harr-codex-scheduler session-list ...
harr-codex-scheduler session-cwd ...
harr-codex-scheduler self-test
```

`codex-schedule`, `sol`, `terra`, `luna` and `codex-scheduler-ui` are thin shell entrypoints to that binary.

An `at` job always launches a **separate `harr-codex-scheduler job-runner` process**. The running Codex turn therefore does not depend on the GUI/tray process staying alive. The runner launches `codex exec --json`, captures JSONL output, updates the persistent task JSON and optionally writes the clean final answer. Closing or restarting the desktop app cannot lose the job output.

The desktop process watches the task-state directory using `QFileSystemWatcher`. Atomic task-state updates from the runner therefore refresh open tabs and tray state promptly. A slow reconciliation timer remains as a fallback; the runner and GUI do not require a socket or service daemon.

## Desktop app

The Qt Widgets UI is task-oriented:

- every open tab represents one scheduler task;
- `+` sits directly after the last tab;
- closing a tab closes only the view; non-empty tasks remain in persistent state;
- the left tasks sidebar can be hidden from the tab strip;
- **Active** and **History** are independently collapsible;
- task menus can reopen views, cancel scheduled/running jobs, delete scheduler state/logs, or explicitly delete an exported answer;
- task state lives under `$XDG_STATE_HOME/harr-codex-scheduler` (normally `~/.local/state/harr-codex-scheduler`).

### Sessions

Session choices come only from the documented App Server `thread/list` / `thread/read` APIs. `thread/list` requests `archived: false` and the application also defensively filters any returned `archived=true` entries.

The visible selector shows the human-readable session name/preview. The actual UUID remains the stored value and is shown in tooltips. A UUID pasted manually remains valid; when metadata is found through `thread/read`, the visible field is replaced by the session name while the UUID remains the real value.

Reading session metadata does not start a model turn, so session selection remains available when model usage is exhausted as long as the local Codex runtime is responsive.

### Tray-first workflow

The application is designed to live in the system tray. Its tray menu provides:

- **Open main window**;
- **Schedule for session** → one item per active/non-archived Codex session;
- a compact quick-schedule dialog containing only the selected session, run time and prompt;
- **Active tasks (N)** → clicking a task opens that task in the main window;
- completion/failure/cancellation notifications when persisted task state changes;
- **Quit**.

Normal quick scheduling therefore does not require opening the main workspace.

### Time picker

The picker defaults to **current local time + 05:02**, rounded to whole-minute `at` precision. It uses Qt widgets: date/calendar, `Today`, `Tomorrow`, `Now + 5:02` presets, and click-first hour/minute steppers. Monday is explicitly the first day of the calendar week. A past time is rejected while choosing the value, and the native CLI independently validates timestamps before invoking `at`.

### Theme

The app uses Qt's normal platform integration and standard widgets. A coherent application palette is applied when GNOME/Qt exposes a broken half-dark palette. Structural QSS is kept small and limited to application chrome such as tabs/sidebar/flat selectors.

`HARR_CODEX_THEME=dark|light|system` remains available for diagnostics.

## Build

Build dependencies on Ubuntu/Debian:

```bash
sudo apt install cmake ninja-build qt6-base-dev at git
```

Build and run directly from the checkout:

```bash
cmake -S tools/codex-scheduler \
      -B tools/codex-scheduler/build \
      -G Ninja \
      -DCMAKE_BUILD_TYPE=Release
cmake --build tools/codex-scheduler/build

tools/codex-scheduler/build/harr-codex-scheduler
```

Native smoke test:

```bash
QT_QPA_PLATFORM=offscreen \
HARR_CODEX_THEME=dark \
tools/codex-scheduler/build/harr-codex-scheduler self-test
```

Full native CLI/job-runner contract:

```bash
bash tools/codex-scheduler/tests/test_cli.sh
```

## Distribution

The supported formats are:

1. **`.deb` — primary Ubuntu/Debian distribution.** It contains the native C++ executable, desktop entry and thin shell selectors. It has no Python/PyQt dependency.
2. **`linux-<arch>.tar.gz` — portable/fallback bundle.** It contains the same native executable and uses the host Qt runtime to preserve normal distro/GNOME/Wayland integration.

OpenAI Codex CLI is not bundled and must be installed separately as `codex`.

### Build release artifacts

```bash
bash tools/codex-scheduler/packaging/build-release.sh
```

With version `0.2.0` on amd64 this produces:

```text
tools/codex-scheduler/dist/harr-codex-scheduler_0.2.0_amd64.deb
tools/codex-scheduler/dist/harr-codex-scheduler-0.2.0-linux-amd64.tar.gz
```

### Install `.deb`

```bash
sudo apt install ./tools/codex-scheduler/dist/harr-codex-scheduler_0.2.0_amd64.deb
```

or build and install in one step:

```bash
bash tools/codex-scheduler/install-ubuntu.sh
```

Run:

```bash
harr-codex-scheduler
```

Remove the application:

```bash
sudo apt remove harr-codex-scheduler
```

Package removal intentionally preserves task history. To also erase user state/logs:

```bash
rm -rf ~/.local/state/harr-codex-scheduler
```

### Portable bundle

```bash
tar -xzf harr-codex-scheduler-0.2.0-linux-amd64.tar.gz
cd harr-codex-scheduler-0.2.0-linux-amd64
./harr-codex-scheduler
```

Runtime dependencies are Qt 6 Widgets/Core/Gui, `at`, and `git`; no Python is required.

## Release tags

`tools/codex-scheduler/VERSION` is the release version source of truth. A matching tag builds and publishes the native `.deb` and tarball:

```bash
git tag codex-scheduler-v0.2.0
git push origin codex-scheduler-v0.2.0
```

The release workflow rejects a tag whose version does not match `VERSION`.

## Tests

Tests use fake `codex` and `at` executables and spend no Codex quota. The CI contract verifies:

- native C++/Qt build;
- state and transcript self-test;
- App Server cwd/session-list behavior including archived-session filtering;
- Sol/Terra/Luna High + Standard selector contracts;
- absolute timestamp validation;
- same-binary `job-runner` execution and answer/state persistence;
- `.deb` and portable package contents contain no Python;
- real `apt install` of the produced native package;
- installed binary self-test.
