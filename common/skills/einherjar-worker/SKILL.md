---
name: einherjar-worker
description: Delegate bounded code implementation, debugging, and test loops to any Harr Einherjar external CLI-agent backend while the parent remains planner.
---
<!-- harr-managed-skill-v1 -->

# Einherjar worker

Use Einherjar only after architecture, scope, invariants, forbidden changes, and acceptance criteria are fixed.

1. **Choose backend only when needed.** Normally omit `backend` and let Harr use `~/.config/harr/einherjar.json`. Use an explicit backend only when the user or task requires it.
2. **Delegate the whole bounded implementation loop.** Prefer `plan_path` for substantial work; use a direct prompt only for small self-contained tasks.
3. **Do not duplicate active work.** After `start` or `resume`, do not edit/read/revalidate the delegated scope in the parent while the session is RUNNING.
4. **Use compact supervision.** `status` is a one-shot snapshot; `wait` blocks inside the bridge; `messages` is only for an explicit progress request. Do not create model-side polling loops.
5. **Trust verified DONE handoffs.** Ask the same worker for missing proof rather than automatically repeating its full code review.
6. **Resolve ESCALATE in the planner.** Send only the new decision/evidence back with `resume`; Einherjar maps the Harr session to the backend's private vendor session.
7. **Session identity is Harr-owned.** Never ask for, store, or pass vendor session ids yourself.
8. **No external writes by default.** Worker commits/pushes/publishes only when the user's explicit task and execution contract require them.
9. **Backend failures are not design decisions.** Missing executable, malformed output, timeout, or permissions are FAILED/tool issues. Architecture contradictions are ESCALATE.

The stable adapter contract for adding new CLI backends is documented in `docs/EINHERJAR_BRIDGE_CONTRACT.md`.
