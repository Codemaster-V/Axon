# AXON — Code Review

**Reviewer:** Claude
**Component:** Observation Engine + SQLite Schema
**Date:** 2026-05-18
**Reviewing:** axon_sol_observation_engine_dec016_src_layout.zip
**Scope Checked Against:** DEC-015 (Python MVP), DEC-016 (Folder Structure), DEC-017 (Review Format), MVP Safe Action Boundary (DEC-010), Schema V0.2 (DEC-009)

---

## SECTION 1 — SUMMARY

Sol's implementation is significantly more mature and production-ready than Claude's v1. Where Claude produced a single-file proof of concept, Sol produced a properly structured Python package with clean module separation, typed data models, a dedicated database layer, separate collectors, a CLI entry point, tests, and scripts. The schema is also more rigorous — better constraints, better indexing, better column naming, and the addition of a `schema_migration` tracking table that Claude missed entirely. Sol's approach correctly anticipated the `src/axon/` package structure she proposed in DEC-016 and built to it from the start. This implementation should be the structural base for the merged final version.

---

## SECTION 2 — WHAT WORKS WELL

**Package structure is exactly right.** Sol built to the agreed `src/axon/` layout with proper `__init__.py` files, clean imports, and a `core/` layer for shared infrastructure. This is immediately importable and testable as a proper Python package.

**Collectors are separated from the engine.** `collectors.py` handles data gathering; `observation_engine.py` handles orchestration. This separation makes it much easier to swap out or extend individual collectors (e.g. replacing the GPU stub with a real vendor API) without touching the engine logic.

**`hardware_fingerprint` is a smart addition.** Sol generates a SHA-256 hash of stable hardware identifiers to uniquely identify a device. Claude's v1 used device name only, which would break if the user renamed their machine. Sol's approach is more robust.

**Graceful degradation is built in properly.** The `safe()` wrapper in `collect_system_snapshot()` catches exceptions per-collector and records them in `collector_errors` without crashing the whole snapshot. Claude's v1 had try/except blocks but no systematic error recording.

**Schema constraints are much stronger.** Sol's schema uses `CHECK` constraints on enums (e.g. `goal_mode`, `status`, `risk_level`), integer range checks on tolerance scores (0–100), and `NOT NULL DEFAULT` patterns throughout. Claude's schema was more permissive and relied on application logic to enforce these rules.

**`schema_migration` table is a good addition.** Tracks which migrations have been applied. Claude missed this entirely. Important for when the schema evolves.

**Blocked capabilities are explicitly seeded.** Sol seeds blocked actions (registry modification, driver modification, overclocking) into `capability_registry` with `mvp_allowed = 0`. Claude only seeded the permitted ones. Sol's approach is more complete — the registry becomes a full record of what is and isn't allowed, not just what is.

**`requires_admin` and `requires_user_approval` fields on `capability_registry`.** Claude's registry didn't track these separately. Sol's addition makes the Decision Engine's job easier later.

**Tests are included.** Sol provided `test_schema.py`, `test_observation_engine.py`, and `test_event_logger.py`. Claude produced no tests in v1.

**`scripts/` folder with `init_db.py` and `smoke_test.py`.** Ready to run from day one. Claude didn't include setup scripts.

**`pyproject.toml` and `requirements.txt` included.** Claude produced neither. Sol's package is ready for proper Python packaging from the start.

---

## SECTION 3 — CONCERNS & SUGGESTED CHANGES

**Severity: Medium | GPU telemetry is a stub**
Sol's `collect_device_profile()` returns `gpu_summary_json: []` always, with a note that vendor APIs vary. Claude's v1 attempted WMI GPU access (though it was also fragile). Neither implementation has working GPU telemetry, but GPU performance is central to the gaming MVP. This needs to be addressed before the Observation Engine is considered complete for the gaming use case.
*Suggested fix:* Add a GPU collector using `GPUtil` (NVIDIA) with a graceful fallback for AMD/Intel. Document clearly which vendors are supported in MVP.

**Severity: Medium | Startup app enumeration is deferred**
Sol explicitly defers startup app enumeration with a placeholder note. Claude's v1 attempted it via registry query. Startup app management is a confirmed MVP action (DEC-010), so observation of startup apps is needed before the Action Engine can act on them.
*Suggested fix:* Adopt Claude's registry-based startup enumeration approach (with Sol's graceful degradation pattern wrapping it) so the Observation Engine can see startup apps from day one.

**Severity: Low | `observation_reason` field is good but not in Claude's schema**
Sol's `system_snapshot` table includes an `observation_reason` field (e.g. `'pre_action'`, `'scheduled_sample'`, `'baseline'`). This is important for the Learning Engine to know why a snapshot was taken. Claude's schema had `snapshot_type` which is equivalent but less descriptive. Sol's naming is better.

**Severity: Low | `raw_payload_json` column stores full snapshot twice**
Sol's `system_snapshot` stores the entire snapshot payload in `raw_payload_json` in addition to the broken-out JSON columns (`cpu_json`, `memory_json`, etc.). This causes data duplication. At MVP telemetry volumes it won't matter, but it's worth noting for when the data volume grows.
*Suggested fix:* Either keep `raw_payload_json` for debugging and document it as intentional duplication, or remove it and rely on the individual JSON columns.

**Severity: Low | `correlation_id` on `event_log` is a good addition**
Sol's `event_log` includes a `correlation_id` field for linking related events across a session. Claude's schema didn't include this. It's useful and should be kept.

**Severity: Low | `user_tolerance_profile` uses integer 0–100 scores**
Sol uses integers (0–100) for tolerance scores; Claude used floats (0.0–1.0). Both work, but integers are easier to display in a UI and less prone to floating point comparison issues. Sol's approach is slightly better for an MVP.

---

## SECTION 4 — RISKS OR GAPS SPOTTED

**GPU telemetry gap is the biggest risk.** Without GPU monitoring, the gaming optimiser cannot meaningfully observe the primary resource users care about. This needs to be resolved before the Observation Engine is handed to the Decision Engine.

**Startup app observation is missing.** The Decision Engine will need startup app data to generate startup-related recommendations. This should be added to the Observation Engine before moving on.

**No process CPU warm-up explanation for Tyson.** Sol's `collect_processes()` does a CPU warm-up sleep (`process_cpu_warmup_seconds`) before measuring CPU usage per process. This is technically correct (psutil needs an interval to measure CPU %) but adds latency to every snapshot. Worth documenting clearly so Tyson understands why snapshots aren't instant.

**`schema_migration` table needs a seeding step.** Sol inserts the migration record at schema creation time, which is correct. But there's no mechanism yet to handle future migrations (e.g. V0.3 schema changes). This is fine for MVP but should be noted in DOC4 as a future risk.

---

## SECTION 5 — TESTING / EVIDENCE

- **Was the code run?** No — Claude reviewed Sol's code statically. The test files were not executed in this review environment.
- **Environment tested in:** N/A (static review only)
- **Commands run:** None
- **Tests passed/failed:** Not run — review is structural and logical only
- **Runtime errors or warnings:** None identified from static review, though GPU and thermal collectors will silently return empty/None on machines where those APIs are unavailable, which is the correct behaviour.

---

## SECTION 6 — SCOPE COMPLIANCE

| Check | Status |
|---|---|
| Observation Engine only? | ✅ Yes — no optimisation actions executed |
| SQLite schema only? | ✅ Yes |
| No optimisation actions executed? | ✅ Confirmed |
| Safe action boundary respected? | ✅ Yes — blocked capabilities seeded correctly |
| Folder structure followed? | ✅ Yes — built to DEC-016 `src/axon/` layout |
| Clean Python importable filenames used? | ✅ Yes — `observation_engine.py`, `collectors.py`, `models.py`, `database.py` |
| Schema V0.2 entities all present? | ✅ All 9 entities confirmed |

---

## SECTION 7 — RECOMMENDED FINAL APPROACH

**Use Sol's implementation as the structural base.** Her package structure, database layer, collectors separation, schema constraints, and test infrastructure are all better than Claude's v1.

**Merge these specific elements from Claude's v1:**
- Startup app enumeration (registry-based, wrapped in Sol's graceful degradation pattern)
- GPU telemetry attempt via WMI/GPUtil with explicit vendor fallback documentation

**Add these to the merged version:**
- GPU collector using `GPUtil` with AMD/Intel fallback stubs
- Startup app collector using Windows registry query
- Document `process_cpu_warmup_seconds` latency clearly in code comments

**Schema:** Use Sol's schema as the base. It is more rigorous. Keep `schema_migration` table, `CHECK` constraints, `observation_reason` field, `correlation_id` on event log, `requires_admin` and `requires_user_approval` on capability_registry, and integer tolerance scores.

---

## SECTION 8 — OVERALL RATING

**Strengths:**
- Properly structured Python package from day one
- Clean module separation (collectors, engine, database, models)
- Rigorous schema with constraints and migration tracking
- Graceful degradation built in systematically
- Tests and setup scripts included
- Blocked capabilities explicitly seeded in registry
- Hardware fingerprint is more robust than device name alone

**Weaknesses:**
- GPU telemetry is a stub (significant gap for gaming MVP)
- Startup app enumeration deferred (needed for Action Engine)
- Minor data duplication in `raw_payload_json`

**Verdict: Adopt with changes**
Sol's v1 is the better structural foundation. Merge Claude's startup and GPU collector attempts into Sol's architecture, address the two medium severity gaps, and this becomes the agreed v1 Observation Engine for Axon.
