# Harr Doctor — detailed development and safe-repair plan

Status: **v1 implemented on `feature/harr-doctor`**. Read-only local/E2E diagnosis, registry-declared safe probes, install provenance, JSON/strict modes, and deterministic R1 repair with snapshot/rollback are implemented. R2 targeted runtime repair and R3 automatic stale-child refresh intentionally remain **BLOCKED/fail-closed** until Harr has a per-server install primitive and verified host respawn proof.
Primary command: `harr doctor`  
Scope: Harr installation integrity, LeanCTX runtime, selected MCPs, host routing, live-process health, and conservative recovery.

## 1. Why this command is needed

Harr already has `harr status`, component-specific status commands, and upstream `lean-ctx doctor`, but it currently lacks one Harr-level command that proves the complete managed route an agent will actually use.

The incident diagnosed on 2026-10-29 is the mandatory regression case:

- `harr secret status` reported GitLab as configured.
- GitLab was selected in the Harr MCP registry.
- GitLab MCP runtime was installed.
- LeanCTX config was managed and contained the expected secret-memento route `mcp/gitlab/default`.
- However, `~/.local/bin/lean-ctx` had been replaced by a raw LeanCTX ELF binary, bypassing the Harr wrapper.
- Therefore the private GitLab secret existed but was never injected into new LeanCTX processes as the memento expected by the gateway.
- Existing LeanCTX MCP processes were running from a deleted old executable and lacked the memento.
- The gateway therefore registered GitLab with 0 tools and reported `missing secret memento mcp/gitlab/default`.
- A separate legacy direct Codex GitLab MCP registration used another PAT, so its failing health check was not testing the Harr credential.
- Restoring the Harr launcher and replacing only stale LeanCTX MCP children restored the gateway path. A fresh `gitlab::health_check` returned `status=ok`, `authenticated=true`, and the GitLab tool catalog became available.

The failure was not “the GitLab token is bad”. It was a broken chain between installation, wrapper, process environment, gateway and client routing.

The doctor must answer:

> If an agent tries to use every Harr-selected capability right now, does the complete Harr-managed path actually work; if not, what exact layer is broken, and can Harr restore that layer safely without damaging unrelated state?

## 2. Principles

The doctor must be built around these rules:

1. **Diagnose before mutating.**
2. **Repair only what Harr owns.**
3. **Never infer that a missing/failed dependency should be deleted or replaced.**
4. **Never rotate credentials automatically.**
5. **Never overwrite user/project configuration that Harr does not own.**
6. **Prefer the smallest reversible repair.**
7. **Take a safety snapshot before every repair that changes files or host configuration.**
8. **Re-run the exact failed checks after repair.**
9. **If preconditions are ambiguous, stop and report instead of “trying something”.**
10. **Never call destructive MCP tools as health probes.**
11. **Never print secrets.**
12. **A repair mode must be explicitly requested by the user.**
13. **The Harr skill must not trigger repair merely because doctor found failures.**
14. **Source checkout state is not automatically installation truth. Installed provenance is authoritative.**

## 3. Command surface

### Diagnostic mode

```sh
harr doctor
harr doctor --local
harr doctor --json
harr doctor --verbose
harr doctor --strict
harr doctor gitlab
```

### Repair mode

Recommended explicit form:

```sh
harr doctor --repair
harr doctor gitlab --repair
```

Optional safer staged form:

```sh
harr doctor --repair --dry-run
```

Do **not** make plain `harr doctor` mutate the system.

### Semantics

- `harr doctor`: full read-only end-to-end diagnosis.
- `--local`: no external API probes.
- `--json`: stable machine-readable report.
- `--verbose`: expanded evidence, PIDs, expected/actual identities and repair reasoning, still redacted.
- `--strict`: WARN contributes to non-zero exit.
- `NAME`: focus downstream checks on one selected MCP while still running core checks required to trust its route.
- `--repair`: perform only repair actions that have passed explicit safety preconditions.
- `--repair --dry-run`: compute and show the repair plan without changing state.

## 4. Status model

Every check must return one of:

- `PASS` — expected state proven.
- `WARN` — usable but drift/shadow/stale/noncanonical state exists.
- `FAIL` — selected capability cannot be trusted through the expected Harr route.
- `SKIP` — not applicable, disabled, blocked by `--local`, or unsupported on this platform.

Repair actions separately return:

- `NOT_NEEDED`
- `PLANNED`
- `REPAIRED`
- `BLOCKED`
- `FAILED`
- `ROLLED_BACK`

Suggested exit codes:

- `0`: no FAIL after final verification.
- `1`: one or more FAIL remain.
- `2`: invalid invocation or doctor internal/config metadata error.
- `3`: repair attempted but rollback was required or repair could not safely complete.

With `--strict`, WARN makes the final result non-zero.

## 5. Diagnostic layers

### A. Harr installation provenance

Add an immutable install manifest, for example:

```text
~/.local/libexec/harr/install-manifest.json
```

Suggested fields:

```json
{
  "schema": 1,
  "harr_version": "0.2.8",
  "install_type": "package|source",
  "installed_at": "...",
  "source": {
    "repository": "...",
    "commit": "...",
    "dirty": false
  },
  "leanctx": {
    "version": "3.11.0",
    "build": "3.11.0-harr-workspace.4",
    "identity": "..."
  },
  "managed_files": {
    "~/.local/bin/harr": "sha256:...",
    "~/.local/bin/lean-ctx": "sha256:..."
  }
}
```

Checks:

- Harr version and install root.
- Harr launcher identity.
- managed file integrity.
- LeanCTX expected build identity.
- install origin and source commit for source installs.
- legacy installation without manifest -> WARN, not automatic FAIL.

Important: doctor compares installed state to the install manifest, **not** to whichever source checkout happens to be open.

### B. LeanCTX launcher integrity

Validate `~/.local/bin/lean-ctx` is the Harr wrapper:

- exists and executable;
- contains Harr wrapper marker;
- points to expected Harr vendor build;
- wrapper manager path exists;
- effective registry path exists;
- real LeanCTX exists;
- real build identity matches installed provenance.

This exact check must catch “raw ELF copied over Harr wrapper”.

### C. LeanCTX config

Checks:

- managed config exists;
- Harr ownership marker present;
- config validates;
- rendered gateway set matches effective selected registry;
- each selected server appears exactly once;
- runner is Harr-managed;
- secret memento declarations match registry.

### D. Secrets and memento wiring

For every selected MCP secret:

1. registry record exists;
2. private secret file exists when required;
3. file permissions are acceptable;
4. memento id is valid;
5. target env/header declaration is valid;
6. rendered LeanCTX config uses the same memento;
7. fresh wrapper execution proves presence of the expected memento variable in the child environment.

Only variable **names/presence** may be reported. Never values.

### E. Live process audit

Doctor must distinguish “fresh install is correct” from “current GUI/client still holds stale children”.

Linux checks:

- enumerate LeanCTX MCP children of supported hosts;
- record parent/client;
- executable path;
- `(deleted)` executable mappings;
- unexpected/non-vendor executable;
- expected memento variable names present/absent;
- multiple runtime generations.

Equivalent platform-specific checks should be implemented on macOS/Windows where possible; unsupported subchecks return SKIP.

### F. Host/client routing

For Codex and OpenCode:

- LeanCTX command points to Harr launcher;
- expected args are present;
- Harr-managed policy/config ownership intact;
- no alternate LeanCTX route shadows Harr;
- no direct duplicate MCP registration conflicts with an MCP already selected behind Harr gateway.

Direct duplicates are classified:

- identical benign duplicate -> WARN;
- same logical MCP with different credential/config -> WARN shadow;
- host bypasses Harr where Harr selection requires gateway -> FAIL.

### G. Runtime prerequisites

For every selected MCP:

- runtime executable/package exists;
- expected package/version is installed;
- external prerequisite exists;
- offline probe/cache readiness succeeds where declared;
- required non-secret env config exists and parses.

Example: selected GigaCode with missing `gigacode` CLI -> FAIL before handshake.

### H. Fresh LeanCTX + gateway handshake

Doctor must launch a **fresh temporary LeanCTX through the Harr wrapper** and perform real MCP initialize.

Then through `ctx_tools`:

- refresh/list gateway;
- confirm every selected server appears;
- collect tool counts;
- capture handshake errors per server.

The fresh session is authoritative for “would a newly started client work now?”.

### I. Full catalog validation

“All registered tools” means validate all registered tool definitions, not execute them.

For every tool:

- non-empty name;
- unique server-local name;
- valid input schema structure;
- unique gateway-qualified name;
- LeanCTX can index it;
- required tools declared by Harr are present.

### J. Safe live probes

Each server may declare one explicitly reviewed read-only probe in registry metadata.

Never infer safety from a tool name.

Proposed registry form:

```json
"doctor": {
  "required_tools": ["health_check"],
  "probe": {
    "kind": "tool",
    "tool": "health_check",
    "arguments": {},
    "timeout_sec": 10,
    "success": {
      "json_content": {
        "status": "ok",
        "authenticated": true
      }
    }
  }
}
```

Supported probe kinds:

- `catalog-only`
- `mcp-ping`
- `tool`

Unknown probe kinds are registry errors.

## 6. Initial MCP probes

### CodeGraph

- required tool: `codegraph_explore`;
- probe: catalog-only in v1;
- do not invent a semantic query solely for doctor.

### GitLab

Required tools include:

- `health_check`;
- `get_merge_request` because Harr workflows depend on it.

Probe:

```text
gitlab::health_check
```

Success requires:

- MCP call success;
- `status == ok`;
- `authenticated == true`.

### Grafana

Required tool:

- `user_info`.

Probe:

```text
grafana::user_info
```

Successful non-error read is enough.

### Kibana

Required tool:

- `list_data_views`.

Probe:

```text
kibana::list_data_views
```

### Jira

Required tool:

- `jira_get_all_projects`.

Probe:

```text
jira::jira_get_all_projects
```

Preserve Jira’s existing authenticated preflight and report whether failure occurred in preflight vs MCP call.

### GigaCode

Required tool:

- `gigacode`.

Do not invoke `start`, `resume`, `wait`, `messages` or `cancel`.

Health is:

- required CLI exists;
- MCP initialize succeeds;
- catalog contains `gigacode`.

## 7. Safe repair architecture

Repair is part of doctor, but it must be **strictly staged**.

### Stage 1 — diagnose

Run all applicable checks and produce an immutable diagnosis object.

No mutations.

### Stage 2 — derive repair plan

Map each failure to a repair action only if:

- Harr owns the affected asset;
- the expected state is proven from installed provenance/effective registry;
- the action is bounded and reversible;
- the repair does not require guessing user intent;
- the action does not require replacing/rotating a secret.

If any precondition is uncertain, mark repair `BLOCKED`.

### Stage 3 — safety snapshot

Before the first mutation:

- snapshot affected Harr-managed files/config;
- record process list and current expected identities;
- preserve old launcher/config exactly;
- do not snapshot secret contents into logs/output;
- reuse Harr’s existing snapshot mechanisms where possible.

Repair session metadata should have a unique id and a local private directory.

### Stage 4 — minimal repair

Perform only actions required by the proven failures.

### Stage 5 — post-repair verification

Re-run:

- the exact failed checks;
- core launcher/config/memento checks;
- affected MCP handshake/catalog/probe.

### Stage 6 — rollback on regression

If repair worsens state or the postcondition fails in a way indicating the mutation was harmful:

- restore the safety snapshot;
- report `ROLLED_BACK`;
- leave unrelated state untouched.

Do not keep applying additional speculative fixes.

## 8. Repair classes

Repairs must be classified by risk.

### Class R0 — no mutation

Examples:

- report missing external GigaCode dependency;
- report expired/invalid PAT;
- report unsupported platform check;
- report source/install drift.

Doctor cannot safely repair these automatically.

### Class R1 — deterministic Harr-owned file restoration

Examples:

- Harr `lean-ctx` wrapper replaced by raw ELF;
- Harr launcher missing;
- Harr-generated LeanCTX config differs from effective selected registry;
- Harr-managed skills/policy file missing or corrupted.

Allowed only when installed manifest and Harr source-of-truth make expected bytes/config unambiguous.

This is the primary repair class for the 2026-10-29 incident.

### Class R2 — Harr-owned runtime reinstallation

Examples:

- expected vendor LeanCTX binary missing/corrupt;
- selected pinned npm MCP package missing/version mismatch;
- cached uvx runtime missing when Harr has an explicit prefetch/install route.

Repair may call existing Harr install primitives, but only for the affected managed component.

Avoid broad `harr install all` unless multiple independent managed components are proven broken and the repair plan explicitly lists them.

### Class R3 — stale child process refresh

Examples:

- current Codex/OpenCode owns LeanCTX children running deleted/non-managed executables;
- fresh doctor session passes but live client child is stale.

Safe behavior must be conservative:

1. identify child as a Harr LeanCTX MCP child of a supported host;
2. prove it is stale/deleted/wrong generation;
3. terminate **only that child**, not the host application;
4. allow host to respawn it;
5. verify respawned process uses expected vendor binary and memento names.

If host does not respawn or process ownership is ambiguous, stop and report. Do not kill the entire IDE/app automatically.

### Class R4 — shadow registration cleanup

Potentially dangerous. Do **not** auto-delete in v1.

Doctor may report:

```text
direct GitLab shadow registration detected
suggested repair: remove legacy direct registration
```

Actual cleanup should require a separately explicit action in a later version or a highly constrained `--repair-shadow` mode.

Reason: a direct MCP registration may have been intentionally created outside Harr.

### Class R5 — credential repair

Never automatic.

If a safe probe proves authentication failure:

- report which Harr secret name is implicated;
- suggest `harr secret set NAME`;
- do not reuse another credential;
- do not copy from a direct MCP registration;
- do not rotate;
- do not prompt in noninteractive doctor repair unless explicitly designed later.

## 9. Repairs for the 2026-10-29 regression

Given:

- installed provenance says Harr wrapper should own `~/.local/bin/lean-ctx`;
- path contains raw ELF;
- vendor LeanCTX build exists and matches expected identity;
- Harr wrapper source exists;

`harr doctor --repair` should be able to:

1. snapshot the unexpected launcher;
2. restore the exact Harr wrapper;
3. validate wrapper marker and referenced vendor build;
4. launch a temporary child and verify expected memento names are injected;
5. inspect live client LeanCTX MCP children;
6. terminate only stale children using deleted/non-managed executable;
7. verify respawned children use the expected vendor LeanCTX and memento names;
8. refresh a fresh gateway diagnostic session;
9. run GitLab `health_check`;
10. report PASS if authenticated.

It must **not**:

- overwrite the PAT;
- copy the old direct Codex PAT into Harr;
- remove direct GitLab registration automatically;
- restart Codex itself;
- reinstall unrelated MCPs;
- change Git config/SSH.

## 10. Repair plan UX

Before mutating, human output should show something like:

```text
Repair plan

1. Restore Harr-managed LeanCTX launcher
   reason: launcher is an unmanaged ELF
   source: installed Harr provenance
   risk: low
   rollback: exact current launcher snapshot

2. Refresh 8 stale LeanCTX MCP child processes
   reason: executable mapping is deleted and predates repaired launcher
   scope: child processes only
   host process will not be terminated

No credentials will be changed.
No direct MCP registrations will be removed.
```

For `--repair --dry-run`, stop there.

For actual `--repair`, apply the plan without asking another interactive question because the user already explicitly requested repair.

## 11. Repair idempotency

Every repair action must be idempotent:

- restoring an already-correct launcher -> NOT_NEEDED;
- regenerating an already-matching managed config -> NOT_NEEDED;
- no stale processes -> NOT_NEEDED;
- runtime already pinned/healthy -> NOT_NEEDED.

A second `harr doctor --repair` on a healthy system must perform no mutations.

## 12. Harr skill integration

The Harr diagnostic skill is updated in the same change as the v1 command. Keep this atomic: do **not** advertise doctor/repair behavior that the installed implementation cannot perform.

The skill should teach the model a strict escalation policy.

### Normal diagnosis

For Harr installation/runtime/MCP failures:

```text
harr doctor
```

should become the preferred first high-level diagnostic command.

Use focused form when the user names a component:

```text
harr doctor gitlab
```

The skill should explain that `harr status` remains the cheap snapshot while `harr doctor` performs end-to-end validation.

### Repair policy in the skill

The skill must explicitly say:

> Never run `harr doctor --repair` merely because doctor reports a failure. Repair mutates Harr-owned runtime state and may terminate stale Harr child processes. Run repair only when the user explicitly asks to repair, restore, fix, recover, or otherwise authorizes mutation.

This follows the same safety principle used for optional executors: diagnostics may be proactive when relevant, mutations require user intent.

Examples:

User says:

```text
проверь почему gitlab mcp не работает
```

Allowed:

```text
harr doctor gitlab
```

Not allowed automatically:

```text
harr doctor gitlab --repair
```

User says:

```text
почини gitlab mcp штатными средствами harr
```

Allowed:

```text
harr doctor gitlab --repair
```

because repair intent is explicit.

### Skill rules for repair

The Harr skill should include these operational constraints:

1. Prefer `harr doctor NAME --repair` over manual file replacement when doctor knows the repair.
2. Do not manually reproduce doctor repair steps unless doctor says repair is BLOCKED and the user explicitly requests deeper intervention.
3. Never expose or copy secret values while diagnosing/repairing.
4. Never replace an invalid Harr credential with a credential discovered in another client registration.
5. Never remove shadow/direct MCP registrations automatically.
6. Never terminate the host Codex/OpenCode app automatically; only doctor-owned validated stale children may be refreshed.
7. If repair reports ROLLED_BACK, stop and report evidence rather than attempting a second speculative repair path.
8. If doctor reports BLOCKED, surface the blocking precondition and suggested explicit next action.
9. Treat doctor’s post-repair verification as authoritative; do not claim success solely because a command exited zero.
10. Do not bypass Harr repair with upstream LeanCTX installers or unmanaged package upgrades.

### Proposed Harr skill command block

After implementation, add:

```text
harr status
harr doctor [NAME]
harr doctor [NAME] --local
harr doctor [NAME] --repair
harr doctor [NAME] --repair --dry-run
```

And accompanying text:

```text
Use `harr status` for a cheap configuration snapshot.
Use `harr doctor` for end-to-end Harr runtime diagnostics.
Repair is conservative and Harr-owned, but mutating: use `--repair` only with explicit user repair intent.
```

This skill change should ship atomically with the command implementation and tests.

## 13. Registry doctor metadata

Doctor behavior should be declared in the shared registry rather than hard-coded by server name.

Recommended schema:

```json
{
  "doctor": {
    "required_tools": ["..."],
    "probe": {
      "kind": "catalog-only|mcp-ping|tool",
      "tool": "...",
      "arguments": {},
      "timeout_sec": 10,
      "success": {}
    },
    "repair": {
      "runtime_reinstall": true,
      "credential_auto_repair": false
    }
  }
}
```

The `repair` section expresses only generic permissions/capabilities. It must not contain arbitrary shell commands.

Validation rules:

- unknown probe/repair fields are rejected;
- tool probe must name an explicitly reviewed tool;
- timeout is bounded;
- no secret values;
- no arbitrary executable snippets;
- server-specific repair may only call Harr-owned generic primitives.

## 14. Internal implementation architecture

Recommended structure:

```text
common/doctor/
  model.py
  registry.py
  installation.py
  leanctx.py
  gateway.py
  catalog.py
  probes.py
  repair.py
  redact.py
  output.py
  platform/
    linux.py
    macos.py
    windows.py
```

The exact file layout may differ, but responsibilities should remain separated.

### Diagnostic model

Represent every check with:

- stable check id;
- scope;
- status;
- summary;
- evidence;
- remediation hint;
- repairability;
- dependency check ids.

### Repair model

A repair action needs:

- stable action id;
- affected check ids;
- risk class;
- preconditions;
- mutations;
- rollback description;
- postconditions.

Do not implement repair as an ad-hoc list of shell commands assembled from error text.

### CLI shell layer

The Harr shell front-end should only parse and dispatch:

```text
harr doctor ...
```

Use a shared implementation for actual protocol/JSON/process logic. Python is a natural fit because Harr already uses Python for the MCP registry manager.

## 15. Relationship to existing commands

### `harr status`

Question answered:

> What is configured/installed?

Properties:

- fast;
- mostly static/local;
- good for routine overview.

### `harr doctor`

Question answered:

> Does the complete managed path work, and where is it broken?

Properties:

- fresh wrapper/process checks;
- gateway handshake;
- tool catalog validation;
- safe remote probes;
- live stale-process audit.

### `harr doctor --repair`

Question answered:

> Can Harr restore the broken Harr-owned layers conservatively and prove the result?

Properties:

- explicit mutation;
- repair plan;
- snapshot;
- minimal repair;
- verification;
- rollback.

Do not collapse these three modes into one command behavior.

## 16. Security and redaction

Mandatory rules:

1. Never print secret values.
2. Never print secret hashes by default.
3. Environment inspection reports variable names/presence only.
4. Captured MCP stderr/stdout is redacted before presentation or persistence.
5. Safe tool probes are registry-declared.
6. Unknown tools are never invoked by doctor.
7. TLS verification is never disabled by doctor.
8. Doctor never switches authentication methods implicitly.
9. Doctor never copies secrets between registrations.
10. Repair snapshots containing private configuration remain private and mode-restricted.
11. Repair logs must describe secret operations symbolically, e.g. `gitlab secret present`.
12. JSON output follows the same rules.

## 17. Concurrency, timeouts and process safety

Target normal healthy runtime: under one minute.

Suggested budgets:

- local checks: a few seconds;
- LeanCTX initialize: 10 s;
- downstream server handshake: 10–15 s each;
- safe API probe: 10 s each;
- child respawn verification after R3 repair: bounded, e.g. 10–15 s.

Use one fresh LeanCTX diagnostic session when possible.

Do not leave background child processes behind.

Repair process refresh must:

- signal only proven stale Harr LeanCTX child;
- never use broad `pkill lean-ctx`;
- never kill by name alone;
- verify parent PID/identity;
- verify executable generation;
- record exactly which PID was touched.

## 18. Human output examples

### Broken installation before repair

```text
Harr Doctor 0.2.8

Installation
  provenance ............... PASS
  LeanCTX vendor build ..... PASS
  LeanCTX launcher ......... FAIL
    expected Harr wrapper
    found unmanaged ELF

Secrets
  gitlab secret ............ PASS
  gitlab memento config .... PASS
  fresh injection .......... FAIL
    Harr wrapper bypassed

Live runtime
  LeanCTX sessions ......... FAIL
    8 stale process(es)
    8 using deleted executable
    expected GitLab memento absent

Gateway
  gitlab ................... FAIL
    0 tools
    missing secret memento mcp/gitlab/default

Routing
  direct GitLab shadow ..... WARN
    direct registration uses a different credential

Result: FAIL
Repairable Harr-owned failures: 2
Non-automatic warnings: 1
```

### Dry-run repair

```text
$ harr doctor gitlab --repair --dry-run

Planned:
  R1 restore Harr LeanCTX wrapper
  R3 refresh 8 stale Harr LeanCTX child processes

Blocked/not changed:
  direct GitLab shadow registration
  credentials

No changes made.
```

### After successful repair

```text
Repair
  restore launcher ......... REPAIRED
  refresh stale children ... REPAIRED

Verification
  launcher ................. PASS
  memento injection ........ PASS
  live process generation .. PASS
  gitlab tools ............. PASS 216
  gitlab health ............ PASS authenticated

Remaining
  direct GitLab shadow ..... WARN

Result: PASS with 1 warning
```

## 19. JSON output and repair journal

Stable JSON should include both diagnosis and repair.

Conceptual shape:

```json
{
  "schema": 1,
  "harr_version": "0.2.8",
  "result": "pass",
  "checks": [],
  "repair": {
    "requested": true,
    "dry_run": false,
    "session_id": "...",
    "actions": [
      {
        "id": "leanctx.launcher.restore",
        "class": "R1",
        "status": "repaired"
      }
    ],
    "rollback": {
      "performed": false
    }
  }
}
```

A private local repair journal may be retained for rollback/audit, but must not store secret values.

## 20. Mandatory regression tests

### A. Raw ELF overwrites Harr wrapper

Expected:

- launcher FAIL;
- R1 repair available;
- repair restores wrapper from installed source of truth;
- post-repair injection PASS.

### B. Secret exists but memento injection missing

Expected:

- secret presence PASS;
- config route PASS;
- injection FAIL;
- no credential replacement;
- repair only if injection failure is due to a proven Harr-owned wrapper/config defect.

### C. Stale deleted LeanCTX processes

Expected:

- fresh installation checks may PASS;
- live runtime FAIL/WARN;
- R3 action targets only stale children;
- host process untouched;
- respawn verified.

### D. Selected MCP has 0 tools

Expected:

- FAIL;
- root cause records handshake/runtime error;
- no speculative tool calls.

### E. Missing external prerequisite

Example GigaCode CLI absent.

Expected:

- FAIL;
- repair BLOCKED/R0 unless Harr explicitly owns installation of that dependency;
- no package manager guessing.

### F. Direct duplicate GitLab registration

Expected:

- gateway health independently reported;
- shadow WARN;
- v1 repair does not remove it.

### G. Direct GitLab uses different credential

Expected:

- report only `credential differs`;
- no values/hashes;
- no copying between stores.

### H. GitLab auth failure with correct launcher

Expected:

- installation PASS;
- memento injection PASS;
- catalog may PASS;
- `health_check authenticated=false` FAIL;
- credential repair R5/manual.

### I. Required tool absent

Example `get_merge_request` absent.

Expected:

- tool count may be > 0;
- required-tool validation FAIL.

### J. Malformed tool schema

Expected:

- handshake may PASS;
- catalog validation FAIL;
- identify qualified tool safely.

### K. Current source checkout differs from installed source

Expected:

- installed manifest remains authoritative;
- normal doctor does not fail;
- optional verbose drift note only.

### L. Legacy install lacks provenance manifest

Expected:

- WARN;
- other checks continue;
- repair that requires exact provenance may be BLOCKED rather than guessed.

### M. Rollback path

Inject failure after launcher replacement but before postcondition.

Expected:

- restore exact snapshot;
- action status ROLLED_BACK;
- no second speculative repair.

### N. Repair idempotency

Run repair twice.

Expected:

- first repairs;
- second has zero mutations.

### O. Secret redaction

Seed recognizable sentinel secrets into files/env/stderr.

Expected:

- sentinel absent from terminal output;
- absent from JSON;
- absent from repair journal.

### P. `--local`

Expected:

- no external API call;
- API probes SKIP;
- local repair may still be available if explicitly requested and all safety preconditions are local/proven.

### Q. Skill policy regression

Automated/documentation test should ensure Harr skill wording preserves:

- plain diagnosis may invoke doctor;
- repair requires explicit repair intent;
- no automatic `--repair` after a failed diagnosis.

## 21. Cross-platform matrix

Linux v1 should support the full feature set including `/proc`-based stale/deleted process detection.

macOS and Windows should implement equivalent safe process identity mechanisms incrementally.

Golden rule:

> Missing platform implementation yields SKIP, never a false PASS and never a guessed repair.

A repair requiring an unsupported process check is BLOCKED.

## 22. Development phases

### Phase 0 — contract and tests

- commit this design;
- finalize CLI semantics;
- finalize result/repair states;
- finalize registry doctor schema;
- write regression fixtures for the 2026-10-29 incident;
- write redaction tests.

### Phase 1 — install provenance

- write install manifest for package and source installs;
- record source commit/dirty bit;
- record Harr/LeanCTX identities;
- support legacy installation without manifest.

### Phase 2 — read-only local doctor

Implement `harr doctor --local`:

- installation;
- launcher;
- config;
- registry;
- secret declarations;
- memento wiring;
- runtime prerequisites;
- host routing;
- duplicate/shadow registrations.

### Phase 3 — fresh memento proof

Add safe child-environment presence checks through the real Harr wrapper.

This phase alone must catch the main incident without network access.

### Phase 4 — MCP diagnostic client

Implement bounded MCP protocol client:

- initialize;
- tools/list;
- LeanCTX `ctx_tools refresh/list/find/call`;
- deterministic shutdown;
- redacted diagnostics.

### Phase 5 — catalog checks and safe probes

- validate all registered tool definitions;
- required-tool checks;
- add reviewed registry probes;
- end-to-end health for every selected MCP.

### Phase 6 — live process audit

Linux:

- host parent detection;
- executable generation;
- deleted executable;
- expected memento variable names.

Then macOS/Windows.

### Phase 7 — repair planner, dry-run only — implemented

Implement:

```text
harr doctor --repair --dry-run
```

- derive R0–R5 actions;
- prove preconditions;
- show rollback plan;
- no mutation.

### Phase 8 — R1 repairs — implemented

Enable deterministic Harr-owned file/config restoration with safety snapshots and rollback.

Must include raw-ELF-over-wrapper regression.

### Phase 9 — R2 runtime repairs — intentionally blocked in v1

Targeted managed component reinstall/prefetch only.

No broad “install everything” fallback.

### Phase 10 — R3 stale child refresh — intentionally blocked in v1

Safely refresh only stale proven Harr LeanCTX children.

### Phase 11 — skill integration

In the same release that exposes working repair:

- update `common/skills/harr/SKILL.md`;
- update generated Codex/OpenCode copies through normal Harr install/apply flow;
- document `doctor` vs `status`;
- explicitly gate `--repair` on user repair intent;
- add skill-policy regression test.

### Phase 12 — final hardening

- JSON schema stability;
- timeout/error injection;
- rollback tests;
- cross-platform behavior;
- docs;
- release smoke test from both package and local-source install.

## 23. Acceptance criteria

The feature is complete only when all of the following are true:

1. Reproducing the 2026-10-29 raw-ELF wrapper incident yields a clear FAIL at the launcher/injection layers.
2. `harr doctor --repair --dry-run` proposes only wrapper restoration and validated stale-child refresh for that incident.
3. Actual repair restores GitLab through the Harr gateway without touching the PAT.
4. Every selected MCP is handshaken and its full tool catalog validated.
5. Every declared safe probe is executed only in non-local mode.
6. A selected MCP with 0 tools is FAIL.
7. An external missing dependency is not “fixed” speculatively.
8. Shadow/direct registrations are detected but not removed automatically.
9. Secrets never appear in output, JSON, or repair logs.
10. Repair rollback is tested.
11. Repair is idempotent.
12. Plain `harr doctor` is mutation-free.
13. Harr skill permits proactive diagnosis but requires explicit user repair intent for `--repair`.
14. `harr status` remains fast and unchanged in purpose.
15. The installed provenance, not an arbitrary current checkout, is the source of truth for repair.

## 24. Current expected result on the observed machine

Based on the live diagnosis performed while designing this feature, after restoring the Harr wrapper the conceptual doctor result would be approximately:

```text
Core
  Harr installation ........ PASS
  LeanCTX Harr build ........ PASS
  LeanCTX launcher .......... PASS
  LeanCTX config ............ PASS
  fresh memento injection ... PASS
  stale LeanCTX processes ... PASS

MCP gateway
  codegraph ................. PASS
  gitlab .................... PASS  authenticated
  grafana ................... PASS
  kibana .................... PASS
  gigacode .................. FAIL  external CLI dependency missing
  jira ...................... PASS

Routing
  direct GitLab shadow ...... WARN  separate credential/config

Overall: FAIL because a selected MCP (GigaCode) is not healthy.
```

This current observation is not hard-coded expected behavior; it is an example of the diagnostic model.

## 25. Explicitly deferred

Not part of v1 unless separately designed:

- automatic credential replacement/rotation;
- removal of legacy direct MCP registrations;
- automatic installation of arbitrary external prerequisites;
- restarting entire GUI/IDE host processes;
- running write/destructive tools to prove health;
- repairing project-level configuration not owned by Harr;
- silently reconciling installed state to the current source checkout.

