-- ============================================================
-- AXON — SQLite Database Schema
-- Version: 0.2
-- Created: 2026-05-18
-- ============================================================
-- This schema implements all 9 confirmed entities from
-- the Axon Data Architecture V0.2.
--
-- Design principles:
--   - Event-driven: events are stored, not just state
--   - Local-first: no cloud dependency
--   - Clean separation so a C# layer can wrap this later
--   - All tables include created_at timestamps
-- ============================================================

PRAGMA journal_mode=WAL;  -- Better concurrent read performance
PRAGMA foreign_keys=ON;   -- Enforce relationships

-- ============================================================
-- 1. DEVICE PROFILE
-- Hardware fingerprint and capability map.
-- One row per device. Updated if hardware changes.
-- ============================================================
CREATE TABLE IF NOT EXISTS device_profile (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name         TEXT NOT NULL,
    os_version          TEXT NOT NULL,
    cpu_name            TEXT NOT NULL,
    cpu_cores_physical  INTEGER NOT NULL,
    cpu_cores_logical   INTEGER NOT NULL,
    cpu_base_clock_mhz  REAL,
    ram_total_gb        REAL NOT NULL,
    gpu_name            TEXT,
    gpu_vram_gb         REAL,
    storage_drives      TEXT,           -- JSON array of drives
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- 2. SYSTEM SNAPSHOT
-- Point-in-time state capture. Foundation for rollback.
-- Taken before any action is executed.
-- ============================================================
CREATE TABLE IF NOT EXISTS system_snapshot (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_type       TEXT NOT NULL,  -- 'pre_action', 'scheduled', 'baseline'
    cpu_usage_pct       REAL,
    ram_usage_pct       REAL,
    ram_used_gb         REAL,
    gpu_usage_pct       REAL,
    gpu_vram_used_gb    REAL,
    cpu_temp_c          REAL,
    gpu_temp_c          REAL,
    active_processes    TEXT,           -- JSON array of running processes
    startup_apps        TEXT,           -- JSON array of startup entries
    power_profile       TEXT,           -- e.g. 'balanced', 'high_performance'
    storage_free_gb     REAL,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- 3. EVENT LOG
-- Immutable. Flexible JSON payload. System memory layer.
-- Nothing is ever deleted from this table.
-- ============================================================
CREATE TABLE IF NOT EXISTS event_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type          TEXT NOT NULL,  -- e.g. 'goal_created', 'action_executed',
                                        --       'rollback_triggered', 'snapshot_taken',
                                        --       'recommendation_generated', 'preference_updated'
    source              TEXT NOT NULL,  -- 'observation_engine', 'goal_engine',
                                        --   'decision_engine', 'action_engine', 'learning_engine'
    payload             TEXT,           -- JSON blob: flexible per event type
    related_goal_id     INTEGER,        -- Optional link to goal_record
    related_action_id   INTEGER,        -- Optional link to action_record
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- 4. GOAL RECORD
-- Captures user intent and interpreted goal.
-- ============================================================
CREATE TABLE IF NOT EXISTS goal_record (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_mode           TEXT NOT NULL,  -- 'maximise_fps', 'quiet_mode',
                                        --   'free_storage', 'balanced'
    user_input          TEXT,           -- Reserved for future free-text input (Phase 2)
    interpreted_goal    TEXT NOT NULL,  -- Human-readable interpretation
    priority_context    TEXT,           -- JSON: what the user cares about most
    status              TEXT NOT NULL DEFAULT 'active',  -- 'active', 'completed', 'cancelled'
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at        TEXT
);

-- ============================================================
-- 5. CAPABILITY REGISTRY
-- Formal registry of permitted actions, permissions,
-- risk classifications, and rollback methods.
-- This is checked before any recommendation is generated.
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_registry (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_name         TEXT NOT NULL UNIQUE,
    description             TEXT NOT NULL,
    category                TEXT NOT NULL,  -- 'startup', 'process', 'power',
                                            --   'cache', 'storage'
    permission_required     TEXT,           -- Windows permission level needed
    risk_level              TEXT NOT NULL,  -- 'low', 'medium', 'high'
    is_permitted_in_mvp     INTEGER NOT NULL DEFAULT 1,  -- 0 = blocked in MVP
    rollback_method         TEXT NOT NULL,  -- How to reverse this action
    rollback_reliable       INTEGER NOT NULL DEFAULT 1,  -- 1 = confirmed reversible
    notes                   TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Seed the capability registry with MVP-permitted actions
INSERT OR IGNORE INTO capability_registry
    (capability_name, description, category, risk_level, is_permitted_in_mvp, rollback_method, rollback_reliable)
VALUES
    ('toggle_startup_app',      'Enable or disable a startup application',         'startup', 'low',    1, 'Re-enable the startup entry via registry/task manager equivalent', 1),
    ('suspend_process',         'Temporarily suspend a background process',         'process', 'medium', 1, 'Resume the suspended process',                                    1),
    ('change_power_profile',    'Switch Windows power plan',                        'power',   'low',    1, 'Restore previous power plan by name',                             1),
    ('clear_cache',             'Clear temporary files and system cache',           'cache',   'low',    1, 'Cache is rebuilt automatically; no rollback needed',               1),
    ('storage_cleanup_suggest', 'Recommend files for deletion (no auto-delete)',    'storage', 'low',    1, 'User-initiated only; no automated action taken',                  1);

-- ============================================================
-- 6. RECOMMENDATION RECORD
-- Decision Engine output. V0.2: split confidence scores.
-- ============================================================
CREATE TABLE IF NOT EXISTS recommendation_record (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id                     INTEGER NOT NULL REFERENCES goal_record(id),
    capability_id               INTEGER NOT NULL REFERENCES capability_registry(id),
    snapshot_id                 INTEGER REFERENCES system_snapshot(id),
    title                       TEXT NOT NULL,
    explanation                 TEXT NOT NULL,      -- Why this was recommended
    expected_benefit            TEXT NOT NULL,      -- Human-readable expected outcome
    confidence_effectiveness    REAL NOT NULL,      -- 0.0–1.0: will this help?
    confidence_safety           REAL NOT NULL,      -- 0.0–1.0: is this safe?
    risk_level                  TEXT NOT NULL,      -- 'low', 'medium', 'high'
    is_reversible               INTEGER NOT NULL DEFAULT 1,
    simulation_summary          TEXT,               -- What Simulation Mode would show
    status                      TEXT NOT NULL DEFAULT 'pending',
                                                    -- 'pending', 'approved', 'declined',
                                                    --   'executed', 'rolled_back'
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    actioned_at                 TEXT
);

-- ============================================================
-- 7. ACTION RECORD
-- Links recommendations to execution and outcome.
-- ============================================================
CREATE TABLE IF NOT EXISTS action_record (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id       INTEGER NOT NULL REFERENCES recommendation_record(id),
    pre_action_snapshot_id  INTEGER NOT NULL REFERENCES system_snapshot(id),
    capability_id           INTEGER NOT NULL REFERENCES capability_registry(id),
    action_parameters       TEXT,           -- JSON: specific parameters used
    execution_status        TEXT NOT NULL,  -- 'success', 'failed', 'rolled_back'
    execution_notes         TEXT,
    executed_at             TEXT NOT NULL DEFAULT (datetime('now')),
    rolled_back_at          TEXT
);

-- ============================================================
-- 8. OUTCOME RECORD
-- V0.2: includes environmental_context block.
-- Prevents Learning Engine from drawing wrong conclusions.
-- ============================================================
CREATE TABLE IF NOT EXISTS outcome_record (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id               INTEGER NOT NULL REFERENCES action_record(id),
    goal_id                 INTEGER NOT NULL REFERENCES goal_record(id),
    measurement_type        TEXT NOT NULL,  -- 'fps', 'ram_freed_gb', 'boot_time_ms',
                                            --   'cpu_temp_reduction', 'storage_freed_gb'
    value_before            REAL,
    value_after             REAL,
    improvement_pct         REAL,
    user_rating             INTEGER,        -- Optional: 1–5 user satisfaction
    user_feedback           TEXT,
    environmental_context   TEXT NOT NULL,  -- JSON: what else was happening
                                            -- e.g. {"other_apps_running": [...],
                                            --        "cpu_temp_at_action": 78,
                                            --        "time_of_day": "evening"}
    observation_window_sec  INTEGER,        -- How long we observed before recording
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- 9. USER TOLERANCE PROFILE
-- Optimisation personality. Set at onboarding.
-- Refined by Learning Engine over time (Phase 2).
-- ============================================================
CREATE TABLE IF NOT EXISTS user_tolerance_profile (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    performance_vs_stability    REAL NOT NULL DEFAULT 0.5,  -- 0=stability, 1=performance
    noise_tolerance             REAL NOT NULL DEFAULT 0.5,  -- 0=silent, 1=don't care
    interruption_tolerance      REAL NOT NULL DEFAULT 0.5,  -- 0=never interrupt, 1=always ok
    risk_tolerance              TEXT NOT NULL DEFAULT 'moderate',  -- 'conservative','moderate','aggressive'
    visual_quality_tolerance    REAL NOT NULL DEFAULT 0.5,  -- 0=quality matters, 1=don't care
    autonomy_preference         TEXT NOT NULL DEFAULT 'approval_required',
                                                            -- 'approval_required', 'notify_only',
                                                            --   'fully_autonomous' (Phase 2+)
    onboarding_complete         INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- INDEXES — for common query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_event_log_type       ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_created    ON event_log(created_at);
CREATE INDEX IF NOT EXISTS idx_recommendation_goal  ON recommendation_record(goal_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_status ON recommendation_record(status);
CREATE INDEX IF NOT EXISTS idx_action_recommendation ON action_record(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_outcome_action       ON outcome_record(action_id);
CREATE INDEX IF NOT EXISTS idx_outcome_goal         ON outcome_record(goal_id);

-- ============================================================
-- END OF SCHEMA
-- ============================================================
