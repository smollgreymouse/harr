# Harr Doctor — deferred repair work

Status: deferred after Harr 0.3.0.

Harr 0.3.0 deliberately ships Doctor with read-only end-to-end diagnosis and deterministic R1 repair only. The two broader repair classes below remain fail-closed as `BLOCKED`; this is intentional safety behavior, not an unfinished hidden fallback.

## R2 — targeted managed runtime repair

Current state: **BLOCKED**.

Doctor can diagnose a missing or mismatched selected MCP runtime, but it must not repair that failure by calling the broad `harr install mcp` path because that can reinstall or prefetch unrelated selected runtimes.

R2 may be enabled only after Harr has a per-server repair primitive with these properties:

- selects exactly one Harr-managed MCP/runtime by canonical registry name;
- validates that the runtime is Harr-owned and repairable according to registry metadata;
- never changes credentials;
- never changes MCP selection;
- never installs unrelated runtimes;
- records the exact action in Doctor evidence;
- re-runs only the affected runtime/catalog/gateway checks after repair;
- has Linux, macOS and Windows regression coverage.

Likely command surface:

```text
harr install mcp NAME
```

Doctor should call that narrow primitive rather than duplicate package-manager logic.

## R3 — stale Harr LeanCTX child refresh

Current state: **BLOCKED**.

Doctor can detect stale/wrong-generation LeanCTX processes and can distinguish candidates that appear under supported Codex/OpenCode hosts. Harr 0.3.0 does **not** terminate them automatically.

R3 may be enabled only when Harr can prove all of the following before mutation:

1. the process is a LeanCTX child launched through Harr, not a user-owned/direct LeanCTX;
2. the process belongs to a supported host route managed by Harr;
3. the executable is deleted or belongs to the wrong installed Harr generation;
4. the current PID/process identity is revalidated immediately before termination;
5. terminating the child does not terminate the host application;
6. the host is expected to respawn the managed child;
7. Doctor observes a replacement process using the expected Harr generation;
8. the replacement completes a fresh LeanCTX/gateway handshake;
9. if respawn/verification fails, Doctor reports the failure explicitly rather than pretending that “no live process” is healthy.

Linux ownership evidence should remain conservative and must never print environment values. Equivalent macOS/Windows support can return `SKIP` until ownership and respawn can be proven safely on those platforms.

## Non-goals

These remain forbidden for both R2 and R3:

- credential rotation/copying;
- removing user-owned shadow MCP registrations automatically;
- killing Codex/OpenCode itself;
- broad “repair everything” fallbacks;
- replacing Harr with an upstream LeanCTX installer;
- retrying speculative alternative mutations after a `BLOCKED` or `ROLLED_BACK` result.

## Release policy

R2/R3 can land independently in later 0.3.x releases once their safety contracts and regression tests are complete. They do not block Harr 0.3.0.
