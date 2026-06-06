# AXON — Project Bible
**Version:** 1.1
**Created:** 14/05/2026
**Last Updated:** 15/05/2026
**Owner:** Tyson
**Maintained by:** Claude (documentation), Sol (ChatGPT), Tyson (decisions)

---

## What Is Axon?

Axon is a goal-driven AI system optimisation platform. It monitors devices deeply, interprets what the user wants to achieve, and determines the safest and most effective path to get there — explaining tradeoffs clearly, requiring user approval, and learning from outcomes over time.

This is not a system cleaner. It is not a rule-based optimiser. It is not a generic monitor.

Axon is a trusted, intelligent orchestration layer between the user and their device.

---

## The North Star — The Jarvis Principle

The product vision is best captured by one analogy: Jarvis from Iron Man.

Not Jarvis as a chatbot. Jarvis as a goal-directed intelligent system that understands the environment deeply, receives a high-level instruction from the user, and reconfigures everything it controls to achieve that goal — then reports back.

> "Jarvis, I need more power in the main weapon."
> "Understood. Diverting power from thrusters. You'll lose flight momentarily but you'll have full output for one decisive strike."

The user states what they want to **achieve**. Axon figures out the system-level changes to get them there, explains the tradeoffs, gets approval, executes, and monitors the outcome.

**This principle guides the architecture. It does not define the MVP.**

---

## Core Philosophy

**Optimise toward goals, not metrics.**

Most optimiser software targets: lower RAM, lower CPU, free storage.
Users actually care about: smoother gaming, longer battery, quieter fans, faster rendering.

The shift is:
> Goal → Strategy → Tradeoff → Action → Monitoring → Learning

Not:
> Problem → Recommendation

**Trust is the real product.**

Users are granting software permission to change settings, suspend processes, and alter system behaviour. Trust architecture matters as much as technical capability. Rollback, explainability, and simulation are not optional features — they are the foundation.

---

## Non-Negotiable Principles

These are anchor constraints. They do not change during feature debates without Tyson's explicit sign-off.

- **Trust before autonomy** — user approval required before any action; autonomy expands only as trust is earned over time
- **Explainability before optimisation aggression** — the user must always understand why a recommendation was made and what it will do
- **Simulation before execution** — users can always see what would change before anything changes
- **Rollback capability required for all MVP actions** — if an action cannot be reliably reversed, it is not permitted in MVP
- **Architecture must support future orchestration without forcing MVP scope expansion** — design for Jarvis; build the first step only

---

## The 5-Engine Architecture

Axon is built around five decoupled engines. This separation prevents the "everything talks to everything" failure mode common in AI-first products.

| Engine | Purpose |
|---|---|
| **Observation Engine** | Collects telemetry, usage patterns, hardware state, app behaviour |
| **Goal Engine** | Interprets user intent, priorities, and tradeoff preferences |
| **Decision Engine** | Determines what changes could help, expected outcomes, risk/confidence |
| **Action Engine** | Executes approved optimisations, manages rollback and monitoring |
| **Learning Engine** | Learns which optimisations worked, user preferences, accepted tradeoffs |

All engines are designed for the full Jarvis vision. Not all engines are fully implemented in MVP.

---

## What Makes Axon Different

- Learns **optimisation personality** — users optimise within personal tolerance bands, not toward a universal "maximum performance" goal
- **Hardware knowledge layer** — understands bottlenecks and can advise on upgrades, not just software settings
- **Explainability first** — every recommendation can be interrogated; the AI explains what it noticed, why it matters, expected benefit, risk level, and rollback option
- **Event-driven architecture** — stores events (goals created, actions executed, outcomes measured), not just state — enabling learning, debugging, auditability, and future enterprise scaling
- **Simulation Mode** — shows users what would change and the expected impact before any action is taken

---

## Optimisation Personality

Users are not identical. Axon learns each user's tolerance profile:

- Performance vs stability preference
- Noise tolerance
- Interruption tolerance
- Risk tolerance (conservative / moderate / aggressive)
- Visual quality tolerance
- Autonomy level preference

This profile is set during onboarding and refined by the Learning Engine over time based on approve/decline patterns. This is a core differentiator and potential moat.

---

## Long-Term Platform Vision

**Phase 1 — MVP:** Windows AI gaming and performance optimiser
**Phase 2 — Consumer platform:** Phones + PCs + tablets
**Phase 3 — Cross-device intelligence:** "Your phone video syncs are filling your gaming SSD"
**Phase 4 — Enterprise:** Predictive maintenance, fleet optimisation, AI-managed IT, energy efficiency

Enterprise is where significant commercial value exists long term.

---

## Internal Reference Names

- **Jarvis** — internal name for the goal-directed orchestration philosophy (NOT for external use; Marvel IP)
- **Axon** — the official product name

---

## Document Rules

- This document captures **vision, philosophy, and architecture principles only**
- Implementation detail does not belong here
- This document changes rarely — only when a fundamental decision shifts
- All changes require Tyson's sign-off

---
*v1.0 created 14/05/2026 | v1.1 — Added Non-Negotiable Principles section per Sol recommendation 15/05/2026*
*No changes in Session 3 (18/05/2026) or Session 4 (03/06/2026) — document remains current*
