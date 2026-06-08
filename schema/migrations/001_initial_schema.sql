-- AXON — Initial SQLite Schema
-- Version: S2 merged v2
-- Target location: schema/migrations/001_initial_schema.sql
-- Scope: local-first SQLite schema for Axon's MVP database foundation.
--
-- Design notes:
--   - Defines all 9 confirmed Schema V0.2 entities.
--   - Uses TEXT UUID-style primary keys consistently.
--   - Stores key dashboard/query metrics as scalar columns and extended telemetry as JSON.
--   - JSON CHECK constraints are NULL-safe.
--   - event_log is append-only against application-level UPDATE/DELETE via triggers.
--   - capability_registry includes permitted and explicitly blocked MVP action classes.
--   - Capability seed data lives in this migration for S2 so assert_permitted() is usable now.
--     TODO(S4): move capability seed rows into schema/seeds/001_capability_registry.sql.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- -----------------------------------------------------------------------------
-- schema_migrations
-- Lightweight migration bookkeeping. This is not one of the 9 Axon domain
-- entities; it exists to avoid confusion as the schema evolves.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
);

INSERT OR IGNORE INTO schema_migrations (
    migration_id,
    applied_at,
    description
) VALUES (
    '001_initial_schema',
    '2026-06-07T00:00:00Z',
    'Initial Axon MVP schema: 9 entities, immutable event log, capability registry seed'
);

-- -----------------------------------------------------------------------------
-- 1. device_profile
-- Hardware/software fingerprint and capability map.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_profile (
    device_profile_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    hostname TEXT,
    os_platform TEXT,
    os_version TEXT,
    os_release TEXT,
    machine_architecture TEXT,
    cpu_model TEXT,
    cpu_physical_cores INTEGER CHECK (cpu_physical_cores IS NULL OR cpu_physical_cores >= 0),
    cpu_logical_cores INTEGER CHECK (cpu_logical_cores IS NULL OR cpu_logical_cores >= 0),
    cpu_base_freq_mhz REAL CHECK (cpu_base_freq_mhz IS NULL OR cpu_base_freq_mhz >= 0),
    ram_total_gb REAL CHECK (ram_total_gb IS NULL OR ram_total_gb >= 0),
    ram_total_bytes INTEGER CHECK (ram_total_bytes IS NULL OR ram_total_bytes >= 0),
    gpu_brand TEXT,
    gpu_model TEXT,
    gpu_vram_gb REAL CHECK (gpu_vram_gb IS NULL OR gpu_vram_gb >= 0),
    gpu_driver_version TEXT,
    storage_type TEXT,
    storage_total_gb REAL CHECK (storage_total_gb IS NULL OR storage_total_gb >= 0),
    supports_gpu_telemetry INTEGER NOT NULL DEFAULT 0 CHECK (supports_gpu_telemetry IN (0, 1)),
    supports_thermal_telemetry INTEGER NOT NULL DEFAULT 0 CHECK (supports_thermal_telemetry IN (0, 1)),
    gpu_summary_json TEXT CHECK (gpu_summary_json IS NULL OR json_valid(gpu_summary_json)),
    storage_summary_json TEXT CHECK (storage_summary_json IS NULL OR json_valid(storage_summary_json)),
    network_summary_json TEXT CHECK (network_summary_json IS NULL OR json_valid(network_summary_json)),
    capability_summary_json TEXT CHECK (capability_summary_json IS NULL OR json_valid(capability_summary_json)),
    raw_payload_json TEXT CHECK (raw_payload_json IS NULL OR json_valid(raw_payload_json))
);

CREATE INDEX IF NOT EXISTS idx_device_profile_created_at
ON device_profile(created_at);

CREATE INDEX IF NOT EXISTS idx_device_profile_hostname
ON device_profile(hostname);

-- -----------------------------------------------------------------------------
-- 2. system_snapshot
-- Point-in-time state. Used for observation, comparison, and pre-action baselines.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    device_profile_id TEXT,
    trigger_action_id TEXT,
    captured_at TEXT NOT NULL,
    snapshot_type TEXT NOT NULL DEFAULT 'observation'
        CHECK (snapshot_type IN ('observation', 'baseline', 'scheduled', 'pre_action', 'post_action', 'rollback', 'manual')),

    -- Key scalar telemetry for direct SQL queries, dashboards, and later simulation logic.
    cpu_usage_percent REAL CHECK (cpu_usage_percent IS NULL OR (cpu_usage_percent >= 0 AND cpu_usage_percent <= 100)),
    cpu_freq_mhz REAL CHECK (cpu_freq_mhz IS NULL OR cpu_freq_mhz >= 0),
    ram_used_gb REAL CHECK (ram_used_gb IS NULL OR ram_used_gb >= 0),
    ram_available_gb REAL CHECK (ram_available_gb IS NULL OR ram_available_gb >= 0),
    ram_usage_percent REAL CHECK (ram_usage_percent IS NULL OR (ram_usage_percent >= 0 AND ram_usage_percent <= 100)),
    gpu_usage_percent REAL CHECK (gpu_usage_percent IS NULL OR (gpu_usage_percent >= 0 AND gpu_usage_percent <= 100)),
    gpu_vram_used_gb REAL CHECK (gpu_vram_used_gb IS NULL OR gpu_vram_used_gb >= 0),
    gpu_temp_celsius REAL,
    cpu_temp_celsius REAL,
    storage_free_gb REAL CHECK (storage_free_gb IS NULL OR storage_free_gb >= 0),
    storage_used_gb REAL CHECK (storage_used_gb IS NULL OR storage_used_gb >= 0),
    power_profile TEXT,

    -- Extended/raw telemetry. These are not the source of truth for scalar fields above;
    -- they preserve richer platform-specific payloads and fallback details.
    active_processes_json TEXT CHECK (active_processes_json IS NULL OR json_valid(active_processes_json)),
    startup_apps_json TEXT CHECK (startup_apps_json IS NULL OR json_valid(startup_apps_json)),
    process_summary_json TEXT CHECK (process_summary_json IS NULL OR json_valid(process_summary_json)),
    disk_summary_json TEXT CHECK (disk_summary_json IS NULL OR json_valid(disk_summary_json)),
    gpu_summary_json TEXT CHECK (gpu_summary_json IS NULL OR json_valid(gpu_summary_json)),
    thermal_summary_json TEXT CHECK (thermal_summary_json IS NULL OR json_valid(thermal_summary_json)),
    raw_snapshot_json TEXT CHECK (raw_snapshot_json IS NULL OR json_valid(raw_snapshot_json)),

    FOREIGN KEY (device_profile_id) REFERENCES device_profile(device_profile_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (trigger_action_id) REFERENCES action_record(action_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_system_snapshot_captured_at
ON system_snapshot(captured_at);

CREATE INDEX IF NOT EXISTS idx_system_snapshot_device_profile
ON system_snapshot(device_profile_id);

CREATE INDEX IF NOT EXISTS idx_system_snapshot_type
ON system_snapshot(snapshot_type);

CREATE INDEX IF NOT EXISTS idx_system_snapshot_cpu_usage
ON system_snapshot(cpu_usage_percent);

CREATE INDEX IF NOT EXISTS idx_system_snapshot_gpu_temp
ON system_snapshot(gpu_temp_celsius);

-- -----------------------------------------------------------------------------
-- 3. event_log
-- Immutable event stream. This is Axon's local memory/audit layer.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_log (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    source_engine TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info'
        CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    related_entity_type TEXT,
    related_entity_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(payload_json)),
    schema_version TEXT NOT NULL DEFAULT '0.2',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_log_occurred_at
ON event_log(occurred_at);

CREATE INDEX IF NOT EXISTS idx_event_log_event_type
ON event_log(event_type);

CREATE INDEX IF NOT EXISTS idx_event_log_source_engine
ON event_log(source_engine);

CREATE INDEX IF NOT EXISTS idx_event_log_severity
ON event_log(severity);

CREATE INDEX IF NOT EXISTS idx_event_log_related_entity
ON event_log(related_entity_type, related_entity_id);

-- Enforce append-only behaviour against normal application-level UPDATE/DELETE.
-- This is not a tamper-proof audit store against a user with direct DB/file access.
CREATE TRIGGER IF NOT EXISTS trg_event_log_block_update
BEFORE UPDATE ON event_log
BEGIN
    SELECT RAISE(ABORT, 'event_log is append-only: UPDATE is not permitted');
END;

CREATE TRIGGER IF NOT EXISTS trg_event_log_block_delete
BEFORE DELETE ON event_log
BEGIN
    SELECT RAISE(ABORT, 'event_log is append-only: DELETE is not permitted');
END;

-- -----------------------------------------------------------------------------
-- 4. user_tolerance_profile
-- Optimisation personality; set during onboarding, refined later by learning.
-- Defined before goal_record so goal_record can link to the active profile.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_tolerance_profile (
    profile_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    profile_name TEXT NOT NULL DEFAULT 'default',
    performance_vs_stability REAL NOT NULL DEFAULT 0.5
        CHECK (performance_vs_stability >= 0.0 AND performance_vs_stability <= 1.0),
    noise_tolerance REAL NOT NULL DEFAULT 0.5
        CHECK (noise_tolerance >= 0.0 AND noise_tolerance <= 1.0),
    interruption_tolerance REAL NOT NULL DEFAULT 0.5
        CHECK (interruption_tolerance >= 0.0 AND interruption_tolerance <= 1.0),
    risk_tolerance TEXT NOT NULL DEFAULT 'conservative'
        CHECK (risk_tolerance IN ('conservative', 'moderate', 'aggressive')),
    visual_quality_tolerance REAL NOT NULL DEFAULT 0.5
        CHECK (visual_quality_tolerance >= 0.0 AND visual_quality_tolerance <= 1.0),
    autonomy_level TEXT NOT NULL DEFAULT 'approval_required'
        CHECK (autonomy_level IN ('approval_required', 'recommend_only', 'trusted_low_risk')),
    raw_preferences_json TEXT CHECK (raw_preferences_json IS NULL OR json_valid(raw_preferences_json)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_user_tolerance_active
ON user_tolerance_profile(is_active);

INSERT OR IGNORE INTO user_tolerance_profile (
    profile_id,
    created_at,
    updated_at,
    profile_name,
    performance_vs_stability,
    noise_tolerance,
    interruption_tolerance,
    risk_tolerance,
    visual_quality_tolerance,
    autonomy_level,
    raw_preferences_json,
    is_active
) VALUES (
    'default_tolerance_profile',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z',
    'default',
    0.5,
    0.5,
    0.5,
    'conservative',
    0.5,
    'approval_required',
    '{}',
    1
);

-- -----------------------------------------------------------------------------
-- 5. goal_record
-- Captures user intent and interpreted goal state.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS goal_record (
    goal_id TEXT PRIMARY KEY,
    tolerance_profile_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    goal_mode TEXT NOT NULL
        CHECK (goal_mode IN ('maximise_fps', 'quiet_mode', 'free_storage', 'balanced')),
    raw_user_intent TEXT,
    interpreted_goal_json TEXT CHECK (interpreted_goal_json IS NULL OR json_valid(interpreted_goal_json)),
    priority_json TEXT CHECK (priority_json IS NULL OR json_valid(priority_json)),
    acknowledged_tradeoffs_json TEXT CHECK (acknowledged_tradeoffs_json IS NULL OR json_valid(acknowledged_tradeoffs_json)),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'cancelled', 'superseded')),
    FOREIGN KEY (tolerance_profile_id) REFERENCES user_tolerance_profile(profile_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_goal_record_created_at
ON goal_record(created_at);

CREATE INDEX IF NOT EXISTS idx_goal_record_status
ON goal_record(status);

CREATE INDEX IF NOT EXISTS idx_goal_record_mode
ON goal_record(goal_mode);

CREATE INDEX IF NOT EXISTS idx_goal_record_tolerance_profile
ON goal_record(tolerance_profile_id);

-- -----------------------------------------------------------------------------
-- 6. capability_registry
-- Formal registry of what Axon may recommend/execute. Includes explicit blocks.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS capability_registry (
    capability_id TEXT PRIMARY KEY,
    capability_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    is_permitted_in_mvp INTEGER NOT NULL CHECK (is_permitted_in_mvp IN (0, 1)),
    blocked_reason TEXT,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    requires_admin INTEGER NOT NULL DEFAULT 0 CHECK (requires_admin IN (0, 1)),
    required_permissions_json TEXT CHECK (required_permissions_json IS NULL OR json_valid(required_permissions_json)),
    requires_gpu_telemetry INTEGER NOT NULL DEFAULT 0 CHECK (requires_gpu_telemetry IN (0, 1)),
    requires_thermal_data INTEGER NOT NULL DEFAULT 0 CHECK (requires_thermal_data IN (0, 1)),
    reversibility_class TEXT NOT NULL
        CHECK (reversibility_class IN (
            'toggle_reversal',
            'process_resume',
            'previous_value_restore',
            'temporary_expiry',
            'natural_rebuild',
            'recommendation_only',
            'not_reversible',
            'blocked'
        )),
    rollback_description TEXT NOT NULL,
    rollback_notes TEXT,
    permission_notes TEXT,
    safety_notes TEXT,
    implementation_status TEXT NOT NULL DEFAULT 'not_implemented'
        CHECK (implementation_status IN ('not_implemented', 'planned', 'implemented', 'blocked', 'deferred')),
    added_in_version TEXT NOT NULL DEFAULT '0.2',
    created_at TEXT NOT NULL,
    updated_at TEXT,
    CHECK (
        (is_permitted_in_mvp = 1 AND blocked_reason IS NULL)
        OR
        (is_permitted_in_mvp = 0 AND blocked_reason IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_capability_registry_key
ON capability_registry(capability_key);

CREATE INDEX IF NOT EXISTS idx_capability_registry_permitted
ON capability_registry(is_permitted_in_mvp);

CREATE INDEX IF NOT EXISTS idx_capability_registry_risk
ON capability_registry(risk_level);

-- Permitted MVP capabilities.
INSERT OR IGNORE INTO capability_registry (
    capability_id, capability_key, display_name, category, description,
    is_permitted_in_mvp, blocked_reason, risk_level, requires_admin,
    required_permissions_json, requires_gpu_telemetry, requires_thermal_data,
    reversibility_class, rollback_description, rollback_notes,
    permission_notes, safety_notes, implementation_status, added_in_version,
    created_at, updated_at
) VALUES
(
    'cap_startup_app_toggle',
    'startup_app_toggle',
    'Startup app toggle',
    'startup_management',
    'Enable or disable a non-critical startup application after explicit user approval.',
    1,
    NULL,
    'medium',
    0,
    '["read_startup_entries","write_user_startup_entries"]',
    0,
    0,
    'toggle_reversal',
    'Rollback restores the previous enabled/disabled startup state recorded before the action.',
    'Rollback depends on capturing the exact startup entry location and previous enabled state.',
    'May require user-level or admin access depending on startup location.',
    'MVP must use allowlists/blocklists and avoid security, driver, vendor updater, and unknown critical entries.',
    'planned',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_process_suspend',
    'process_suspend',
    'Process suspension',
    'process_management',
    'Temporarily suspend a curated safe background process after explicit user approval.',
    1,
    NULL,
    'medium',
    0,
    '["enumerate_processes","suspend_process","resume_process"]',
    0,
    0,
    'process_resume',
    'Rollback resumes the suspended process if it still exists and was suspended by Axon.',
    'If the process exits naturally, rollback becomes a no-op rather than a failure.',
    'Some processes may be protected or require elevation.',
    'Never suspend system-critical, security, anti-cheat, game, driver, or unknown processes in MVP.',
    'planned',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_power_profile_change',
    'power_profile_change',
    'Power profile change',
    'power_management',
    'Switch between supported Windows power profiles after explicit user approval.',
    1,
    NULL,
    'medium',
    0,
    '["read_power_profile","set_power_profile"]',
    0,
    0,
    'previous_value_restore',
    'Rollback restores the previous power profile recorded before the action.',
    'Do not create or modify custom power plan internals in MVP.',
    'Power profile commands vary by Windows version and permissions.',
    'Do not create custom power plans or permanently alter hidden power settings in MVP.',
    'planned',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_temporary_optimization_state',
    'temporary_optimization_state',
    'Temporary optimisation state',
    'temporary_state',
    'Apply a temporary Axon-controlled optimisation mode that expires or can be reverted.',
    1,
    NULL,
    'low',
    0,
    '["create_temporary_state","clear_temporary_state"]',
    0,
    0,
    'temporary_expiry',
    'Rollback cancels the temporary state or waits for natural expiry.',
    'Temporary states must have an expiry condition and clear user visibility.',
    'Should not rely on permanent OS configuration changes.',
    'Must be time-bounded and clearly visible to the user.',
    'planned',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_cache_cleanup',
    'cache_cleanup',
    'Cache cleanup',
    'storage_management',
    'Clean selected temporary/cache files after explicit user approval.',
    1,
    NULL,
    'medium',
    0,
    '["scan_temp_locations","delete_selected_cache_files"]',
    0,
    0,
    'natural_rebuild',
    'This is not true restoration: cleared caches are expected to rebuild naturally when applications need them.',
    'Rollback should never claim that deleted cache files are restored from Axon snapshots.',
    'May require permission to access selected folders.',
    'MVP must limit cleanup to clearly safe cache/temp locations and never delete personal files.',
    'planned',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_storage_cleanup_recommendation',
    'storage_cleanup_recommendation',
    'Storage cleanup recommendation',
    'storage_management',
    'Recommend storage cleanup opportunities without deleting files automatically.',
    1,
    NULL,
    'low',
    0,
    '["scan_storage_usage"]',
    0,
    0,
    'recommendation_only',
    'No rollback required because Axon only recommends; user performs or approves any actual cleanup separately.',
    'If a later action deletes files, that separate action must have its own capability and rollback classification.',
    'No elevated permission required for recommendation-only behaviour.',
    'Do not imply deletion has happened when only a recommendation was generated.',
    'planned',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
);

-- Explicitly blocked MVP capabilities.
INSERT OR IGNORE INTO capability_registry (
    capability_id, capability_key, display_name, category, description,
    is_permitted_in_mvp, blocked_reason, risk_level, requires_admin,
    required_permissions_json, requires_gpu_telemetry, requires_thermal_data,
    reversibility_class, rollback_description, rollback_notes,
    permission_notes, safety_notes, implementation_status, added_in_version,
    created_at, updated_at
) VALUES
(
    'cap_registry_modification_blocked',
    'registry_modification',
    'Registry modification',
    'blocked_system_change',
    'Modify Windows Registry keys or values.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["registry_write","admin_possible"]',
    0,
    0,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'Registry changes can be difficult to reverse safely and are out of scope.',
    'Often requires elevated permissions and can destabilise Windows or applications.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_driver_modification_blocked',
    'driver_modification',
    'Driver modification',
    'blocked_system_change',
    'Install, remove, update, disable, or alter device drivers.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["driver_management","admin_required"]',
    0,
    0,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'Driver operations can destabilise hardware, OS, games, anti-cheat, or security tooling.',
    'Requires elevated permissions and can cause device or OS instability.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_bios_firmware_interaction_blocked',
    'bios_firmware_interaction',
    'BIOS/firmware interaction',
    'blocked_system_change',
    'Read, write, modify, update, or control BIOS/UEFI/firmware settings.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["firmware_access","admin_required","vendor_specific_tooling"]',
    0,
    0,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'Firmware changes are outside Axon MVP trust and rollback boundaries.',
    'Firmware interaction is high-risk and vendor-specific.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_overclocking_blocked',
    'overclocking',
    'Overclocking',
    'blocked_performance_change',
    'Increase CPU/GPU/RAM clocks, power limits, or voltage-related performance limits.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["hardware_control","admin_possible","vendor_specific_tooling"]',
    1,
    1,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'Overclocking is specifically excluded from MVP to protect trust and hardware safety.',
    'Can cause crashes, overheating, warranty issues, or hardware instability.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_undervolting_blocked',
    'undervolting',
    'Undervolting',
    'blocked_performance_change',
    'Reduce CPU/GPU voltage or alter voltage curves.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["hardware_control","admin_possible","vendor_specific_tooling"]',
    1,
    1,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'Undervolting is vendor-specific and can cause instability despite appearing less risky than overclocking.',
    'Can cause instability and is vendor/tool specific.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_permanent_os_configuration_change_blocked',
    'permanent_os_configuration_change',
    'Permanent OS configuration change',
    'blocked_system_change',
    'Make persistent Windows configuration changes outside Axon-controlled reversible actions.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["system_configuration_write","admin_possible"]',
    0,
    0,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'MVP only permits tightly scoped app-controlled reversible changes.',
    'May have broad, unclear, or hard-to-reverse side effects.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
),
(
    'cap_security_policy_change_blocked',
    'security_policy_change',
    'Security policy change',
    'blocked_security_change',
    'Change firewall, antivirus, Defender, UAC, account, permissions, or security policy settings.',
    0,
    'Explicitly disallowed by MVP safe action boundary.',
    'critical',
    1,
    '["security_policy_write","admin_required"]',
    0,
    0,
    'blocked',
    'Blocked in MVP. No rollback is promised because the action must not be executed.',
    'Security policy changes would undermine trust and may create legal/support risk.',
    'Security changes create unacceptable trust and safety risk for MVP.',
    'Explicitly disallowed by MVP safe action boundary.',
    'blocked',
    '0.2',
    '2026-06-07T00:00:00Z',
    '2026-06-07T00:00:00Z'
);

-- -----------------------------------------------------------------------------
-- 7. recommendation_record
-- Split confidence scoring: effectiveness and safety are separate signals.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_record (
    recommendation_id TEXT PRIMARY KEY,
    goal_id TEXT,
    snapshot_id TEXT,
    capability_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    recommendation_type TEXT NOT NULL,
    target_resource TEXT,
    recommended_value TEXT,
    current_value TEXT,
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    what_will_change TEXT,
    what_wont_change TEXT,
    expected_benefit_text TEXT,
    expected_benefit_metric TEXT,
    expected_benefit_value REAL,
    expected_benefit_json TEXT CHECK (expected_benefit_json IS NULL OR json_valid(expected_benefit_json)),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    confidence_of_effectiveness REAL NOT NULL
        CHECK (confidence_of_effectiveness >= 0.0 AND confidence_of_effectiveness <= 1.0),
    confidence_of_safety REAL NOT NULL
        CHECK (confidence_of_safety >= 0.0 AND confidence_of_safety <= 1.0),
    reversibility_class TEXT NOT NULL
        CHECK (reversibility_class IN (
            'toggle_reversal',
            'process_resume',
            'previous_value_restore',
            'temporary_expiry',
            'natural_rebuild',
            'recommendation_only',
            'not_reversible',
            'blocked'
        )),
    rollback_description TEXT,
    simulation_run INTEGER NOT NULL DEFAULT 0 CHECK (simulation_run IN (0, 1)),
    simulation_result_json TEXT CHECK (simulation_result_json IS NULL OR json_valid(simulation_result_json)),
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'simulated', 'approved', 'declined', 'deferred', 'executed', 'superseded', 'failed')),
    decided_at TEXT,
    FOREIGN KEY (goal_id) REFERENCES goal_record(goal_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (snapshot_id) REFERENCES system_snapshot(snapshot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (capability_id) REFERENCES capability_registry(capability_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_recommendation_goal
ON recommendation_record(goal_id);

CREATE INDEX IF NOT EXISTS idx_recommendation_capability
ON recommendation_record(capability_id);

CREATE INDEX IF NOT EXISTS idx_recommendation_status
ON recommendation_record(status);

CREATE INDEX IF NOT EXISTS idx_recommendation_decided_at
ON recommendation_record(decided_at);

-- -----------------------------------------------------------------------------
-- 8. action_record
-- Links approved recommendations to execution, rollback data, and outcomes.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS action_record (
    action_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    pre_action_snapshot_id TEXT,
    approved_at TEXT,
    executed_at TEXT,
    completed_at TEXT,
    action_status TEXT NOT NULL DEFAULT 'created'
        CHECK (action_status IN ('created', 'approved', 'executing', 'succeeded', 'failed', 'rolled_back', 'rollback_failed', 'cancelled')),
    execution_payload_json TEXT CHECK (execution_payload_json IS NULL OR json_valid(execution_payload_json)),
    rollback_payload_json TEXT CHECK (rollback_payload_json IS NULL OR json_valid(rollback_payload_json)),
    result_payload_json TEXT CHECK (result_payload_json IS NULL OR json_valid(result_payload_json)),
    error_message TEXT,
    FOREIGN KEY (recommendation_id) REFERENCES recommendation_record(recommendation_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (capability_id) REFERENCES capability_registry(capability_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (pre_action_snapshot_id) REFERENCES system_snapshot(snapshot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_action_recommendation
ON action_record(recommendation_id);

CREATE INDEX IF NOT EXISTS idx_action_status
ON action_record(action_status);

CREATE INDEX IF NOT EXISTS idx_action_capability
ON action_record(capability_id);

CREATE INDEX IF NOT EXISTS idx_action_pre_snapshot
ON action_record(pre_action_snapshot_id);

-- -----------------------------------------------------------------------------
-- 9. outcome_record
-- Captures measured results plus environmental context to avoid false attribution.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outcome_record (
    outcome_id TEXT PRIMARY KEY,
    action_id TEXT,
    recommendation_id TEXT,
    created_at TEXT NOT NULL,
    measurement_window_seconds INTEGER CHECK (measurement_window_seconds IS NULL OR measurement_window_seconds >= 0),
    baseline_snapshot_id TEXT,
    post_action_snapshot_id TEXT,
    outcome_summary_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(outcome_summary_json)),
    environmental_context_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(environmental_context_json)),
    cpu_usage_before REAL,
    cpu_usage_after REAL,
    ram_usage_before REAL,
    ram_usage_after REAL,
    gpu_usage_before REAL,
    gpu_usage_after REAL,
    fps_before REAL,
    fps_after REAL,
    storage_freed_gb REAL,
    effectiveness_score REAL CHECK (effectiveness_score IS NULL OR (effectiveness_score >= -1.0 AND effectiveness_score <= 1.0)),
    safety_score REAL CHECK (safety_score IS NULL OR (safety_score IS NULL OR (safety_score >= 0.0 AND safety_score <= 1.0))),
    notes TEXT,
    FOREIGN KEY (action_id) REFERENCES action_record(action_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (recommendation_id) REFERENCES recommendation_record(recommendation_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (baseline_snapshot_id) REFERENCES system_snapshot(snapshot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (post_action_snapshot_id) REFERENCES system_snapshot(snapshot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_outcome_action
ON outcome_record(action_id);

CREATE INDEX IF NOT EXISTS idx_outcome_recommendation
ON outcome_record(recommendation_id);

CREATE INDEX IF NOT EXISTS idx_outcome_created_at
ON outcome_record(created_at);
