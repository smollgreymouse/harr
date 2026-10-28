# Worker diagnostics runbook

Operator-facing map of the detached worker bridges (`common/mcp/gigacode_server.py`,
`common/mcp/einherjar_server.py`) and their on-disk diagnostics. Tool contracts
are unchanged; everything here is read-only observation.

## Where state lives

Both bridges keep all session state in files — there is no in-memory session
store, and every `status`/`messages`/`wait` call re-reads from disk. A bridge
restart therefore never loses state.

| File | Bridge | Purpose |
|---|---|---|
| `~/.cache/gigacode-mcp/<workspace-hash>/<sid>.state.json` | gigacode | Session phase machine, pid, handoff |
| `~/.cache/harr/einherjar/<instance>/<workspace-hash>/<sid>.state.json` | einherjar | Same, plus `backend`/`backend_config` |
| `<sid>.runtime.log` | both | Append-only human lines + structured JSON events |
| `<sid>.<turn>.stdout` / `.stderr` | both | Raw CLI output per turn |
| `<sid>.<job>.worker.log` | both | stdout+stderr of the detached worker process (its tracebacks land here) |
| `<sid>.<job>.job.json` | both | Pending job spec; unlinked when the job reaches a terminal state |
| `<sid>.<job>.control.json` | both | Cancel channel; unlinked after cancel is applied |
| `<sid>.<job>.progress.cursor` | gigacode | `wait` progress stream byte offset |
| `~/.gigacode/projects/*/chats/<sid>.jsonl` | gigacode | Vendor chat transcript (source of `messages`) |
| `~/.local/state/harr/gigacode-app/` | gigacode panel | `gigacode-ui-sessions.json` (ACTIVE), `gigacode-ui-invocations.json` (SCOPES), `gigacode-ui-server.jsonl` (+`.1` after rotation), `delivered-completions/` |
| `~/.local/state/harr/ein-ui/` | ein panel | Same set per instance |

The live-panel servers retain at most 256 in-memory transcript cursors each.
Least-recently-used entries are discarded; a panel whose cursor was evicted
falls back to the normal full transcript parse, so its revision and message
results are unchanged. Ein keys cursors by both instance and session.

Terminal completion notifications use a per-panel owner token for bounded
retries (three attempts). A repeated claim from that same panel recovers a
claim whose response was lost; a competing panel cannot take the claim. A
panel teardown cancels retry timers and pending request timers. If `ui/message`
delivered a message but its acknowledgement was lost, a retry can deliver a
duplicate: the UI protocol provides no idempotency key, so exactly-once
delivery cannot be guaranteed in that case.

## State phases (gigacode)

`queued → running → (cancelling) → cancelled | timed_out | completed → finished`
`finished` always carries `handoff` (the planner-facing JSON). `cancelled`
stays resumable. A `running`/`queued` state whose pids are dead reports
`FAILED` on the next `status` — the planner payload also embeds this as a
`blockers` entry, and the runtime log gets a `FAILED_EVIDENCE` event with the
artifact paths.

Einherjar collapses terminal transitions straight to `phase=finished` with a
`FAILED` handoff for owner-loss/cancel/timeout.

## Structured runtime events

Machine-readable records are single JSON lines (`"event"` field) interleaved
with the human-readable lines. Filter with:

```bash
grep '"event"' ~/.cache/gigacode-mcp/<hash>/<sid>.runtime.log | tail
```

| Event | Meaning | Key fields |
|---|---|---|
| `START` | Turn started | `turn`, `timeout_sec`, `backend` (ein) |
| `DETACHED` | Detached worker spawned | `job_id`, `worker_pid` |
| `CONFIRMED` | Startup handshake saw activity | `activity` |
| `PROGRESS` | Chat transcript grew | `chat_size`, `chat_age` |
| `RSS` | Agent CLI memory sample (Linux, every ~30s) | `pid`, `rss_kb`, `elapsed_sec` |
| `CANCEL` / `CANCEL_REQUEST` | Cancel applied / requested | `job_id`, `pid` |
| `TIMEOUT` | Hard timeout fired | `elapsed_sec`, `pid` |
| `OWNER_LOST` / `MCP_OWNER_LOST` | Owning MCP process died or its PID was reused | `classification`, `reason`, `owner_pid`, `owner_start_ticks` |
| `HANDOFF` | Worker produced the final handoff | `status`, `exit_code` |
| `END` | Turn ended | `exit_code`, `terminal_reason` (ein) |
| `FAILED_EVIDENCE` | Worker died without a handoff; artifact paths | `phase`, `worker_log`, `stdout_path`, `stderr_path` |
| `STATE_CORRUPT` | state.json unreadable (status stays UNKNOWN) | `path`, `error` |
| `PRUNE` | Old artifacts removed at launch | `removed` |

## Leak and retention behavior

- `_prune_worker_artifacts()` runs at every job launch and deletes
  stdout/stderr/worker.log/runtime.log/cursor files untouched for longer
  than the retention window. Default 14 days; `HARR_WORKER_RETENTION_SEC`
  overrides it (`0` disables pruning). `state.json`, job specs, and control
  files are lifecycle data and are never pruned.
- Active sessions rewrite their artifacts continuously, so nothing live is
  ever removed.
- Panel app servers bound their registries: invocation scopes expire after
  24h (cap 64), delivered-completions claims are capped (128 oldest-first),
  and the panel event log rotates at 5 MB (one `.1` generation kept).
- The worker monitor loops sample CLI RSS into the log; a growing `rss_kb`
  trend in `RSS` events is the leak signal for the vendor CLI itself.

## Common diagnoses

**Status says RUNNING but nothing happens** — check `pid_start_ticks`
mismatch: a reused PID no longer counts as alive; the state was written by
an older bridge if `pid_start_ticks` is absent.

**Worker stopped without a handoff** — read `FAILED_EVIDENCE` for
`worker_log`/`stdout_path`/`stderr_path`, then read those files; the
worker's own traceback is in `worker.log`.

**Bridge restarted mid-job** — look for `MCP_OWNER_LOST` with
`classification=owner_disappeared_possible_bridge_restart`. The detached
worker cancels itself on purpose; `reason=owner_pid_reused` vs
`owner_pid_missing` distinguishes PID reuse from a real exit.

**Panel feels heavy** — the long-poll reads the transcript incrementally
per session cursor; a full re-parse happens only when a panel pages from
behind. `server.jsonl` growth beyond one rotation indicates a hot loop in
a client.

## Where logs go

Stdio MCP servers inherit the stderr of whatever spawned them: the LeanCTX
gateway when on-demand, or journald (`journalctl --user -u harr-mcp@NAME`)
when run as a systemd unit. `harr mcp status` / `harr mcp logs NAME` remain
the entry points for service-level diagnostics.
