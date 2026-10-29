# Historical GigaCode completion delivery

> Status: superseded by the named Ein UI shipped in Harr 0.2.9.
>
> This file records the earlier GigaCode-only experiment so the migration history
> remains understandable. It is not the current user-facing contract.

The old `harr-gigacode-app` prototype sent `ui/message` when an attached
Codex Desktop panel observed a GigaCode session become terminal. That direct app
and the public `gigacode::gigacode` route are retired.

The current implementation uses one shared read-only Codex Desktop app,
`harr-ein-ui`, for all named Ein instances. The model-visible entry point is
`show_ein_live`; callers provide an explicitly chosen instance id and an
existing Ein session UUID. The app never launches a worker. Poll/list helpers
remain app-only, session/history state is isolated per instance, and completion
delivery contains only bounded handoff information rather than raw CLI JSON.

Delegation itself still requires a direct user instruction and uses
`<instance-name>::ein`. A configured instance, including a sole instance, is
not authorization to start work automatically.

The original experiment's safety properties remain relevant:

- only an attached panel may deliver a terminal notification;
- completion claiming must be atomic so multiple panels do not duplicate it;
- reopening an already completed session must not create another notification;
- progress/transcript remains UI-only unless the caller explicitly requests
  normalized `messages`;
- host rejection or deferral of `ui/message` must not alter session state or
  cause the bridge to fabricate completion.
