# AXON — New Conversation Introduction
**Last Updated:** 06/06/2026
**Purpose:** Paste this at the start of any new conversation with Claude or Sol, along with all five project documents. This gives immediate context and prevents unnecessary re-explanation.

---

## For Claude

Hi Claude. We are continuing work on a software project called Axon. You have been involved in this project from the start and have been handling architecture, documentation, parallel code development, document control, and writing explicit prompts for Sol and Cline each session.

The five documents attached contain everything you need to get fully up to speed:
- DOC1: Project Bible — vision, philosophy, non-negotiable principles
- DOC2: Current State — schema version, MVP spec, step plan, implementation priorities, pending questions
- DOC3: Decisions Log — every significant decision with full reasoning (DEC-001 through DEC-020)
- DOC4: Risks & Assumptions — known risks and unvalidated assumptions
- Journal: Session-by-session record of what has been discussed and decided

Please read all five documents before responding. The most important immediate context is in DOC2 Current State — check the "Immediate Next Steps" section for where we are up to.

**Your role this project (DEC-019):**
- Architecture and document control (as always)
- Write the merged final code each session
- Write the explicit Cline prompt for Tyson to paste — word for word, ready to use
- Write the explicit Sol prompt for Tyson to relay — word for word, ready to use
- Flag when the conversation is approaching context limit
- Flag when Cline is ready to move to expanded or full agent mode

**Team structure:**
- Tyson — product owner, final decisions, relay
- Claude — architecture, documents, merged code, all prompt authoring
- Sol (ChatGPT) — parallel implementation, adversarial stress-testing, Windows API expertise
- Cline — file writes, test execution, output reporting

**Session workflow (DEC-018):**
1. Load context → 2. Orient → 3. Claude codes + writes Sol prompt → 4. Sol adversarial review + implementation → 5. Compare, agree, Claude writes merged version → 6. Claude writes Cline prompt, Tyson pastes once → 7. Tyson pastes Cline output back, Claude confirms → 8. Update all five documents, define next step, reset

**Where we are up to (as of Session 5, 06/06/2026):**
- DEC-001 through DEC-020 all confirmed
- S1 fully complete — GitHub live at github.com/thevendettagamingchannel-rgb/Axon, local clone at E:/Github/Axon
- Cline operational — creates files, commits via git; pushes currently fall back to GitHub Desktop (git PATH fix needed)
- Document upload workflow via Cline established
- Known issue: git not in Cline's terminal PATH — fix before or during S2
- Immediate next step: S2 — merged v2 schema (schema.sql) and database core (database.py)

---

## For Sol

Hi Sol. We are continuing work on a software project called Axon. You have been involved in this project from the start alongside Claude (Anthropic's AI).

The five documents attached contain everything you need to get fully up to speed:
- DOC1: Project Bible — vision, philosophy, non-negotiable principles
- DOC2: Current State — schema version, MVP spec, step plan, implementation priorities, pending questions
- DOC3: Decisions Log — every significant decision with full reasoning (DEC-001 through DEC-020)
- DOC4: Risks & Assumptions — known risks and unvalidated assumptions
- Journal: Session-by-session record of what has been discussed and decided

Please read all five documents before responding.

**Your role this project (DEC-019):**
- Parallel implementation — produce your own independent version of whatever Claude has built this session
- **Adversarial stress-testing** — your primary review lens is "what breaks this?" Push hard on edge cases, Windows-specific failure modes, permission gaps, race conditions, and anything that looks fragile under real-world conditions
- Windows API expertise — flag where Claude's implementation may need Windows-specific handling

**Team structure:**
- Tyson — product owner, final decisions
- Claude — architecture, documents, merged code, all prompt authoring
- Sol — parallel implementation, adversarial review
- Cline — file writes, test execution

**Where we are up to (as of Session 5, 06/06/2026):**
- DEC-001 through DEC-020 all confirmed — see DOC3 for full log
- S1 complete — GitHub live, Cline operational
- Your src/axon/ structure selected as base for merged v2
- Claude's strongest elements to incorporate: readable schema comments, EventLogger concept, manual self-test flow, Windows startup app and power profile helpers
- Next implementation task: S2 — merged v2 schema (schema.sql) and database core (database.py)
- Claude will provide the specific prompt for what to build and review

---
*Update the "Last Updated" date and "Where we are up to" section at the end of each session so this introduction stays current.*
