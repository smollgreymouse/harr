# Experimental Codex Desktop completion delivery

The existing GigaCode MCP App can send `ui/message` (role `user`) when its live
panel observes a running session become terminal. The message contains only the
session UUID and terminal status; Sol is asked to fetch `gigacode::gigacode`
`status` exactly once for structured evidence. Progress/transcript remains
UI-only. This is not a new assistant message and may initiate a Codex turn.

## Scope and safeguards

- Only an attached, open panel that observed an initially nonterminal session
  sends a completion message. Closed panels do **not** deliver notifications.
- Only one panel may claim a given session completion. The claim is persisted
  per user in `~/.local/state/harr/gigacode-app/delivered-completions` and claimed
  atomically across server instances. It is released if `ui/message` fails.
- A reopened already-completed session does not trigger a new message.
- The feature relies on the host allowing `ui/message`; the CLI has no MCP App
  delivery support. There is not yet an end-to-end Codex Desktop acceptance test.
- The host may defer or reject sending a message, or may start a new assistant
  turn while the user is conversing. Therefore this should be reviewed and
  tested in an isolated Codex Desktop chat before rollout.
