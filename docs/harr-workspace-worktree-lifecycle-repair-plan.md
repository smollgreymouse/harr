# Harr / LeanCTX Workspace + Git worktree lifecycle repair plan

Status: **analysis / implementation plan, no runtime changes yet**  
Incident: 2026-10-29, OpenCode and Codex LeanCTX/ctx_tools startup failure after an intentionally deleted Codex worktree.  
Scope: Harr Workspace manager/control/App/Doctor + Harr LeanCTX fork Workspace store and Git checkout identity.

## 1. Incident and confirmed failure chain

The live `performance-dsp` Harr Workspace store contains an additional root for an intentionally deleted Codex worktree:

`/home/nmkartsev/.codex/worktrees/adsdsp-8452-protocol-transport-split/performance-dsp`

The persisted store itself is structurally valid. The directory is gone.

Current LeanCTX behavior:

1. `workspace_store::load()` parses the store.
2. `validate_value()` calls `validate_root()` for primary and every additional root.
3. `validate_root()` calls `Path::canonicalize()`.
4. A missing additional root returns ENOENT.
5. The entire Workspace store becomes unreadable.
6. Harr `ensure_workspace_store()` treats that as fatal.
7. LeanCTX exits before MCP initialize, so `ctx_tools` and every downstream gateway MCP disappear.

The failure reproduces directly with:

`lean-ctx workspace-admin show <store>`

returning:

`Workspace admin failed: No such file or directory (os error 2)`

This is a lifecycle bug, not accidental store corruption: deleting a Git worktree is a normal operation and must not revoke the availability of the parent Workspace.

## 2. Contract regression

The original Harr multi-root design already specified the correct behavior:

> A directory may become unavailable: report diagnostic status and exclude it from effective roots; do not silently delete the user's persisted configuration.

The implementation regressed from that contract by using one validation operation for two different concerns:

- persisted configuration validity;
- current filesystem authority/effectiveness.

Those must be separated.

## 3. Additional confirmed lifecycle defects

### 3.1 Missing additional root is impossible to remove through the public API

There are two independent blockers:

- Harr `workspace_command.resolve_target()` rejects `remove` unless the target is currently a directory.
- LeanCTX `workspace_store::mutate(..., add=false)` calls `validate_root(root)` before reading/removing it, so a missing root cannot be revoked.

Therefore the current state machine contains a dead-end:

`registered -> filesystem deleted -> store unreadable -> remove impossible`

Manual JSON editing is currently the only escape.

### 3.2 `harr workspace list` hides damaged/unavailable stores

`workspace list` catches `SystemExit` from `read_workspace_state()` and silently skips the entry.

Consequences:

- diagnostics lie by omission;
- orphaned worktree stores accumulate invisibly;
- Doctor sees no Workspace failure;
- a user cannot distinguish corrupt state from unavailable roots.

### 3.3 Workspace App has a "missing" UI status that can never be reached

`workspace_app.root_row()` already supports `status = "missing"`.

But `current_snapshot()` first executes `harr workspace show`, and current `show` fails before the App receives the missing root. Thus the intended degraded-state UI is unreachable.

### 3.4 Doctor does not validate persisted Workspace stores

Current Doctor proves launcher/binary/config/gateway/process health, but it does not enumerate and inspect all Harr Workspace stores. A fresh Doctor can return all PASS while a real project-specific LeanCTX launch fails before MCP initialize.

### 3.5 Persisted revision is not sufficient for filesystem-driven authority changes

Today request publication is fenced by Workspace `revision`.

If we correctly stop making a missing additional root fatal, disappearance/reappearance of a directory can change the effective authority without changing persisted revision.

Therefore a request could otherwise:

1. start with root X effective;
2. read/index X;
3. X disappears or changes identity;
4. persisted revision remains N;
5. old result is published under revision N.

The fix must introduce an **effective authority fingerprint/generation** in addition to persisted revision and re-check it at response publication.

The same fingerprint must scope/index caches that currently use only Workspace UUID + revision, otherwise a temporarily unavailable/replaced root can leave stale authorized corpus data under the same namespace.

### 3.6 Path-only identity resurrects stale configuration

Harr store filename is derived only from canonical primary path. Stored roots are path strings.

If a checkout is deleted and a different checkout later appears at the same path, the old Workspace UUID/configuration can be reused.

For generic user-configured directories this may be intentional path-binding behavior. For Git worktrees it is unsafe/incorrect because checkout identity exists independently of path.

### 3.7 `git worktree move` is not represented by Workspace state

The current Workspace store knows only the old path, so a moved worktree becomes "missing".

LeanCTX already has `core::git_checkout` with a stable `checkout_key` specifically designed to survive `git worktree move`, but Workspace does not use it.

### 3.8 Worktree topology and multi-root authority are currently conflated

Current Harr `workspace_sync` can persist host/session working folders as `additional` roots.

That means a sibling worktree of the **same Git repository** may become an independent additional Workspace authority.

This violates the intended model:

**Git worktree != independent Workspace additional root.**

A worktree is another checkout of a repository slot. Discovering/listing it is topology metadata and must not itself grant read/search authority. LeanCTX's `git_checkout.rs` explicitly states this invariant.

Independent repositories/directories remain valid multi-root additions.

## 4. Existing LeanCTX foundation we should reuse

The currently shipped Harr LeanCTX lineage includes commit `75d3c6500 feat: add Git worktree identity foundation`.

It already provides:

- `RepositoryIdentity.repository_key`;
- optional portable repository identity;
- `CheckoutIdentity.checkout_key`;
- `CheckoutKind::{Main, Linked}`;
- stable checkout identity across detach;
- stable checkout identity across `git worktree move`;
- `list_worktrees()` metadata including:
  - current root,
  - git dir,
  - branch/head,
  - `locked`,
  - `prunable`,
  - `exists`;
- protection against treating a foreign checkout recreated at an old path as the old worktree;
- the explicit rule that sibling discovery is metadata only and never authority.

Do not duplicate this logic in Harr with ad-hoc path-name heuristics such as `.codex/worktrees`.

## 5. Target model: configured state != effective authority

### 5.1 Persisted configuration

Persisted Workspace state must remain readable when an additional root is unavailable.

Conceptually:

```
ConfiguredWorkspace {
  id,
  revision,
  primary,
  additional[]
}
```

A missing path is not structural corruption.

Structural/file-security errors remain fatal:

- malformed JSON/schema;
- bad UUID/revision;
- duplicate/unsorted configured entries where schema requires otherwise;
- relative/broad/unsafe lexical paths;
- wrong owner/mode;
- store or parent symlink violations;
- state stored inside one of its configured roots.

### 5.2 Runtime resolution

Every request derives an immutable runtime snapshot:

```
ResolvedWorkspace {
  workspace_id,
  persisted_revision,
  authority_fingerprint,
  primary,
  effective_additional[],
  root_status[]
}
```

Each configured root receives a status, e.g.:

- `active`
- `missing`
- `unavailable`
- `identity_mismatch`
- `unsafe`
- `moved` (when a stable Git checkout identity resolves at a new path)
- `prunable_worktree`
- `locked_unavailable_worktree`

Only `active` roots become authority.

### 5.3 Primary semantics

Primary is special.

- Missing/unavailable **additional** root: Workspace remains usable; root is excluded from authority.
- Missing/unavailable **primary** root: no file/search authority can be constructed. The MCP process/diagnostic surface should remain alive when possible and report `primary_unavailable`; it must not silently switch to another checkout/root.
- Primary remains immutable through ordinary add/remove.
- Explicit future checkout/worktree switching is a distinct operation, not `add_root`.

### 5.4 No silent persisted deletion on ordinary load

A temporarily unmounted directory must not be erased because one request observed ENOENT.

Normal resolution is read-only.

Explicit cleanup is allowed through:

- user-requested `workspace remove PATH`;
- a separately specified Doctor repair only when its safety proof is strong enough;
- future worktree lifecycle reconciliation with recorded checkout identity.

## 6. P0 — immediate correctness fix

P0 restores the original multi-root contract and prevents another MCP outage.

### 6.1 LeanCTX: split store parsing from authority resolution

Refactor `workspace_store.rs` into distinct responsibilities.

Suggested internal API:

- `load_config(path) -> ConfiguredWorkspace`
  - validates protected state file and structural/path invariants;
  - does **not** require additional roots to exist.

- `resolve_authority(path/config) -> ResolvedWorkspace`
  - primary must resolve safely;
  - each additional root is independently resolved;
  - missing/unavailable additions are omitted from effective authority and reported.

Do not make a permissive `load()` and then keep existing callers that blindly convert `additional` strings into authority.

Update all security-sensitive callers explicitly:

- MCP startup;
- request snapshot construction;
- `ctx_workspace_get/list/diagnose`;
- publication fence;
- index namespace/authority key;
- admin mutation.

### 6.2 LeanCTX: allow exact removal of a missing configured root

Add and remove need different validation.

`add`:
- target must exist;
- canonicalize;
- safe-root checks;
- store canonical binding;
- CAS revision.

`remove`:
- read protected configured state first;
- locate an existing configured entry;
- if supplied target exists, canonicalize and match;
- if supplied target is missing, accept only a normalized absolute lexical path that exactly matches a stored configured path;
- never allow removal of primary;
- CAS revision and atomic save.

This lets a stale worktree path be revoked after `git worktree remove`.

### 6.3 Harr CLI: stop requiring directory existence for remove

Split `resolve_target()` semantics:

- add/sync: existing directory required;
- remove: normalized absolute path; existing paths canonicalized; missing paths allowed only for exact configured match performed by LeanCTX.

### 6.4 Harr list/show: expose degraded stores

`workspace show` should expose configured roots and statuses.

`workspace list` must not silently drop an unavailable Workspace.

Corrupt/protected-file failures should appear explicitly as an error/status row rather than vanishing.

### 6.5 Workspace App: make missing status real

The App should render configured roots even when inactive.

For a missing additional root:
- keep row visible;
- show `missing` / worktree-specific status;
- allow explicit removal using current revision.

### 6.6 Effective authority fingerprint

Calculate a deterministic fingerprint from at least:

- Workspace UUID;
- persisted revision;
- resolved primary binding;
- ordered effective additional bindings;
- for Git-backed bindings, checkout/repository identity where available.

At request start capture both:
- persisted revision;
- authority fingerprint.

Before publishing:
- re-resolve;
- reject if either revision or fingerprint changed.

Use the same authority fingerprint (or a digest incorporating it) for security-sensitive search/index cache namespaces.

This preserves revocation semantics for filesystem/worktree lifecycle changes that do not write the store.

## 7. P1 — restore proper Git worktree lifecycle semantics

P0 makes stale roots safe. P1 prevents the bad state from being created in the first place.

### 7.1 Enforce: same-repository worktree is not an additional root

At the authority boundary, when adding/syncing a candidate:

1. discover Git identity for primary;
2. discover Git identity for candidate;
3. if both are checkouts of the same local repository but different checkout slots:
   - do not add candidate as `additional`;
   - return a typed skip/rejection such as `same_repository_worktree`;
   - do not grant sibling-worktree search authority.

This must be enforced in LeanCTX, not only in the Harr skill.

Harr `workspace_sync` should report the skip reason clearly.

Separate independent clones of the same remote remain independent local repositories and may be explicit multi-root additions.

### 7.2 Add checkout identity metadata for Git-backed root bindings

Evolve the persisted root schema (schema version/migration required) so Git-backed roots can carry identity, not only a path:

```
RootBinding {
  configured_path,
  kind: path | git_checkout,
  repository_key?,
  checkout_key?,
  portable_identity?
}
```

Do not use portable remote identity as local authority: separate clones of the same remote are distinct local repositories.

### 7.3 Worktree move

If a configured Git checkout binding has the same `checkout_key` at a new path:

- report it as moved;
- update the effective path immediately;
- only persist the new configured path through an explicit reconciliation transaction/CAS;
- never add the old and new paths simultaneously.

The existing `checkout_key` contract already supports this.

### 7.4 Worktree remove/prune

For a registered worktree checkout:

- `git worktree remove` -> checkout becomes inactive; Workspace continues.
- stale Git admin record marked prunable -> diagnostic `prunable_worktree`.
- `git worktree prune` -> identity may become unrecoverable from Git metadata; stored binding remains inactive until explicit cleanup.
- locked/missing worktree -> do not auto-delete; this may be removable/offline storage.

### 7.5 Recreated path

A Git checkout root reappearing at the same filesystem path with a different `checkout_key` must **not** silently regain the old worktree authority.

Return `identity_mismatch` and require explicit re-authorization/rebinding.

Generic `kind=path` roots can retain path-binding semantics.

### 7.6 Active worktree / primary checkout switching

Do not solve checkout switching by adding the sibling worktree as an additional root.

Introduce a separate trusted operation/binding for changing the active checkout of a Git-backed logical root.

Properties:

- preserve logical Workspace identity;
- bind to a specific `checkout_key`;
- old checkout is not simultaneously readable merely because it is a sibling;
- no fallback from deleted active worktree to main checkout without explicit action;
- a moved active worktree can be followed by stable checkout identity;
- independent additional repositories remain unchanged.

Exact command/API naming can be decided during implementation, e.g. `workspace checkout use` / `workspace checkout status`; do not expose sibling discovery as authority.

## 8. Primary worktree lifecycle

A linked worktree can itself be the project from which Codex/OpenCode launches.

Required behavior:

### Live session, worktree later deleted

- MCP process must not crash merely because the primary checkout disappears.
- Subsequent file/search calls fail closed with a structured `primary_unavailable`.
- Workspace diagnostic/control surfaces remain available.
- Never silently fall back to main checkout, because that could redirect edits/reads to the wrong branch.

### Restart after worktree deletion

A host cannot reliably launch from a deleted cwd. Harr should produce a clear launcher diagnostic rather than a generic traceback/ENOENT where possible.

### Orphaned per-worktree stores

Existing path-keyed stores for deleted primary worktrees should be visible to `workspace list`/Doctor as orphaned, not silently hidden.

A later cleanup/forget operation may remove them explicitly; ordinary background startup must not delete them.

## 9. Harr Doctor additions

Add a Workspace diagnostic layer.

Checks:

- enumerate every Harr-owned Workspace store;
- protected file/schema health;
- primary status;
- configured additional count;
- effective additional count;
- missing/unavailable roots;
- Git identity mismatch/moved/prunable/locked status when known;
- orphaned primary stores;
- stale legacy path-only entries;
- active live LeanCTX process -> bound store -> effective authority validation.

Classification:

- missing additional root: WARN, not global FAIL;
- missing primary of an inactive/orphan store: WARN;
- live/current workspace primary unavailable: FAIL;
- malformed/security-invalid store: FAIL for that store;
- same-repository sibling worktree persisted as additional: WARN migration/reconciliation required.

Doctor must not hide unreadable stores.

Repair policy:

- P0 does **not** require Doctor to delete missing roots. Once LeanCTX tolerates them, availability is restored without destructive mutation.
- `--repair` may later migrate schema/reconcile a proven moved checkout with snapshot + rollback + CAS.
- Do not auto-delete a merely missing generic root.
- Explicit `harr workspace remove <missing-path>` remains the deterministic user cleanup path.

## 10. LeanCTX test plan — mandatory

Add these tests to the LeanCTX fork, not only Harr wrappers.

### L1. Missing additional root does not invalidate store

1. create primary + additional;
2. create store;
3. add additional;
4. remove additional directory from filesystem without mutating store;
5. inspect/load configured state succeeds;
6. resolved authority contains primary only;
7. status reports missing additional;
8. MCP initialize succeeds;
9. `ctx_workspace_get/diagnose` reports degraded root;
10. `ctx_read/tree/search` on the missing root is denied.

This is the direct regression for the 2026-10-29 incident.

### L2. Remove missing additional root

After L1:
- `workspace-admin remove STORE <missing-path> REV` succeeds;
- revision increments exactly once;
- configured additional disappears;
- stale CAS still loses;
- restart persists clean state.

### L3. Missing additional during an already-running MCP session

1. launch MCP with active additional root;
2. confirm search/read succeeds;
3. delete root externally;
4. without restart, next Workspace diagnostic shows inactive/missing;
5. access is denied;
6. primary operations still succeed.

### L4. In-flight deletion publication fence

Use deterministic debug barrier:

1. request reads/searches additional root;
2. pause after authority/read and before publication;
3. delete root externally without changing persisted revision;
4. release;
5. result must not publish;
6. authority fingerprint mismatch is observed.

This specifically proves that persisted revision alone is no longer the only revocation fence.

### L5. Cache/index isolation across availability change

1. warm BM25/dense/ANN state with additional active;
2. make root unavailable without revision mutation;
3. query from Workspace scope;
4. no result/path/count/content from inactive root may surface;
5. authority fingerprint/cache namespace changes;
6. restore root and verify intentional reactivation semantics.

### L6. Same-repository sibling worktree cannot be additional authority

Create a real Git repo + linked worktree.

- adding linked sibling as an additional root is rejected/skipped as `same_repository_worktree`;
- independent second repo is accepted;
- separate clone of same remote is not mistaken for the same local repository.

### L7. Worktree remove

With recorded worktree identity:

- create linked worktree;
- bind/register according to new model;
- `git worktree remove`;
- Workspace remains usable;
- removed worktree becomes inactive;
- sibling discovery does not grant it;
- explicit cleanup works.

### L8. Worktree prune

- create worktree;
- make it stale/prunable;
- verify diagnostic status;
- run `git worktree prune`;
- no crash;
- no authority resurrection;
- explicit cleanup remains possible.

### L9. Worktree move

- bind checkout;
- `git worktree move old new`;
- stable `checkout_key` resolves new path;
- old path is not authority;
- no duplicate root;
- reconciliation CAS behaves deterministically.

### L10. Recreate old worktree path with foreign checkout

- remove/move original linked checkout;
- create another checkout/repository at the old path;
- old binding must not authorize the foreign checkout;
- report `identity_mismatch`.

This should reuse the adversarial cases already present in `git_checkout.rs`.

### L11. Locked/offline worktree

- lock a linked worktree;
- simulate unavailable path;
- do not delete persisted binding;
- exclude from authority;
- report locked/unavailable state.

### L12. Primary linked worktree disappears in live MCP

- launch with linked worktree as primary;
- remove it after initialization;
- MCP stays alive;
- Workspace diagnostics remain callable;
- content tools fail closed with `primary_unavailable`;
- no fallback to main checkout.

### L13. Primary path recreation / identity resurrection

- create Git-backed primary and store;
- remove checkout;
- create a different checkout at same path;
- prove old Workspace authority is not silently rebound when Git identity metadata is available.

### L14. Concurrent clients and filesystem lifecycle

Two live MCP processes share one store:

- both observe the same initial authority fingerprint;
- external root deletion changes both effective snapshots;
- no persisted revision race is required;
- both deny stale authority;
- later explicit remove uses CAS with a single winner.

### L15. Existing security suite remains green

Re-run:

- store CAS/churn/ABA;
- mid-request persisted revocation;
- same-primary authority isolation;
- dense namespace isolation;
- ANN contamination tests;
- long-lived MCP isolation;
- multi-UID;
- symlink/rename store attacks;
- interrupted writer recovery.

The lifecycle fix must not weaken fail-closed store security.

## 11. Harr test plan

### H1. CLI stale-root lifecycle

Extend `tests/workspace-cli.sh`:

- add root;
- delete directory;
- show succeeds with missing status;
- list includes Workspace;
- remove missing path succeeds;
- revision/CAS correct.

### H2. Manager startup regression

Extend `tests/workspace-manager.py` / real LeanCTX variant:

- pre-create store with one missing additional;
- `exec-leanctx ... mcp` still initializes;
- manager does not recreate/overwrite the store.

### H3. Live OpenCode/Codex-equivalent regression

Extend `workspace-live-update.py`:

- active root works;
- external deletion without Harr mutation;
- same MCP stays alive;
- primary still works;
- missing root denied;
- explicit stale removal updates revision.

### H4. Real Codex acceptance

Extend `workspace-codex-acceptance.py` with an external filesystem deletion stage, not only clean Harr `remove`.

The exact incident must be represented:
- worktree-like additional directory deleted first;
- Codex keeps `lean-ctx` / `ctx_tools` alive;
- Workspace inspection reports inactive root;
- cleanup succeeds afterwards.

### H5. Workspace Control MCP

- `workspace_get` works with unavailable additions;
- sync does not re-add same-repository sibling worktrees;
- skip reason is visible.

### H6. Workspace App

- missing root row renders;
- remove button works for missing root;
- revision conflicts still handled;
- no fake "OK" after failed mutation.

### H7. Doctor

Fixtures:
- healthy store;
- missing additional;
- missing primary;
- malformed store;
- same-repository-worktree legacy additional;
- moved/mismatched Git checkout.

Assert no store is silently omitted.

## 12. Migration strategy

Do not combine schema migration and incident recovery in one opaque step.

### Stage A: backward-compatible P0

Keep current persisted JSON readable.

- parse existing `primary/additional`;
- tolerate unavailable additional roots;
- add diagnostic output fields without rewriting store automatically;
- make remove of missing exact path possible.

This immediately fixes current production behavior.

### Stage B: v2 root identity metadata

Introduce versioned root bindings for Git-aware lifecycle.

Migration rules:

- existing live paths can be classified and enriched explicitly/safely;
- missing legacy roots cannot be guessed to be Git worktrees from their pathname;
- keep them as legacy path bindings/inactive until user cleanup or future proof;
- never use `.codex/worktrees` naming as security identity.

## 13. Implementation order

1. **LeanCTX P0 store split**: configured parse vs effective authority.
2. **LeanCTX missing-root tests L1-L5** before touching Harr.
3. **LeanCTX remove-missing semantics** + CAS tests.
4. **Authority fingerprint + cache/publication fencing**.
5. **Harr CLI/show/list/App/control compatibility**.
6. **Harr incident regression tests H1-H4**.
7. **Doctor Workspace diagnostics**.
8. Release/install new Harr LeanCTX build and verify both Codex and OpenCode on the real `performance-dsp` store.
9. **P1 same-repository worktree rejection** using `git_checkout`.
10. **v2 Git checkout binding** and worktree move/remove/prune/recreate tests.
11. Add explicit active-checkout switching; do not emulate it with `additional roots`.

## 14. Acceptance invariants

The fix is complete only when all of these hold:

1. Deleting one additional worktree can never prevent LeanCTX MCP initialize for the primary Workspace.
2. A missing additional root is never authority.
3. A missing additional root remains visible/diagnosable until explicitly cleaned or safely reconciled.
4. A missing root can be explicitly removed after it is gone.
5. Missing/unavailable filesystem state cannot bypass the response publication fence.
6. Cached/indexed data from an inactive root cannot surface after lifecycle change.
7. A sibling worktree of the same repository is not automatically an independent additional root.
8. Worktree discovery/topology never grants authority.
9. A moved worktree can be recognized by stable checkout identity.
10. Reusing an old worktree path for another checkout does not resurrect old Git checkout authority.
11. Missing primary does not redirect authority to another checkout.
12. `workspace list`, App and Doctor never hide a stale/orphaned Workspace by silently skipping it.
13. Existing CAS, ownership, symlink, atomic-write, revocation and multi-client isolation guarantees remain intact.

## 15. Related live observation: downstream direct calls work while discovery is degraded

On the same live Harr installation, GitLab MCP is operational enough to execute a direct qualified call successfully: MR `!2151` was read through Harr.

At the same time, discovery remains broken/degraded in `find/refresh`.

This is important diagnostic separation:

- downstream runtime/authentication is **not globally broken**;
- Harr -> LeanCTX gateway -> GitLab execution path can succeed;
- the remaining GitLab symptom belongs to the discovery/catalog layer (refresh/index/catalog visibility/ranking/state), not necessarily credential injection or MCP process availability;
- do not use discovery failure alone as evidence that a downstream MCP is unavailable;
- direct qualified calls should remain an acceptance probe when the exact downstream tool name is known.

The Workspace/worktree lifecycle incident is separate: when LeanCTX itself fails before MCP initialization because a Workspace store is unreadable, neither discovery nor direct downstream calls can exist for that client session.

Doctor and regression tests should therefore distinguish at least:

1. LeanCTX MCP startup/handshake;
2. gateway downstream registration/handshake;
3. discovery catalog refresh/find;
4. direct qualified downstream tool invocation.

A failure in (3) with (4) passing must be reported as a discovery-layer defect, not a runtime/authentication outage.

## 16. Current-system recovery note

Do not encode the current machine's stale path as a product-specific exception.

After P0 is implemented, the existing `performance-dsp` store should become readable without deleting its configured stale entry; LeanCTX should start with that entry inactive. The user can then explicitly remove the obsolete root through the normal Workspace API.

Until P0 is installed, the current store remains capable of preventing LeanCTX startup in clients bound to `performance-dsp`.
