# AXON — Project Journal
**Maintained by:** Claude
**Format:** One entry per working session, appended chronologically. Entries never edited after session closes.

---

## 14/05/2026 — Session 1

**Participants:** Tyson, Claude, Sol (via Tyson relay)

**Summary:**

This was the founding session. The app concept was introduced to both Claude and Sol — a background AI optimisation app that monitors device usage, learns behaviour, and proactively suggests or applies optimisations.

Sol reviewed Claude's initial summary and produced a strong independent assessment. Both independently agreed that the core differentiator is not storage cleaning — it is adaptive behavioural optimisation.

Sol's most important contribution: pushback on iOS-first as the starting platform. Apple's sandboxing restrictions would gut the core functionality. Windows was agreed as the correct starting point.

Sol proposed the Windows AI gaming performance optimiser as the MVP entry point — measurable outcomes, motivated audience, accessible system permissions, impressive demos.

Tyson introduced the Jarvis analogy (Iron Man) — not as a chatbot, but as a goal-directed intelligent system that receives a high-level instruction and reconfigures its environment to achieve it. This was the conceptual breakthrough of the session.

Claude endorsed the Jarvis framing and identified it as architecturally significant — it changes the instruction layer, permission model, learning system, and hardware knowledge layer design. Claude and Sol aligned on a critical discipline: Jarvis guides the architecture; Jarvis does NOT define the MVP.

Sol proposed the 5-engine architecture: Observation, Goal, Decision, Action, Learning. Claude formally adopted this framework.

Sol raised Simulation Mode as an important early trust mechanism. Claude elevated it to a core MVP feature.

Sol raised the event-driven architecture point — store events, not just state. Claude agreed and connected it to the 5-engine model.

Claude drafted the V0.1 data schema with 7 entities. Sol critiqued V0.1 and proposed three additions accepted into V0.2: capability_registry, split confidence scoring, and environmental context on outcome_record. explanation_record deferred to post-MVP.

Claude drafted MVP Spec V0.1. Sol reviewed and proposed two amendments: formal safe action boundary and clarification that rollback means app-controlled change reversal only.

**Session Outcome Summary:**
- What changed: Project concept formalised; architecture foundations established; schema V0.2 agreed; MVP Spec V0.1 drafted
- What was agreed: DEC-001 through DEC-009, DEC-014
- What remains unresolved: App name, documentation system, Tyson formal sign-offs on MVP spec
- Immediate next step: Resolve app name and documentation system, then obtain Tyson sign-offs before coding begins

---

## 15/05/2026 — Session 2

**Participants:** Tyson, Claude, Sol (via Tyson relay — full PDF export of Sol conversation history provided by Tyson)

**Summary:**

Session focused on housekeeping decisions before implementation begins: app name, documentation system, and formal sign-offs.

Tyson uploaded a full PDF export of the Sol conversation history, giving Claude a complete record of all prior Sol contributions.

**App name:** Working names (Jarvis, Vision, Mind Stone, Infinity Stone) ruled out due to Marvel IP risk. Claude proposed Axon; Tyson proposed North Star as alternative. Sol reviewed both and confirmed Axon as the stronger option — scales to enterprise, sounds like real infrastructure software, no IP issues. All three parties aligned on Axon. Tyson formally confirmed.

**Documentation system:** Claude proposed four documents; Sol added a fifth (Risks & Assumptions document — her recommendation). System finalised as five documents plus daily journal. Claude explained to Tyson how the system works: documents dropped at start of new conversations to restore full context. Claude will flag Tyson when a conversation is approaching its limit.

**Sol's document review:** Sol reviewed all five documents and recommended several improvements: Non-Negotiable Principles section for DOC1; version relationships table, implementation philosophy section, known non-goals section, and current technical assumptions for DOC2; Supersedes field for DOC3 decision entries; structured Session Outcome Summary format for journal entries. All accepted and incorporated into this session's updated documents.

**Tyson formal sign-offs confirmed this session:**
- App name: Axon ✅ (DEC-012)
- Five-document system ✅ (DEC-013)
- MVP Spec V0.1 ✅ (DEC-010, DEC-011)

**Session Outcome Summary:**
- What changed: All five documents updated with Sol's recommendations; all outstanding sign-offs confirmed; project fully ready for implementation
- What was agreed: DEC-010, DEC-011, DEC-012, DEC-013 all confirmed by Tyson
- What remains unresolved: Which Windows telemetry APIs to use; exact rollback implementation mechanism; Simulation Mode impact estimate method
- Immediate next step: Start new conversation with five documents; Claude and Sol begin independent parallel implementation of Observation Engine and SQLite schema

---

## 18/05/2026 — Session 3

**Participants:** Tyson, Claude, Sol (via Tyson relay)

**Summary:**

Session focused on establishing the development environment, agreeing the technology stack, formalising the project folder structure, completing independent v1 implementations of the Observation Engine and SQLite schema, and conducting cross-reviews.

**Development environment:**
- Tyson installed VS Code (v1.120) on his PC
- Claude Code and Cline extensions installed
- Continue and Genie AI (ChatGPT) extensions also installed
- Decision made to keep manual file control for now; Cline deferred until GitHub is set up and workflow is more established

**Technology stack (DEC-015):**
- Sol recommended Python for the MVP; Claude independently agreed
- Stack: Python 3.12, SQLite, psutil, WMI/pywin32 where needed, PyInstaller for packaging
- Key framing: Python engine layer, architected so C# Windows shell can wrap or replace later
- Tyson signed off ✅

**Folder structure (DEC-016):**
- Claude proposed initial structure; Sol proposed major revision (src/axon/ layout, core/ instead of utils/, no dated filenames on active code, IMPLEMENTATION_REGISTER.md)
- Claude added tyson_decisions/ subfolder to review_packets/ — accepted by Sol
- Sol formalised review_packets/tyson_decisions/ file naming convention (e.g. 260518_DEC-016_Folder_Structure_Approved.md)
- Tyson signed off ✅
- Folders created on Tyson's machine (Game Drive E: / App Development / axon-project)

**Code review format (DEC-017):**
- Claude proposed 6-section format; Sol added 3 improvements: Scope Compliance section, Testing/Evidence section, severity labels on concerns
- Claude fully agreed with Sol's additions
- Tyson signed off ✅

**Independent v1 implementations:**
- Claude produced: observation_engine.py (monolithic), axon_schema.sql — saved to correct project folders
- Sol produced: modular src/axon/ structure with separate collectors.py, models.py, core database layer, comprehensive test stubs, smoke test scripts

**Cross-reviews (both using DEC-017 format):**
- Claude reviewed Sol v1: Strong structure, correct scope. Two gaps: GPU telemetry and startup app enumeration. Verdict: Sol v1 as base for merged v2; merge Claude's GPU + startup telemetry code
- Sol reviewed Claude v1: Correct scope, readable, all 9 schema entities present, self-test runs. Major concerns: does not follow DEC-016 folder structure (High), too monolithic (Medium-High), blocked capabilities missing from registry (High), no automated tests (Medium), no requirements.txt (Medium). Verdict: Merge selected parts with significant structural refactor

**New risks surfaced from code reviews:**
- RISK-008: Capability registry must explicitly list blocked actions, not just omit them
- RISK-009: Event log immutability not enforced at database level in v1 implementations
- ASSUMPTION-006: psutil cross-vendor GPU telemetry reliability unvalidated

**GitHub:**
- Tyson created GitHub repo at github.com/thevendettagamingchannel-rgb/Axon
- Full GitHub setup (local sync, VS Code integration) deferred to next session

**Session Outcome Summary:**
- What changed: DEC-015, DEC-016, DEC-017 all agreed and signed off; folder structure created; v1 implementations complete; cross-reviews complete; two new risks and one new assumption identified; GitHub repo created
- What was agreed: Python stack, folder structure, review format, merged v2 approach
- What remains unresolved: GitHub setup; merged v2 implementation; IMPLEMENTATION_REGISTER.md creation; Sol's review file not yet saved to project folder (pending)
- Immediate next step: New conversation — GitHub setup, then merged v2 implementation

---

## 03/06/2026 — Session 4

**Participants:** Tyson, Claude

**Summary:**

Session focused on formalising the development workflow and team roles before implementation resumes. No code written this session — process architecture only.

**GitHub status update:** Tyson confirmed the project folder on E: drive has been cloned from GitHub. Exact GitHub repo location to be confirmed in a future session.

**Workflow formalised (DEC-018):**

Tyson proposed and Claude refined a sprint-based session loop:
1. Load context (INTRO + five documents uploaded at session start)
2. Claude reads documents and confirms current step from DOC2 Immediate Next Steps
3. Claude and Sol independently produce implementations
4. Compare and agree using DEC-017 format — Claude writes final merged version explicitly
5. Claude writes Cline prompt; Tyson pastes into Cline; Cline writes files and runs tests
6. Cline output pasted back; Claude confirms result
7. Claude updates all five documents; next step defined clearly in DOC2
8. New conversation starts clean

**Step size discipline agreed:** Each session targets no more than 2-3 files of code. Larger components split across multiple sessions. This keeps context budgets manageable on Tyson's current free plan.

**Team roles formalised (DEC-019):**

| Who | Role |
|---|---|
| Claude | Architecture, document control, session management, merged code author, explicit Cline prompt author, explicit Sol prompt author |
| Sol | Parallel implementation, adversarial review ("what breaks this?"), Windows API expertise |
| Cline | File writes, test execution, output reporting — autonomy to increase over time |
| Tyson | Product owner, final decisions, relay |

Key changes from prior informal roles:
- Claude now writes explicit Sol prompts and Cline prompts each session — reduces Tyson relay burden
- Sol's review role shifts toward adversarial stress-testing in addition to parallel implementation
- Cline autonomy to increase progressively as codebase stabilises (target: full agent mode by Steps 6-7)

**Development step plan agreed (DEC-020):**

15-step build plan formalised in DOC2. Each step is one session. Steps sized to fit context budget.

**Cline autonomy strategy:**
- Current: Claude writes single Cline prompt per session; Tyson pastes once; Cline writes all files and runs test; Tyson pastes output back. Two touches per step.
- Future (Steps 6-7+): Full Cline agent mode — higher-level instruction, Cline works through multiple files autonomously, checks back only at decision points. Claude will flag when this threshold is reached.

**Paid plan recommendation:** Claude noted that upgrading from the free plan would meaningfully reduce mid-session context limit risk, particularly during coding sessions where code, reviews, and document updates all compete for context.

**Session Outcome Summary:**
- What changed: DEC-018 (workflow), DEC-019 (team roles), DEC-020 (step plan) agreed; all five documents updated
- What was agreed: Sprint loop, step breakdown, role assignments, Cline autonomy progression strategy
- What remains unresolved: Exact GitHub repo location (Tyson to confirm); GitHub sync setup still pending
- Immediate next step: Session 5 — GitHub sync setup (S1), then begin S2 (merged v2 schema + database core)

---

## 06/06/2026 — Session 5

**Participants:** Tyson, Claude

**Summary:**

Session focused on completing S1 — GitHub sync, initial file commit, and IMPLEMENTATION_REGISTER.md creation. Also discussed VS Code agents and finalised the push workflow.

**VS Code agents discussion:**
Tyson asked whether additional VS Code agents could improve the workflow. Claude assessed current tooling and recommended against adding multiple competing AI assistants. Key recommendation: configure Cline with GitHub MCP server in a future session to allow direct repo read/write without GitHub Desktop fallback. Deferred to after S2 as a setup improvement.

**GitHub sync completed:**
- Axon repo confirmed at E:/Github/Axon (cloned folder)
- Old project files copied from Axon (old) to Axon — excluded chat exports, zip files, and duplicate .git folder
- Initial commit pushed to GitHub via GitHub Desktop: "Initial commit — import existing project structure from Sessions 1-3"
- 6 files committed: .gitattributes, 260518_Sol_v1_Review_Claude.md, review packet zips, axon_schema.sql, observation_engine.py

**Cline proven in production:**
- First real Cline task executed: create IMPLEMENTATION_REGISTER.md in project root
- Cline created file, committed via git, and attempted push autonomously
- Push via Cline terminal failed (git not in Cline's PATH) — GitHub Desktop used as fallback for push
- Fix needed: add git to system PATH so Cline can push directly in future sessions
- GitHub authentication completed via browser during session — now persisted for future pushes

**S1 complete:**
- ✅ GitHub repo live and synced
- ✅ DEC-016 folder structure committed
- ✅ IMPLEMENTATION_REGISTER.md created and pushed
- ✅ Cline proven working for file creation and git commits
- ✅ GitHub authentication configured

**Document upload via Cline:**
- End-of-session document update workflow tested: Claude produces updated documents, Cline uploads them to the docs/ folder in the project, commits and pushes to GitHub. This replaces manual document management.

**Session Outcome Summary:**
- What changed: S1 fully complete; GitHub live; Cline operational; document upload workflow via Cline established
- What was agreed: Git PATH fix needed before next session; Cline handles document commits going forward
- What remains unresolved: Git not in Cline's terminal PATH (workaround: GitHub Desktop for pushes until fixed); Cline GitHub MCP configuration deferred
- Immediate next step: Session 6 — S2 (merged v2 schema + database core): schema.sql and database.py

---
*New entries appended at end of each working session. Entries never edited after session closes.*
