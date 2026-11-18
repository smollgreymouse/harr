# Harr Scheduler

Native Linux desktop scheduler for existing agent CLI sessions — **Codex** and **ZCode** today, one shared task store, tray and transcript UI. The scheduler is implemented entirely in **C++20 + Qt 6 Widgets**; there is no Python/PyQt runtime or Python scheduler code.

Every task targets one agent session. Before creating an `at` job, the scheduler asks the agent's own public API for the session's project directory (Codex App Server `thread/read`), verifies it and its Git worktree, then emits an `at` job beginning with `cd <session-cwd>`. The scheduler never inspects private agent state formats such as rollout JSONL files, SQLite databases, desktop runtime files or provider configs. `--cwd DIR` is available only as a fail-closed explicit fallback and must agree with agent metadata when both are available.

`--timestamp CCYYMMDDhhmm` schedules an absolute local date/time through `at -t`, so GUI tasks can be scheduled days or weeks ahead. CLI `--at` remains available for ordinary `at(1)` expressions.

## Agents

Every agent sits behind a small adapter that uses **public CLI/API surfaces only**. Internal app-server protocols, desktop-only transports and private state files are out of bounds.

| Agent | Session metadata | Model catalog | Turn execution |
|---|---|---|---|
| `codex` | Codex App Server `thread/list` / `thread/read` | App Server `model/list` | `codex exec -m … resume …` |
| `zcode` | **unavailable** — no public session-list CLI/API yet | **unavailable** — no public model-catalog CLI/API yet | `zcode [--resume <id>] --prompt <text> --cwd <workspace> --mode <mode> --json` |

### ZCode (public CLI contract)

Scheduled ZCode turns call the documented standalone CLI directly:

```text
zcode --prompt <text> --cwd <workspace> --mode <build|edit|plan|yolo|guarded> --json
zcode --resume <sessionId> --prompt <text> --cwd <workspace> --mode <mode> --json
```

- `--resume` is added only when the task targets an existing session; sessions are not enumerable, so the GUI keeps the session field as manual paste and project verification stays explicitly unavailable until ZCode exposes a public session API.
- The CLI documents no `--model` launch flag (model selection is configuration-driven), so the scheduler forwards none; the model catalog stays blocked until a public enumeration API appears.
- `--json` emits NDJSON; the terminal `type=result` record carries the final response and feeds the saved answer and transcript.
- Permission modes default to **yolo** for unattended scheduled turns.
- Because headless ZCode runs currently cannot select a model ("Select a model before sending a message" on resume/new turns), actual turn execution remains blocked upstream until ZCode ships a public model-selection contract; the scheduler surfaces that error in the task transcript rather than working around it with internal APIs.

## One native executable

`harr-scheduler` is both the desktop application and the execution backend. It has internal command modes for scheduling, job execution, agent turns and agent metadata lookup:

```text
harr-scheduler                 # GUI + tray
harr-scheduler schedule ...    # --agent codex|zcode
harr-scheduler job-runner ...
harr-scheduler session-list ...
harr-scheduler session-cwd ...
harr-scheduler self-test
```

`harr-schedule`, `codex-schedule`, `sol`, `terra`, `luna` and `codex-scheduler-ui` are thin shell entrypoints to that binary. The 0.3.x package name `harr-codex-scheduler` is replaced by the `.deb`; postinst keeps a compatibility symlink so at jobs queued before the upgrade still run.

An `at` job always launches a **separate `harr-scheduler job-runner` process**. The running agent turn therefore does not depend on the GUI/tray process staying alive. The runner launches the agent's CLI executor, captures its JSONL event stream (codex events natively, zcode `--json` NDJSON via the shared parser), updates the persistent task JSON and optionally writes the clean final answer. Closing or restarting the desktop app cannot lose the job output.

The desktop process watches the task-state directory using `QFileSystemWatcher`. Atomic task-state updates from the runner therefore refresh open tabs and tray state promptly. A slow reconciliation timer remains as a fallback; the runner and GUI do not require a socket or service daemon.

## Desktop app

The Qt Widgets UI is task-oriented:

- every open tab represents one scheduler task;
- each task page has an agent selector; switching it clears the session binding and repopulates the model/session catalogs for that agent;
- only the selectors an agent supports are visible: model/reasoning/speed for Codex, model/mode for ZCode;
- `+` sits directly after the last tab;
- closing a tab closes only the view; non-empty tasks remain in persistent state;
- the left tasks sidebar can be hidden from the tab strip;
- **Active** and **History** are independently collapsible;
- scheduled tasks that have not started can be reopened for editing; the old `at` job is removed first, then the same task returns to draft state and can be rescheduled;
- task menus can reopen views, cancel scheduled/running jobs, delete scheduler state/logs, or explicitly delete an exported answer;
- task state lives under `$XDG_STATE_HOME/harr-scheduler` (normally `~/.local/state/harr-scheduler`); 0.3.x state under `harr-codex-scheduler` is migrated once automatically.

### Models

Model catalogs come from the agent APIs, never from a hardcoded list. Codex fills the selector through the App Server `model/list` API; ZCode reads the account providers and their `builtinModelIds` from the builtin provider config the ZCode CLI itself consumes. The GUI uses the agent's display names and selects the advertised default model for a new draft when one is advertised. The catalog is refreshed at startup and periodically while the application is running.

Reading a model catalog does not start a model turn, so the selector can still be populated when inference usage is exhausted.

### Sessions

Session choices come only from the agents' documented APIs (Codex App Server `thread/list`/`thread/read`; ZCode Protocol `session/list`). Archived entries are filtered defensively, and subagent ZCode sessions are hidden.

The visible selector shows the human-readable session name/preview. The actual session id remains the stored value and is shown in tooltips. An id pasted manually remains valid; when metadata is found, the visible field is replaced by the session name while the id remains the real value.

### Tray-first workflow

The application is designed to live in the system tray. Its tray menu provides:

- **Open main window**;
- **Schedule for session** → one submenu per agent with that agent's active/non-archived sessions;
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
sudo apt install cmake qt6-base-dev at git
```

Build and run directly from the checkout:

```bash
cmake -S tools/codex-scheduler \
      -B tools/codex-scheduler/build \
      -DCMAKE_BUILD_TYPE=Debug
cmake --build tools/codex-scheduler/build

tools/codex-scheduler/build/harr-scheduler
```

Native smoke test:

```bash
QT_QPA_PLATFORM=offscreen \
HARR_CODEX_THEME=dark \
tools/codex-scheduler/build/harr-scheduler self-test
```

Full native CLI/job-runner contract (fake `codex`, `zcode` and `at` executables, no agent quota):

```bash
bash tools/codex-scheduler/tests/test_cli.sh
```

## Distribution

The supported formats are:

1. **`.deb` — primary Ubuntu/Debian distribution.** It contains the native C++ executable, desktop entry and thin shell selectors. It has no Python/PyQt dependency.
2. **`linux-<arch>.tar.gz` — portable/fallback bundle.** It contains the same native executable and uses the host Qt runtime to preserve normal distro/GNOME/Wayland integration.

Agent CLIs are not bundled; install `codex` and/or `zcode` separately.

### Build release artifacts

```bash
cmake -S tools/codex-scheduler \
      -B tools/codex-scheduler/build-release \
      -DCMAKE_BUILD_TYPE=Release
cmake --build tools/codex-scheduler/build-release --target package-release
```

With version `0.4.0` on amd64 this produces:

```text
tools/codex-scheduler/dist/harr-scheduler_0.4.0_amd64.deb
tools/codex-scheduler/dist/harr-scheduler-0.4.0-linux-amd64.tar.gz
```

### Install `.deb`

```bash
sudo apt install ./tools/codex-scheduler/dist/harr-scheduler_0.4.0_amd64.deb
```

or build and install in one step:

```bash
bash tools/codex-scheduler/install-ubuntu.sh
```

Run:

```bash
harr-scheduler
```

Remove the application:

```bash
sudo apt remove harr-scheduler
```

Package removal intentionally preserves task history. To also erase user state/logs:

```bash
rm -rf ~/.local/state/harr-scheduler
```

### Portable bundle

```bash
tar -xzf harr-scheduler-0.4.0-linux-amd64.tar.gz
cd harr-scheduler-0.4.0-linux-amd64
./harr-scheduler
```

Runtime dependencies are Qt 6 Widgets/Core/Gui, `at`, and `git`; no Python is required.

## Release tags

`tools/codex-scheduler/VERSION` is the release version source of truth. A matching tag builds and publishes the native `.deb` and tarball:

```bash
git tag codex-scheduler-v0.4.0
git push origin codex-scheduler-v0.4.0
```

The release workflow rejects a tag whose version does not match `VERSION`.

## Tests

Tests use fake `codex`, `zcode` and `at` executables and spend no agent quota. The CI contract verifies:

- native C++/Qt build;
- state, migration and transcript self-test;
- agent registry, per-agent exec command contracts and explicit unavailability of zcode session/model surfaces;
- Codex App Server cwd/session-list behavior including archived-session filtering;
- zcode public-CLI process contract: new turn, resume, mode, NDJSON result parsing, non-zero exit, cancel, cwd handling — and that `app-server` is never invoked;
- Sol/Terra/Luna High + Standard selector contracts;
- absolute timestamp validation;
- same-binary `job-runner` execution and answer/state persistence for codex and zcode turns;
- `.deb` and portable package contents contain no Python;
- real `apt install` of the produced native package;
- installed binary self-test.
