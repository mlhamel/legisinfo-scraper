<!-- START DIRECTOR RULES (DO NOT EDIT) -->
## Director Coordination Protocol

You are working in a project coordinated by Director. At start, you must rehydrate your context by reading current state. Throughout the session, you must continuously flush decisions and open items to the shared event log.

### Session Initialization
At the very start of your work:
1. Run `director brief` to load the project's Charter, active decisions, recent handoffs, and open items.
2. Run `director status` to see active session liveness and the Needs-you band.
3. If this is a new session, run `director status` (or `director _hook sessionstart`) to register the session in the fleet.

### Continuous logging
Always emit state as you work—do not wait until the session ends:
- A decision (choice + rationale): `director emit --type decision --area <subsystem> [--risk low|escalate] "message"`
- An open loop or deferred follow-up: `director emit --type open-item --area <subsystem> [--risk low|escalate] "message"`
- A handoff at natural boundaries: `director emit --type handoff --area <subsystem> "current task · next · hypotheses"`
- Closing a resolved item: `director resolve <ulid>` (use `director status` or `director brief` to find open ULIDs)

### Session wrap-up
- Suggest running `director handoff` (or run it) when pausing work.
- Suggest running `director complete` when the branch/workstream is finished and merged.

See the `director` skill or run `director help` for details.
<!-- END DIRECTOR RULES -->
