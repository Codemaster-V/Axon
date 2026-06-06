# AXON — Architectural Risks & Assumptions
**Version:** 1.1
**Created:** 15/05/2026
**Last Updated:** 18/05/2026
**Maintained by:** Claude

> This document tracks known technical risks, unresolved uncertainties, and assumptions currently being made. Its purpose is to prevent assumptions from quietly becoming facts over time, and to surface potential problems before they become expensive to fix.

---

## How to Use This Document

- **Risks** — things that could go wrong and need mitigation planning
- **Assumptions** — things we are treating as true but have not yet validated
- **Status** — Open / Mitigated / Validated / Accepted

When a risk is mitigated or an assumption is validated, update the status and note how. Do not delete the entry.

Note: Current Technical Assumptions are also tracked in DOC2 Current State for quick operational reference. This document contains the full detail and reasoning.

---

## Architectural Risks

### RISK-001 | Rollback Reliability
**Status:** Open
**Raised by:** Sol
**Description:** The rollback system is a foundational trust mechanism. If a user cannot reliably undo an action Axon took, the product's core trust proposition fails.
**Concern:** Snapshot-based rollback for app-controlled changes may be more complex than it appears depending on which actions are taken. Some changes are inherently temporary; others require reliable state restoration. Sol's review of Claude v1 specifically flagged that "cache cleanup" should not be described as truly restorable — cache naturally rebuilds rather than being restored from a snapshot.
**Mitigation needed:** Define the exact rollback mechanism for each action type in the capability_registry before implementation begins. Classify rollback types accurately (true restoration vs. natural rebuild vs. toggle reversal). Test rollback for every permitted action type before shipping.

---

### RISK-002 | Windows Permission Complexity
**Status:** Open
**Raised by:** Sol
**Description:** Windows permissions for system-level telemetry, process monitoring, and startup management vary across Windows versions and user account types.
**Concern:** The Observation Engine may behave inconsistently across different Windows configurations. Some users may lack permissions required for certain actions.
**Mitigation needed:** Audit required permissions for each planned action type early. Design graceful degradation — Axon should work in reduced-capability mode if certain permissions are unavailable.

---

### RISK-003 | Telemetry Reliability
**Status:** Open
**Raised by:** Sol
**Description:** Windows telemetry APIs for CPU, GPU, RAM, and thermal data are not uniformly reliable or consistent across hardware vendors.
**Concern:** GPU temperature access varies significantly by vendor (NVIDIA vs AMD vs Intel). Thermal data may be unavailable or inaccurate on some hardware configurations. Both Claude and Sol v1 implementations noted GPU and thermal telemetry unavailable in non-Windows sandbox environments — real-world Windows testing still required.
**Mitigation needed:** Identify which telemetry APIs will be used for each data type. Define fallback behaviour when data is unavailable. Do not display metrics that cannot be reliably sourced.

---

### RISK-004 | Game Compatibility and Anti-Cheat
**Status:** Open
**Raised by:** Sol
**Description:** Axon's gaming optimisation features assume it can operate alongside running games without causing conflicts.
**Concern:** Some games have anti-cheat systems (EAC, BattlEye, Vanguard) that may flag or block background monitoring processes.
**Mitigation needed:** Research anti-cheat compatibility early. Consider whether Axon's process should carry a recognised safe signature. Test with the most common anti-cheat systems before release.

---

### RISK-005 | Process Suspension Edge Cases
**Status:** Open
**Raised by:** Sol
**Description:** Suspending background processes is a core MVP action. Some processes that appear inactive may be performing important background tasks.
**Concern:** Incorrectly suspending a critical system process or a process a running application depends on could cause instability or crashes.
**Mitigation needed:** Build the capability_registry with conservative process whitelists and blacklists. Never suspend processes outside a curated safe list in MVP. Require high confidence_of_safety before any process suspension recommendation. Sol's v1 implementation noted this needs curated safe/blocked process lists before the action engine is built.

---

### RISK-006 | Outcome Attribution Accuracy
**Status:** Open
**Raised by:** Claude
**Description:** Measuring whether an optimisation worked requires attributing performance changes to Axon's actions specifically.
**Concern:** System performance fluctuates naturally. Attributing improvement or degradation to a specific action when other variables are changing simultaneously is difficult and may produce false learning signals.
**Mitigation needed:** Implement environmental_context on outcome_record (confirmed in V0.2). Define a minimum observation window before recording outcomes.

---

### RISK-007 | Scope Creep During Development
**Status:** Open — ongoing vigilance required
**Raised by:** Sol and Claude independently
**Description:** The Jarvis vision is expansive. There will be natural temptation to add features beyond MVP scope as development progresses.
**Concern:** Scope expansion delays shipping, increases complexity, and risks an over-engineered product that never reaches users.
**Mitigation:** The MVP out-of-scope list in DOC2 is the hard boundary. Any proposed addition must go through Tyson for explicit sign-off. Claude and Sol are both responsible for flagging when discussions drift out of scope. DEC-017 now includes a Scope Compliance section in every code review to enforce this actively.

---

### RISK-008 | Capability Registry Completeness
**Status:** Open
**Raised by:** Sol (surfaced in v1 code review)
**Description:** The capability_registry must explicitly list both permitted AND blocked action types.
**Concern:** Claude v1 implementation only seeded permitted actions. Blocked actions (registry modification, driver changes, BIOS, overclocking, etc.) were omitted rather than explicitly marked as disallowed. Omission is weaker than explicit prohibition — future code could accidentally enable a blocked action without triggering a visible violation.
**Mitigation needed:** Capability registry seed data must include all blocked MVP action types with is_permitted_in_mvp = 0. This is a required fix before v2 implementation is adopted.

---

### RISK-009 | Event Log Immutability Not Enforced
**Status:** Open
**Raised by:** Sol (surfaced in v1 code review)
**Description:** The event_log is described as immutable in the architecture, but neither v1 implementation enforces this at the database level.
**Concern:** If the event log can be modified or deleted, the trust, auditability, and learning foundations are compromised.
**Mitigation needed:** Add database-level protection for the event_log table in the merged v2 implementation. Consider triggers or application-level enforcement that prevents UPDATE and DELETE on event_log rows.

---

## Assumptions

### ASSUMPTION-001 | SQLite Is Sufficient for MVP Local Storage
**Status:** Open
**Assumed by:** Claude and Sol
**Assumption:** SQLite will handle the event log, schema entities, and query load for a single-device MVP without performance issues.
**Risk if wrong:** Performance degradation under high telemetry frequency could affect the Observation Engine.
**Validation needed:** Load test the SQLite schema with realistic telemetry volumes before committing to it as the storage layer.

---

### ASSUMPTION-002 | Deterministic Rules Are Sufficient for MVP Decision Engine
**Status:** Open
**Assumed by:** Sol and Claude
**Assumption:** A rule-based, deterministic Decision Engine is sufficient for the MVP action recommendation set. AI is reserved for goal interpretation, explanation, and conversation.
**Risk if wrong:** If rule-based logic cannot produce sufficiently valuable recommendations, early users may be underwhelmed.
**Validation needed:** Define the curated safe action set and test whether rule-based recommendations produce measurable improvements.

---

### ASSUMPTION-003 | Users Will Trust the Approval-First Model
**Status:** Open
**Assumed by:** Claude and Sol
**Assumption:** Requiring user approval for every action in MVP will feel safe and trustworthy rather than cumbersome.
**Risk if wrong:** If approval friction is too high, users may disengage before experiencing value.
**Validation needed:** User experience testing with the approval flow. Simulation Mode may help reduce friction.

---

### ASSUMPTION-004 | Preset Goal Modes Are Sufficient for MVP Goal Engine
**Status:** Open
**Assumed by:** Claude and Sol
**Assumption:** Preset modes (Maximise FPS / Quiet Mode / Free Storage / Balanced) are sufficient without natural language goal input.
**Risk if wrong:** Users may find preset modes too blunt and want more nuanced goal expression earlier than anticipated.
**Validation needed:** User feedback during early testing.

---

### ASSUMPTION-005 | All Permitted MVP Actions Are Reliably Reversible
**Status:** Open — partially refined
**Assumed by:** Claude
**Assumption:** Every action Axon takes in MVP can be reliably reversed by Axon.
**Risk if wrong:** If any permitted action proves difficult to roll back, the trust foundation of the product is compromised.
**Refinement from Sol v1 review:** "Cache cleanup" should not be described as reversible in the traditional sense — cache rebuilds naturally but is not restored from a snapshot. Rollback type classification needs to be more precise per action type.
**Validation needed:** Test rollback for every action type in the capability_registry before including it in the permitted set. See also RISK-001.

---

### ASSUMPTION-006 | psutil Provides Sufficient Cross-Vendor Telemetry
**Status:** Open
**Assumed by:** Claude and Sol
**Assumption:** psutil will provide reliable CPU, RAM, storage, and process telemetry across the major Windows hardware configurations Axon targets.
**Risk if wrong:** Some hardware-specific telemetry (especially GPU temperature from different vendors) may require additional libraries or vendor-specific APIs.
**Validation needed:** Test on real Windows hardware with NVIDIA, AMD, and Intel GPU configurations. Identify gaps and plan fallback approaches before v2 is finalised.

---

## Validated / Mitigated Items

*None yet — this section will be populated as risks are addressed and assumptions are tested.*

---
*New risks and assumptions added as identified. Status updated as addressed. Entries never deleted.*
*v1.0 created 15/05/2026 | v1.1 — Added RISK-008, RISK-009, ASSUMPTION-006; updated RISK-001 and ASSUMPTION-005 with Sol v1 code review findings 18/05/2026*
*No new risks or assumptions in Session 4 (03/06/2026) — document remains current*
