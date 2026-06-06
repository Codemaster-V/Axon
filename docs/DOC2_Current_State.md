# AXON — Current State
**Version:** 1.4
**Last Updated:** 06/06/2026
**Updated by:** Claude

> ⚠️ CONTEXT WINDOW NOTICE: Claude will flag Tyson when a conversation is approaching its limit so all five documents can be updated and saved before the conversation becomes uninteractable. Always produce updated documents at the end of each session.

---

## Version Relationships

| Component | Current Version |
|---|---|
| Project Bible | V1.1 |
| Current State | V1.4 |
| Decisions Log | Live |
| Risks & Assumptions | V1.1 |
| Journal | Live |
| Data Architecture Schema | V0.2 |
| MVP Spec | V0.1 ✅ Signed off by Tyson 15/05/2026 |
| MVP Stack Decision | Python ✅ Signed off by Tyson 18/05/2026 (DEC-015) |
| Folder Structure | DEC-016 ✅ Signed off by Tyson 18/05/2026 |
| Code Review Format | DEC-017 ✅ Signed off by Tyson 18/05/2026 |
| Session Workflow | DEC-018 ✅ Signed off by Tyson 03/06/2026 |
| Team Roles | DEC-019 ✅ Signed off by Tyson 03/06/2026 |
| Development Step Plan | DEC-020 ✅ Signed off by Tyson 03/06/2026 |

---

## Project Status

**Phase:** S1 complete. GitHub live, Cline operational, document workflow established. Ready for S2.

**Active participants and roles:**

| Who | Role |
|---|---|
| **Tyson** | Product owner, final decision maker, relay between tools |
| **Claude** | Architecture, document control, session management, merged code author, explicit Cline prompt author, explicit Sol prompt author |
| **Sol (ChatGPT)** | Parallel implementation, adversarial stress-testing ("what breaks this?"), Windows API expertise |
| **Cline** | File writes, git commits, document uploads, test execution — autonomy increasing progressively |

**Development environment:** VS Code installed on Tyson's PC (v1.120). Claude Code and Cline extensions installed. Project folder at E:/Github/Axon synced to GitHub.

**GitHub:** Repository at github.com/thevendettagamingchannel-rgb/Axon. Local clone at E:/Github/Axon. Initial commit live. ✅

**Known setup issue:** Git not in Cline's terminal PATH — Cline can commit but pushes fall back to GitHub Desktop. Fix: add git to Windows system PATH. To be resolved before or during S2.

---

## Session Workflow (DEC-018)

Each session follows this loop:

1. **Load context** — Tyson uploads INTRO + five documents at session start
2. **Orient** — Claude reads documents, confirms current step from DOC2 Immediate Next Steps
3. **Independent coding** — Claude produces implementation; Claude writes explicit Sol prompt for Tyson to relay
4. **Sol adversarial review** — Sol stress-tests Claude's implementation ("what breaks this?") and produces her own version
5. **Compare and agree** — Claude reviews both using DEC-017 format; Claude writes final merged version explicitly
6. **Cline execution** — Claude writes explicit Cline prompt; Tyson pastes into Cline; Cline writes files and runs tests
7. **Confirm result** — Tyson pastes Cline output back; Claude confirms pass/fail
8. **Update and reset** — Claude updates all five documents; next step defined clearly in DOC2; new conversation

**Step size discipline:** Each session targets no more than 2-3 files of code. Larger components split across multiple sessions.

**Tyson relay touches per step:** Two — one paste into Cline, one paste of output back. Claude handles all prompt authoring.

---

## Cline Autonomy Progression

| Phase | Cline Mode | When |
|---|---|---|
| Current (S1–S5) | Controlled executor — Claude writes exact prompt; Cline writes files and runs one test | Now |
| Mid-build (S6–S7) | Expanded — Cline reads project folder, makes multi-file edits, iterates on test failures | When codebase stabilises |
| Later (S8+) | Full agent mode — high-level instruction; Cline works autonomously; checks back at decision points | Claude will flag when ready |

---

## Development Step Plan (DEC-020)

| Step | What Gets Built | Files | Status |
|---|---|---|---|
| **S1** | GitHub sync + IMPLEMENTATION_REGISTER.md | Setup only | ✅ Complete |
| **S2** | Merged v2 — schema + database core | `schema.sql`, `database.py` | ⏳ Next |
| **S3** | Merged v2 — collectors | `collectors.py` | Pending |
| **S4** | Merged v2 — event logger + capability registry seed | `event_logger.py`, seed SQL | Pending |
| **S5** | Smoke tests for Observation Engine | `test_observation.py` | Pending |
| **S6** | Goal Engine — preset modes | `goal_engine.py` | Pending |
| **S7** | Decision Engine — rule-based recommendations | `decision_engine.py` | Pending |
| **S8** | Simulation Mode | `simulation.py` | Pending |
| **S9** | Action Engine — execution + pre-action snapshot | `action_engine.py` | Pending |
| **S10** | Rollback system | `rollback.py` | Pending |
| **S11** | Outcome logging | `outcome_logger.py` | Pending |
| **S12** | CLI / dev dashboard | `cli.py` | Pending |
| **S13** | AI explanation layer | `explanation.py` | Pending |
| **S14** | Onboarding + tolerance profile | `onboarding.py` | Pending |
| **S15** | Integration + end-to-end test | Full stack smoke test | Pending |

---

## Current Implementation Philosophy

- **Conservative AI** — deterministic, rule-based execution in MVP; AI handles goal interpretation and explanation only
- **Trust before autonomy** — every action requires user approval in MVP
- **Simulation before execution** — users see projected impact before anything is applied
- **Rollback required** — no action is permitted in MVP unless it can be reliably reversed
- **Observation first** — foundational telemetry and event logging must be solid before AI layers are added
- **Python first** — MVP implemented in Python for speed, readability, and ecosystem. Architected cleanly so C# Windows shell can wrap or replace later if needed.

---

## Known Non-Goals

These are things Axon explicitly is not, especially in MVP. Useful for preventing identity drift during development.

- Not a general AI assistant or chatbot
- Not antivirus or security software
- Not an aggressive system "tuner" or overclocker
- Not competing with enterprise IT management tools in MVP
- Not a hardware replacement advisor in MVP
- Not an autonomous agent in MVP

---

## Project Folder Structure (DEC-016)

```
axon-project/
│
├── docs/                          ← Five project documents
│
├── src/
│   └── axon/
│       ├── engines/
│       │   ├── observation_engine/
│       │   ├── goal_engine/
│       │   ├── decision_engine/
│       │   ├── action_engine/
│       │   └── learning_engine/
│       │
│       ├── core/                  ← Shared DB, event logger, helpers
│       ├── config/                ← Settings, capability registry
│       └── cli.py
│
├── schema/
│   ├── migrations/                ← Schema SQL files
│   └── seeds/                     ← Seed data (capability registry)
│
├── ui/
├── tests/
├── scripts/
├── data/
│
├── review_packets/
│   ├── claude_to_sol/
│   ├── sol_to_claude/
│   └── tyson_decisions/           ← Tyson's signed-off decision files
│
├── archive/
│   └── superseded/
│
├── IMPLEMENTATION_REGISTER.md
├── README.md
├── requirements.txt
└── .gitignore
```

**File naming convention:**
- Active code files: clean importable Python names (e.g. `observation_engine.py`)
- Review packets and archive copies: `YYMMDD_ComponentName_Author_vN` (e.g. `260518_Observation_Engine_Claude_v1.py`)
- Tyson decision files: `YYMMDD_DECNNN_Decision_Name.md`

---

## MVP Stack (DEC-015)

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Database | SQLite |
| Core monitoring | psutil |
| Windows-specific | WMI / pywin32 where needed |
| Schema/migrations | Plain SQL migration files |
| UI | Deferred — CLI/dev dashboard first |
| Packaging (future) | PyInstaller |

---

## Current Schema Version — Data Architecture V0.2

### Confirmed Entities

| Entity | Status | Notes |
|---|---|---|
| device_profile | ✅ Confirmed | Hardware fingerprint and capability map |
| system_snapshot | ✅ Confirmed | Point-in-time state; foundation for rollback |
| event_log | ✅ Confirmed | Immutable; flexible JSON payload; system memory layer |
| goal_record | ✅ Confirmed | Captures user intent and interpreted goal |
| recommendation_record | ✅ V0.2 | Split confidence: effectiveness + safety separately |
| action_record | ✅ Confirmed | Links recommendations to execution and outcome |
| outcome_record | ✅ V0.2 | Includes environmental_context block |
| user_tolerance_profile | ✅ Confirmed | Optimisation personality; set at onboarding, ML-refined later |
| capability_registry | ✅ V0.2 | Formal registry of permitted actions, permissions, risk classifications |

### Deferred Entities

| Entity | Reason | Target Phase |
|---|---|---|
| explanation_record | Post-MVP; communication layer optimisation | Phase 2 |

---

## Current MVP Spec — V0.1 ✅ Signed off by Tyson 15/05/2026

**One sentence:** A Windows desktop app that monitors system performance, interprets user goals, and recommends optimisations for gaming and general performance — with full explainability, user approval required for all actions, simulation mode, and rollback support.

**Platform:** Windows only
**Audience:** Gamers and performance-focused PC users
**Storage:** Local SQLite, no cloud dependency

### Engine Status in MVP

| Engine | MVP Status | Notes |
|---|---|---|
| Observation Engine | ✅ Full | First to be implemented — v1 implementations complete |
| Goal Engine | ⚡ Partial | Preset modes only — no free-text input |
| Decision Engine | ⚡ Partial | Deterministic/rule-based; AI for explanation only |
| Action Engine | ✅ Active | User approval required for every action |
| Learning Engine | 🔵 Minimal | Logs outcomes and approve/decline patterns only |

### In Scope for MVP

- CPU/GPU/RAM/thermal monitoring
- Startup app and background process analysis
- Storage usage tracking
- Preset goal modes: Maximise FPS / Quiet Mode / Free Storage / Balanced
- Simulation Mode — show proposed changes and expected impact before execution
- Recommendation cards: confidence (effectiveness + safety), expected benefit, risk level, reversibility
- One-click approve and execute
- Pre-action system snapshot
- Rollback of app-controlled changes (not full system restoration)
- Action and outcome logging
- Basic AI conversational interface for explaining recommendations
- User tolerance profile set during onboarding (not yet ML-refined)

### Safe Action Boundary (DEC-010)

**Allowed in MVP:**
- Startup app toggles
- Process suspension
- Power profile changes
- Temporary optimisation states
- Cache cleanup
- Storage cleanup recommendations

**Explicitly disallowed in MVP:**
- Registry modification
- Driver modification
- BIOS/firmware interaction
- Overclocking or undervolting
- Permanent OS configuration changes
- Security policy changes

### MVP Success Metrics

- Measurable FPS improvement in at least one common scenario
- Measurable boot time or RAM improvement
- Zero unrecoverable actions (rollback must always work)
- User can always explain why a recommendation was made
- User understands what was changed, what impact occurred, and how to reverse it
- Simulation Mode used before first action by majority of new users

### Explicitly Out of Scope for MVP

Free-text goal input, autonomous execution, ML adaptation, cross-device, cloud sync, enterprise features, hardware upgrade recommendations, mobile platform, explanation_record entity

---

## Code Review Format (DEC-017)

All Claude/Sol code reviews use this standard format:

```
AXON — Code Review
Reviewer: [Claude / Sol]
Component: [e.g. Observation Engine + SQLite Schema]
Date: [YYYY-MM-DD]
Reviewing: [e.g. 260518_Sol_v2_Review_Package]
Scope Checked Against: [relevant DECs]

SECTION 1 — SUMMARY
SECTION 2 — WHAT WORKS WELL
SECTION 3 — CONCERNS & SUGGESTED CHANGES
  (each with Severity: Low / Medium / High / Critical)
SECTION 4 — RISKS OR GAPS SPOTTED
SECTION 5 — TESTING / EVIDENCE
  (Was code run? Environment? Commands? Pass/fail?)
SECTION 6 — SCOPE COMPLIANCE
SECTION 7 — RECOMMENDED FINAL APPROACH
SECTION 8 — OVERALL RATING
  Strengths / Weaknesses / Verdict: Adopt / Adopt with changes / Merge selected parts / Reject / Defer
```

---

## Implementation Status

### Observation Engine + Schema

| Item | Claude v1 | Sol v1 |
|---|---|---|
| All 9 schema entities | ✅ | ✅ |
| Event logging | ✅ | ✅ |
| CPU/RAM/storage telemetry | ✅ | ✅ |
| GPU telemetry | ⚡ Attempted | ✅ |
| Startup app detection | ✅ | ✅ |
| Power profile detection | ✅ | ✅ |
| DEC-016 folder structure | ❌ | ✅ |
| Modular file structure | ❌ (monolithic) | ✅ |
| Automated tests | ❌ | ✅ Stubs |
| requirements.txt | ❌ | ✅ |
| Blocked capabilities in registry | ❌ | ✅ |

**Cross-reviews complete:**
- Claude reviewed Sol v1 → Verdict: Sol v1 as base, merge Claude's GPU + startup app telemetry → merged v2
- Sol reviewed Claude v1 → Verdict: Merge selected parts, significant structural refactor needed before adoption

**Next step:** S1 (GitHub sync), then S2 (merged v2 schema + database core)

---

## Unresolved Technical Questions

- Exact GitHub repo URL (Tyson to confirm)
- Which Windows telemetry APIs will be used for GPU temperature (NVIDIA vs AMD vs Intel differences)?
- Exact rollback mechanism implementation for each permitted action type
- How will Simulation Mode calculate expected impact estimates in MVP — heuristic/rule-based assumed
- Rollback field accuracy — Sol flagged that "cache cleanup" rollback is better described as "cache naturally rebuilds" not true restoration

---

## Current Technical Assumptions

- SQLite is sufficient for MVP telemetry scale and query load
- Windows telemetry access is feasible without kernel-level drivers
- Process suspension is safely reversible for all permitted action types
- Simulation Mode impact estimates will be heuristic/rule-based in MVP, not ML-derived
- All permitted MVP actions can be reliably reversed by Axon
- psutil provides sufficient cross-vendor telemetry for CPU/RAM/storage; GPU requires vendor-specific libraries

---

## Immediate Next Steps

1. **Fix git PATH** — add git to Windows system PATH so Cline can push directly without GitHub Desktop fallback
2. **S2 — Merged v2 schema + database core** — Claude and Sol independently produce `schema.sql` and `database.py` using Sol's src/axon/ structure as base; cross-review; merge; Cline writes to project folder, commits and pushes

---
*v1.0 created 15/05/2026 | v1.1 — Sol recommendations 15/05/2026 | v1.2 — DEC-015/016/017, implementation status 18/05/2026 | v1.3 — DEC-018/019/020, workflow, roles, step plan, Cline autonomy progression 03/06/2026 | v1.4 — S1 complete, GitHub live, Cline operational, git PATH issue noted 06/06/2026*
