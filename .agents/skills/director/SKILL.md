---
name: director
description: >-
  Coordination protocol for working alongside other concurrent developer/agent sessions through
  the shared Director log. Use whenever you make a decision, defer a follow-up, hit a blocker,
  reach a handoff boundary, or need to leave context for a parallel/future session.
---

# Director coordination protocol

You coordinate with other sessions only through the shared, append-only LOG, written ONLY via the `director` CLI.

Your transient working state (what you decided, what you deferred, where you are) survives a compaction or a fresh start only if you wrote it to the LOG during a turn.

## 1. Continuous boundary-flush
Emit durable state to the LOG as you work—do not batch it for the end of the session:
- A decision (choice + rationale): `director emit --type decision --area <area> [--risk low|escalate] "message"`
- An open loop or deferred follow-up: `director emit --type open-item --area <area> [--risk low|escalate] "message"`
- A handoff at natural boundaries: `director emit --type handoff --area <area> "current task · next · hypotheses"`
- Closing a resolved item: `director resolve <ulid>` (use `director status` to find open ULIDs)

## 2. Treat injected/brief state as authoritative (Ground Truth)
At session start, run `director brief` to load the project's Charter, active decisions, recent handoffs, and open items.
Build on it; do not re-read the log or re-scan the repo.
