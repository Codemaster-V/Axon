# AXON — Decisions Log
**Created:** 14/05/2026
**Last Updated:** 03/06/2026
**Maintained by:** Claude

> This log records every significant decision made during the Axon project — what was decided, who proposed it, who agreed, and crucially **why**. The reasoning matters as much as the conclusion. Entries are never deleted or modified after the session they were made in closes.

> **Supersedes field:** Where a later decision replaces or refines an earlier one, this is noted explicitly to avoid contradictions.

---

## DEC-001 | Platform: Windows First, Not iOS
**Date:** 14/05/2026
**Proposed by:** Sol
**Agreed by:** Claude, Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** Build the MVP on Windows, not iOS.

**Reasoning:** Apple's sandboxing heavily restricts background monitoring, system-level access, automated optimisation, and performance controls. An iOS-first approach would produce an "AI productivity suggestions" app rather than a genuine AI optimisation platform. Windows provides the system access, telemetry, and permissions the core product vision requires.

---

## DEC-002 | MVP Positioning: Gaming and Performance
**Date:** 14/05/2026
**Proposed by:** Sol
**Agreed by:** Claude, Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** The MVP is positioned as a Windows AI gaming and performance optimiser, not a general-purpose system cleaner or broad AI assistant.

**Reasoning:** Gamers care deeply about performance, results are measurable (FPS, thermals, boot time), the audience tolerates beta products if they deliver real gains, and the use case produces impressive demos. This is the most defensible and testable entry point.

---

## DEC-003 | The Jarvis Principle as Architectural North Star
**Date:** 14/05/2026
**Proposed by:** Claude (introduced to Sol by Tyson)
**Agreed by:** Sol, Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** The Jarvis framing — goal-directed intelligent orchestration — guides the architecture from day one. It does NOT define the MVP identity or feature set.

**Reasoning:** The distinction between "recommendation engine" and "goal-directed agent" changes how the instruction layer, permission model, learning system, and hardware knowledge layer must be designed. Building the foundations without this in mind would require painful refactoring later. However, letting Jarvis define the MVP risks producing an impossible first product. The principle: Jarvis guides architecture; the MVP constrains what gets built first.

---

## DEC-004 | Five-Engine Architecture
**Date:** 14/05/2026
**Proposed by:** Sol
**Agreed by:** Claude, Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** Axon is built around five decoupled engines: Observation, Goal, Decision, Action, Learning.

**Reasoning:** Separating concerns cleanly prevents the "everything talks to everything" failure mode common in AI-first products. Each engine can evolve independently. The decoupling also makes debugging, testing, and rollback significantly more manageable. This maps cleanly onto the Jarvis architecture while keeping MVP implementation bounded.

---

## DEC-005 | Event-Driven Architecture
**Date:** 14/05/2026
**Proposed by:** Sol, endorsed by Claude
**Agreed by:** Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** The system stores events (goals created, recommendations generated, actions approved/executed, outcomes measured, rollbacks triggered, preferences updated) rather than just current state.

**Reasoning:** Event history enables explainability, auditability, learning, debugging, enterprise scaling, and multi-device orchestration. State-only storage would require painful retrofitting later. The event log effectively becomes the system's memory and is critical for the Learning Engine.

---

## DEC-006 | Local-First SQLite Storage for MVP
**Date:** 14/05/2026
**Proposed by:** Claude, confirmed by Sol
**Agreed by:** Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** MVP uses local SQLite storage. Cloud sync remains optional and out of scope for MVP.

**Reasoning:** Local-first supports user trust, simplifies debugging, enables offline functionality, and maximises MVP development velocity. Cloud should remain optional for a long time.

---

## DEC-007 | Simulation Mode as Core MVP Feature
**Date:** 14/05/2026
**Proposed by:** Sol, endorsed by Claude
**Agreed by:** Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** Simulation Mode — "Here's what I would change and the expected impact" — is a core MVP feature, not a nice-to-have.

**Reasoning:** Users can safely understand the optimiser before granting execution permissions. One of the strongest trust-building mechanisms available. Also aids development and debugging.

---

## DEC-008 | User Approval Required for All Actions in MVP
**Date:** 14/05/2026
**Proposed by:** Sol and Claude (agreed independently)
**Agreed by:** Tyson
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** Every action in the MVP requires explicit user approval. No autonomous execution in V1.

**Reasoning:** Trust must be established before autonomy is granted. Autonomous execution before trust is built risks killing the product. Autonomy levels can expand as the Learning Engine matures and user confidence grows.

---

## DEC-009 | Schema V0.2 Entities and Changes
**Date:** 15/05/2026
**Proposed by:** Claude (V0.1), amended by Sol (V0.2 additions)
**Agreed by:** Claude, Sol
**Status:** ✅ Confirmed
**Supersedes:** Schema V0.1

**Decision:** Accept three additions into schema V0.2:
1. capability_registry entity
2. Split recommendation confidence into confidence_of_effectiveness and confidence_of_safety
3. Add environmental_context block to outcome_record

Defer explanation_record to post-MVP.

**Reasoning:** capability_registry formalises what actions are possible before recommendations are generated, supporting future enterprise policy restrictions and plugin architecture. Split confidence reflects that "will this help" and "is this safe" are different signals. Environmental context on outcomes prevents the Learning Engine from drawing wrong conclusions across different usage contexts.

---

## DEC-010 | MVP Safe Action Boundary
**Date:** 15/05/2026
**Proposed by:** Sol
**Agreed by:** Claude, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 15/05/2026
**Supersedes:** N/A

**Decision:** Formally constrain action categories permitted in MVP.

**Allowed:** Startup app toggles, process suspension, power profile changes, temporary optimisation states, cache cleanup, storage cleanup recommendations.

**Explicitly disallowed:** Registry modification, driver modification, BIOS/firmware interaction, overclocking, undervolting, permanent OS configuration changes, security policy changes.

**Reasoning:** Creates a hard operational safety boundary. Dramatically simplifies rollback reliability, testing, trust, debugging, and legal risk. Expanding later is easy; recovering from broken trust is not.

---

## DEC-011 | Rollback Scope Definition
**Date:** 15/05/2026
**Proposed by:** Sol
**Agreed by:** Claude, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 15/05/2026
**Supersedes:** N/A

**Decision:** MVP rollback means reverting app-controlled changes only — NOT full system state restoration.

**Reasoning:** "Rollback from snapshot" could imply full system restore point capability. MVP rollback is scoped to actions Axon itself took. This distinction is critical for managing user expectations. Overpromising on rollback scope risks damaging trust irreparably.

---

## DEC-012 | App Name: Axon
**Date:** 15/05/2026
**Proposed by:** Claude (Axon), Tyson (North Star as alternative)
**Agreed by:** Sol, Claude, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 15/05/2026
**Supersedes:** N/A

**Decision:** The product is named Axon.

**Reasoning:** Axon (signal-transmitting part of a neuron) maps onto signal transmission, orchestration, learning systems, and distributed intelligence. Sounds like real infrastructure software. Scales to enterprise. No IP issues. Jarvis/Vision/Mind Stone/Infinity Stone remain internal references only due to Marvel IP risk.

---

## DEC-013 | Five-Document System + Daily Journal
**Date:** 15/05/2026
**Proposed by:** Claude (four documents), Sol (added Document 4)
**Agreed by:** Sol, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 15/05/2026
**Supersedes:** N/A

**Decision:** The project maintains five documents:
1. Project Bible — vision and philosophy (rarely changes)
2. Current State — operational snapshot updated every session
3. Decisions Log — this document; chronological with reasoning
4. Architectural Risks & Assumptions — risks, uncertainties, assumptions
5. Journal — dated session entries as archive fallback

Claude produces updated versions of all five documents at the end of every session. Claude flags Tyson when a conversation is approaching its limit. An introductory context paragraph is also produced at session end for pasting into new conversations.

**Reasoning:** Context windows have limits. Without external memory, continuity breaks every conversation reset. Five documents give Tyson a portable project brain that can be dropped into any new conversation with Claude or Sol to restore full context immediately.

---

## DEC-014 | Parallel Independent Coding Approach
**Date:** 14/05/2026
**Proposed by:** Tyson
**Agreed by:** Claude, Sol
**Status:** ✅ Confirmed
**Supersedes:** N/A

**Decision:** Claude and Sol develop code independently in parallel. Both implementations are reviewed together and Tyson makes the final call on which approach or combination to use.

**Reasoning:** Two independent implementations surface different approaches and potential issues. Reviewing both before adopting either reduces the risk of architectural mistakes going undetected.

---

## DEC-015 | MVP Stack: Python First
**Date:** 18/05/2026
**Proposed by:** Sol (recommended), Claude (agreed)
**Agreed by:** Claude, Sol, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 18/05/2026
**Supersedes:** N/A

**Decision:** Axon MVP will be implemented in Python. C# remains a possible future production/native Windows pathway once the MVP is validated.

**Stack:** Python 3.12, SQLite, psutil, WMI/pywin32 for Windows-specific access, PyInstaller for packaging.

**Architecture discipline:** Code architected cleanly so a C# Windows shell can wrap it or the app can be rewritten later without rebuilding the core behaviour logic.

**Reasoning:** Axon's immediate priority is proving the system can observe, record events, store snapshots, and support safe recommendation/rollback logic. Python provides the fastest path: strongest monitoring ecosystem (psutil), SQLite already included, readable code for AI-assisted development, faster iteration. C# would slow MVP development before the core product is proven.

---

## DEC-016 | Axon Project Folder Structure
**Date:** 18/05/2026
**Proposed by:** Claude (initial), Sol (major revision), Claude (tyson_decisions subfolder addition)
**Agreed by:** Claude, Sol, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 18/05/2026
**Supersedes:** Claude's initial simple folder proposal

**Decision:** Axon uses a Python-first project structure based on src/axon/, with engines separated according to the five-engine architecture. Active Python files use stable importable filenames. Dated author/version filenames used only for review packets, archived outputs, and superseded versions.

**Key elements:**
- `src/axon/engines/` — five engine subfolders
- `src/axon/core/` — shared database, event logger, helpers (not "utils" — avoids junk drawer tendency)
- `schema/migrations/` and `schema/seeds/` — separate migration and seed files
- `review_packets/claude_to_sol/`, `review_packets/sol_to_claude/`, `review_packets/tyson_decisions/`
- `archive/superseded/` — old file versions
- `IMPLEMENTATION_REGISTER.md` — tracks provenance without polluting filenames

**Reasoning:** Clean importable filenames required for Python module imports. src/axon/ layout is professional and packaging-ready. Separating review packets from active code keeps the codebase clean. tyson_decisions/ subfolder separates Tyson's final product decisions from technical review exchanges.

---

## DEC-017 | Standard Claude/Sol Code Review Format
**Date:** 18/05/2026
**Proposed by:** Claude (initial 6-section format), Sol (added 3 improvements)
**Agreed by:** Claude, Sol, Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 18/05/2026
**Supersedes:** N/A

**Decision:** All Axon code reviews by Claude and Sol use the agreed 8-section standard format.

**Sol's three additions over Claude's initial proposal:**
1. Scope Compliance section — checks every review against approved MVP boundary (addresses RISK-007)
2. Testing/Evidence section — records whether code was actually run, environment, commands, results
3. Severity labels on concerns — Low / Medium / High / Critical — makes Tyson's decision making easier

**Sections:** Summary | What Works Well | Concerns & Suggested Changes (with severity) | Risks or Gaps | Testing/Evidence | Scope Compliance | Recommended Final Approach | Overall Rating (Adopt / Adopt with changes / Merge selected parts / Reject / Defer)

**Reasoning:** Standard format makes independent reviews easy for Tyson to compare and keeps technical feedback aligned with Axon's MVP boundaries, safety principles, and structure decisions.

---

## DEC-018 | Session Workflow Loop
**Date:** 03/06/2026
**Proposed by:** Tyson (concept), Claude (refined)
**Agreed by:** Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 03/06/2026
**Supersedes:** N/A

**Decision:** All development sessions follow a standard 8-step sprint loop:
1. Load context (INTRO + five documents)
2. Orient — Claude confirms current step from DOC2
3. Claude produces implementation; Claude writes explicit Sol prompt
4. Sol adversarial review + parallel implementation
5. Claude reviews both using DEC-017; writes final merged version
6. Claude writes Cline prompt; Tyson pastes once; Cline writes files and runs test
7. Tyson pastes Cline output back; Claude confirms
8. Claude updates all five documents; next step defined; new conversation

**Step size discipline:** No more than 2-3 files per session. Larger components split across multiple sessions.

**Reasoning:** Fixed loop reduces cognitive overhead per session, keeps context budgets manageable, and gives Tyson a predictable two-touch relay per step (one paste to Cline, one paste back). Claude handles all prompt authoring to minimise Tyson's translation work.

---

## DEC-019 | Formal Team Roles
**Date:** 03/06/2026
**Proposed by:** Tyson (intent), Claude (formalised)
**Agreed by:** Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 03/06/2026
**Supersedes:** Informal role assignments from Sessions 1–3

**Decision:** Team roles formally defined as:

| Who | Role |
|---|---|
| Tyson | Product owner, final decision maker, relay |
| Claude | Architecture, document control, session management, merged code author, explicit Cline prompt author, explicit Sol prompt author |
| Sol | Parallel implementation, adversarial stress-testing, Windows API expertise |
| Cline | File writes, test execution, output reporting — autonomy increasing progressively |

**Key changes from prior informal arrangement:**
- Claude now writes explicit Sol prompts and Cline prompts each session
- Sol's review role shifts toward adversarial stress-testing ("what breaks this?") in addition to parallel implementation
- Cline autonomy increases progressively: controlled executor now → expanded mid-build → full agent mode later

**Reasoning:** Reducing Tyson's relay burden and cognitive load is a primary goal. Claude authoring all prompts means Tyson's job is copy-paste, not translation. Sol's adversarial angle strengthens merged output quality beyond what parallel implementation alone achieves.

---

## DEC-020 | Development Step Plan
**Date:** 03/06/2026
**Proposed by:** Claude
**Agreed by:** Tyson ✅
**Status:** ✅ Confirmed — signed off by Tyson 03/06/2026
**Supersedes:** N/A

**Decision:** Axon MVP development proceeds in 15 session-sized steps, each producing no more than 2-3 files. Steps may be split further if context budget requires.

S1: GitHub sync + IMPLEMENTATION_REGISTER.md
S2: Merged v2 schema + database core (schema.sql, database.py)
S3: Merged v2 collectors (collectors.py)
S4: Event logger + capability registry seed (event_logger.py, seed SQL)
S5: Observation Engine smoke tests (test_observation.py)
S6: Goal Engine preset modes (goal_engine.py)
S7: Decision Engine rule-based recommendations (decision_engine.py)
S8: Simulation Mode (simulation.py)
S9: Action Engine execution + pre-action snapshot (action_engine.py)
S10: Rollback system (rollback.py)
S11: Outcome logging (outcome_logger.py)
S12: CLI / dev dashboard (cli.py)
S13: AI explanation layer (explanation.py)
S14: Onboarding + tolerance profile (onboarding.py)
S15: Integration + end-to-end test

**Reasoning:** Step size discipline is the primary constraint given Tyson's current free plan context limits. Small steps keep each session completable within context budget and give Tyson natural breakpoints to save and reset. Claude will flag if any step needs splitting mid-session.

---
*New decisions appended chronologically. Entries never deleted or modified after session closes.*
