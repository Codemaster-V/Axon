"""Axon SQLite database core.

Version: S2 merged v2
Target location: src/axon/core/database.py

Responsibilities:
- Resolve Axon project paths without fixed parent-depth assumptions.
- Manage SQLite connections with WAL mode, busy timeout, and foreign keys enabled.
- Run the initial schema migration idempotently.
- Provide append-only event logging.
- Provide snapshot persistence and lookup helpers.
- Provide capability registry access with assert_permitted() as the MVP hard gate.

This module deliberately does not execute optimisation actions. It only provides
storage and safety-gate foundations for later engines.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

JsonMapping = Mapping[str, Any]

SCHEMA_RELATIVE_PATH = Path("schema") / "migrations" / "001_initial_schema.sql"
DEFAULT_DB_RELATIVE_PATH = Path("data") / "axon.sqlite3"


# =============================================================================
# Exceptions
# =============================================================================


class AxonDatabaseError(RuntimeError):
    """Base database-layer error for Axon."""


class CapabilityNotFoundError(AxonDatabaseError):
    """Raised when a capability key is not present in the capability registry."""


class CapabilityNotPermittedError(AxonDatabaseError):
    """Raised when code tries to use a capability blocked from the MVP."""


class EventLogMutationError(AxonDatabaseError):
    """Raised when event_log immutability does not behave as expected."""


# =============================================================================
# Data objects
# =============================================================================


@dataclass(frozen=True)
class Capability:
    """A capability_registry row exposed as a typed object."""

    capability_id: str
    capability_key: str
    display_name: str
    category: str
    description: str
    is_permitted_in_mvp: bool
    blocked_reason: Optional[str]
    risk_level: str
    requires_admin: bool
    required_permissions: list[str]
    requires_gpu_telemetry: bool
    requires_thermal_data: bool
    reversibility_class: str
    rollback_description: str
    rollback_notes: Optional[str]
    permission_notes: Optional[str]
    safety_notes: Optional[str]
    implementation_status: str
    added_in_version: str


# =============================================================================
# Utility functions
# =============================================================================


def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp with a trailing Z."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Create a readable stable ID suitable for SQLite TEXT primary keys."""

    safe_prefix = prefix.strip().lower().replace(" ", "_")
    return f"{safe_prefix}_{uuid.uuid4().hex}"


def json_dumps(value: Any) -> str:
    """Serialize JSON consistently for storage in TEXT columns."""

    if value is None:
        value = {}
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def json_loads_object(value: Optional[str]) -> dict[str, Any]:
    """Load a JSON object from a SQLite TEXT value, returning {} for blanks."""

    if not value:
        return {}
    loaded = json.loads(value)
    if isinstance(loaded, dict):
        return loaded
    return {"value": loaded}


def json_loads_list(value: Optional[str]) -> list[str]:
    """Load a JSON list of strings from a SQLite TEXT value."""

    if not value:
        return []
    loaded = json.loads(value)
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def find_project_root(start: Optional[Path] = None) -> Path:
    """Find the Axon project root by walking upward until the schema file is found.

    This avoids hard-coding assumptions such as Path(__file__).parents[3]. It works
    from different run contexts as long as the DEC-016 project structure is present
    somewhere above this file or the supplied start path.
    """

    start_path = (start or Path(__file__)).resolve()
    search_start = start_path if start_path.is_dir() else start_path.parent

    for candidate in (search_start, *search_start.parents):
        if (candidate / SCHEMA_RELATIVE_PATH).exists():
            return candidate

    raise FileNotFoundError(
        f"Could not locate Axon project root. Expected to find {SCHEMA_RELATIVE_PATH} "
        f"above {search_start}."
    )


# =============================================================================
# Database connection and migration management
# =============================================================================


class Database:
    """Small SQLite database wrapper for Axon's local-first MVP storage."""

    def __init__(self, db_path: Optional[Path | str] = None, project_root: Optional[Path | str] = None) -> None:
        self.project_root = Path(project_root).resolve() if project_root else find_project_root()
        self.db_path = Path(db_path).resolve() if db_path else (self.project_root / DEFAULT_DB_RELATIVE_PATH)
        self.schema_path = self.project_root / SCHEMA_RELATIVE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with required safety/performance pragmas.

        Foreign keys are disabled by default in SQLite, so this must be done on
        every connection. WAL is also asserted here even though the migration file
        includes a PRAGMA for clarity.
        """

        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row

        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")

        fk_state = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        if fk_state != 1:
            conn.close()
            raise AxonDatabaseError("SQLite foreign key enforcement could not be enabled.")

        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager that commits on success and rolls back on error."""

        conn = self.connect()
        try:
            conn.execute("BEGIN;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Run the initial schema migration idempotently.

        The migration uses CREATE TABLE IF NOT EXISTS and INSERT OR IGNORE, so it
        can safely run on every startup during MVP development rather than only
        when the database file is new.
        """

        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")

        sql = self.schema_path.read_text(encoding="utf-8")
        conn = self.connect()
        try:
            conn.executescript(sql)
        finally:
            conn.close()

    def table_names(self) -> list[str]:
        """Return user table names for smoke tests and diagnostics."""

        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name;
                """
            ).fetchall()
        return [row["name"] for row in rows]

    def verify_event_log_is_immutable(self) -> None:
        """Smoke-check that UPDATE/DELETE on event_log are blocked by triggers.

        This is intentionally destructive only to a temporary test event created by
        this method. The UPDATE and DELETE attempts should fail, leaving the test
        event in the append-only log as evidence of the check.
        """

        logger = EventLogger(self)
        event_id = logger.log_event(
            source_engine="database",
            event_type="database_integrity_check",
            severity="debug",
            payload={"purpose": "verify event_log triggers block update/delete"},
        )

        with self.connection() as conn:
            try:
                conn.execute(
                    "UPDATE event_log SET event_type = ? WHERE event_id = ?;",
                    ("mutation_should_fail", event_id),
                )
            except sqlite3.DatabaseError as exc:
                if "append-only" not in str(exc):
                    raise EventLogMutationError(f"Unexpected UPDATE failure: {exc}") from exc
            else:
                raise EventLogMutationError("event_log UPDATE unexpectedly succeeded.")

        with self.connection() as conn:
            try:
                conn.execute("DELETE FROM event_log WHERE event_id = ?;", (event_id,))
            except sqlite3.DatabaseError as exc:
                if "append-only" not in str(exc):
                    raise EventLogMutationError(f"Unexpected DELETE failure: {exc}") from exc
            else:
                raise EventLogMutationError("event_log DELETE unexpectedly succeeded.")


# =============================================================================
# Event log
# =============================================================================


class EventLogger:
    """Append-only event logger.

    This class intentionally exposes no update/delete methods. Database triggers
    enforce append-only behaviour even if a future caller tries to mutate event_log
    directly through normal SQL UPDATE/DELETE statements.
    """

    VALID_SEVERITIES = {"debug", "info", "warning", "error", "critical"}

    def __init__(self, database: Database) -> None:
        self.database = database

    def log_event(
        self,
        *,
        source_engine: str,
        event_type: str,
        payload: Optional[JsonMapping] = None,
        severity: str = "info",
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
    ) -> str:
        if not source_engine:
            raise ValueError("source_engine is required")
        if not event_type:
            raise ValueError("event_type is required")
        if severity not in self.VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")

        event_id = new_id("event")
        now = utc_now()
        payload_json = json_dumps(payload or {})

        with self.database.connection() as conn:
            conn.execute(
                """
                INSERT INTO event_log (
                    event_id,
                    occurred_at,
                    source_engine,
                    event_type,
                    severity,
                    related_entity_type,
                    related_entity_id,
                    payload_json,
                    schema_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event_id,
                    now,
                    source_engine,
                    event_type,
                    severity,
                    related_entity_type,
                    related_entity_id,
                    payload_json,
                    "0.2",
                    now,
                ),
            )

        return event_id

    def get_recent(self, *, limit: int = 50, severity: Optional[str] = None) -> list[sqlite3.Row]:
        """Return recent events, optionally filtered by severity."""

        if limit <= 0:
            raise ValueError("limit must be positive")

        with self.database.connection() as conn:
            if severity is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM event_log
                    WHERE severity = ?
                    ORDER BY occurred_at DESC
                    LIMIT ?;
                    """,
                    (severity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM event_log
                    ORDER BY occurred_at DESC
                    LIMIT ?;
                    """,
                    (limit,),
                ).fetchall()
        return rows

    def get_errors(self, *, limit: int = 20) -> list[sqlite3.Row]:
        """Return recent error and critical events."""

        if limit <= 0:
            raise ValueError("limit must be positive")

        with self.database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM event_log
                WHERE severity IN ('error', 'critical')
                ORDER BY occurred_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        return rows

    def get_for_entity(self, *, entity_type: str, entity_id: str) -> list[sqlite3.Row]:
        """Return all events related to a specific entity."""

        with self.database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM event_log
                WHERE related_entity_type = ?
                  AND related_entity_id = ?
                ORDER BY occurred_at ASC;
                """,
                (entity_type, entity_id),
            ).fetchall()
        return rows


# =============================================================================
# Snapshot management
# =============================================================================


class SnapshotManager:
    """Persistence helper for device profiles and system snapshots."""

    def __init__(self, database: Database, event_logger: Optional[EventLogger] = None) -> None:
        self.database = database
        self.event_logger = event_logger or EventLogger(database)

    def create_device_profile(
        self,
        *,
        hostname: Optional[str] = None,
        os_platform: Optional[str] = None,
        os_version: Optional[str] = None,
        os_release: Optional[str] = None,
        machine_architecture: Optional[str] = None,
        cpu_model: Optional[str] = None,
        cpu_physical_cores: Optional[int] = None,
        cpu_logical_cores: Optional[int] = None,
        cpu_base_freq_mhz: Optional[float] = None,
        ram_total_gb: Optional[float] = None,
        ram_total_bytes: Optional[int] = None,
        gpu_brand: Optional[str] = None,
        gpu_model: Optional[str] = None,
        gpu_vram_gb: Optional[float] = None,
        gpu_driver_version: Optional[str] = None,
        storage_type: Optional[str] = None,
        storage_total_gb: Optional[float] = None,
        supports_gpu_telemetry: bool = False,
        supports_thermal_telemetry: bool = False,
        gpu_summary: Optional[JsonMapping] = None,
        storage_summary: Optional[JsonMapping] = None,
        network_summary: Optional[JsonMapping] = None,
        capability_summary: Optional[JsonMapping] = None,
        raw_payload: Optional[JsonMapping] = None,
    ) -> str:
        """Create and log a device_profile row."""

        profile_id = new_id("device")
        now = utc_now()

        with self.database.connection() as conn:
            conn.execute(
                """
                INSERT INTO device_profile (
                    device_profile_id,
                    created_at,
                    hostname,
                    os_platform,
                    os_version,
                    os_release,
                    machine_architecture,
                    cpu_model,
                    cpu_physical_cores,
                    cpu_logical_cores,
                    cpu_base_freq_mhz,
                    ram_total_gb,
                    ram_total_bytes,
                    gpu_brand,
                    gpu_model,
                    gpu_vram_gb,
                    gpu_driver_version,
                    storage_type,
                    storage_total_gb,
                    supports_gpu_telemetry,
                    supports_thermal_telemetry,
                    gpu_summary_json,
                    storage_summary_json,
                    network_summary_json,
                    capability_summary_json,
                    raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    profile_id,
                    now,
                    hostname,
                    os_platform,
                    os_version,
                    os_release,
                    machine_architecture,
                    cpu_model,
                    cpu_physical_cores,
                    cpu_logical_cores,
                    cpu_base_freq_mhz,
                    ram_total_gb,
                    ram_total_bytes,
                    gpu_brand,
                    gpu_model,
                    gpu_vram_gb,
                    gpu_driver_version,
                    storage_type,
                    storage_total_gb,
                    1 if supports_gpu_telemetry else 0,
                    1 if supports_thermal_telemetry else 0,
                    json_dumps(gpu_summary or {}),
                    json_dumps(storage_summary or {}),
                    json_dumps(network_summary or {}),
                    json_dumps(capability_summary or {}),
                    json_dumps(raw_payload or {}),
                ),
            )

        self.event_logger.log_event(
            source_engine="observation_engine",
            event_type="device_profile_created",
            related_entity_type="device_profile",
            related_entity_id=profile_id,
            payload={"device_profile_id": profile_id},
        )
        return profile_id

    def create_system_snapshot(
        self,
        *,
        device_profile_id: Optional[str] = None,
        trigger_action_id: Optional[str] = None,
        snapshot_type: str = "observation",
        cpu_usage_percent: Optional[float] = None,
        cpu_freq_mhz: Optional[float] = None,
        ram_used_gb: Optional[float] = None,
        ram_available_gb: Optional[float] = None,
        ram_usage_percent: Optional[float] = None,
        gpu_usage_percent: Optional[float] = None,
        gpu_vram_used_gb: Optional[float] = None,
        gpu_temp_celsius: Optional[float] = None,
        cpu_temp_celsius: Optional[float] = None,
        storage_free_gb: Optional[float] = None,
        storage_used_gb: Optional[float] = None,
        power_profile: Optional[str] = None,
        active_processes: Optional[Any] = None,
        startup_apps: Optional[Any] = None,
        process_summary: Optional[JsonMapping] = None,
        disk_summary: Optional[JsonMapping] = None,
        gpu_summary: Optional[JsonMapping] = None,
        thermal_summary: Optional[JsonMapping] = None,
        raw_snapshot: Optional[JsonMapping] = None,
    ) -> str:
        """Create and log a system_snapshot row.

        The method uses a fixed INSERT shape so partial or minimal snapshots cannot
        generate invalid SQL.
        """

        snapshot_id = new_id("snapshot")
        now = utc_now()

        with self.database.connection() as conn:
            conn.execute(
                """
                INSERT INTO system_snapshot (
                    snapshot_id,
                    device_profile_id,
                    trigger_action_id,
                    captured_at,
                    snapshot_type,
                    cpu_usage_percent,
                    cpu_freq_mhz,
                    ram_used_gb,
                    ram_available_gb,
                    ram_usage_percent,
                    gpu_usage_percent,
                    gpu_vram_used_gb,
                    gpu_temp_celsius,
                    cpu_temp_celsius,
                    storage_free_gb,
                    storage_used_gb,
                    power_profile,
                    active_processes_json,
                    startup_apps_json,
                    process_summary_json,
                    disk_summary_json,
                    gpu_summary_json,
                    thermal_summary_json,
                    raw_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    snapshot_id,
                    device_profile_id,
                    trigger_action_id,
                    now,
                    snapshot_type,
                    cpu_usage_percent,
                    cpu_freq_mhz,
                    ram_used_gb,
                    ram_available_gb,
                    ram_usage_percent,
                    gpu_usage_percent,
                    gpu_vram_used_gb,
                    gpu_temp_celsius,
                    cpu_temp_celsius,
                    storage_free_gb,
                    storage_used_gb,
                    power_profile,
                    json_dumps(active_processes or []),
                    json_dumps(startup_apps or []),
                    json_dumps(process_summary or {}),
                    json_dumps(disk_summary or {}),
                    json_dumps(gpu_summary or {}),
                    json_dumps(thermal_summary or {}),
                    json_dumps(raw_snapshot or {}),
                ),
            )

        self.event_logger.log_event(
            source_engine="observation_engine",
            event_type="system_snapshot_created",
            related_entity_type="system_snapshot",
            related_entity_id=snapshot_id,
            payload={
                "snapshot_id": snapshot_id,
                "snapshot_type": snapshot_type,
                "device_profile_id": device_profile_id,
                "trigger_action_id": trigger_action_id,
            },
        )
        return snapshot_id

    def get(self, snapshot_id: str) -> Optional[sqlite3.Row]:
        """Return one system snapshot by ID."""

        with self.database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM system_snapshot WHERE snapshot_id = ?;",
                (snapshot_id,),
            ).fetchone()
        return row

    def get_latest_baseline(self) -> Optional[sqlite3.Row]:
        """Return the most recent baseline snapshot."""

        with self.database.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM system_snapshot
                WHERE snapshot_type = 'baseline'
                ORDER BY captured_at DESC
                LIMIT 1;
                """
            ).fetchone()
        return row

    def get_pre_action_snapshot(self, action_id: str) -> Optional[sqlite3.Row]:
        """Return the pre-action snapshot linked to an action."""

        with self.database.connection() as conn:
            row = conn.execute(
                """
                SELECT s.*
                FROM system_snapshot s
                JOIN action_record a ON a.pre_action_snapshot_id = s.snapshot_id
                WHERE a.action_id = ?;
                """,
                (action_id,),
            ).fetchone()
        return row


# =============================================================================
# Capability registry
# =============================================================================


class CapabilityRegistry:
    """Read and enforce Axon's capability registry.

    The hard gate is assert_permitted(). Future recommendation/action code should
    call it before simulating, recommending, or executing any capability.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def _row_to_capability(self, row: sqlite3.Row) -> Capability:
        return Capability(
            capability_id=row["capability_id"],
            capability_key=row["capability_key"],
            display_name=row["display_name"],
            category=row["category"],
            description=row["description"],
            is_permitted_in_mvp=bool(row["is_permitted_in_mvp"]),
            blocked_reason=row["blocked_reason"],
            risk_level=row["risk_level"],
            requires_admin=bool(row["requires_admin"]),
            required_permissions=json_loads_list(row["required_permissions_json"]),
            requires_gpu_telemetry=bool(row["requires_gpu_telemetry"]),
            requires_thermal_data=bool(row["requires_thermal_data"]),
            reversibility_class=row["reversibility_class"],
            rollback_description=row["rollback_description"],
            rollback_notes=row["rollback_notes"],
            permission_notes=row["permission_notes"],
            safety_notes=row["safety_notes"],
            implementation_status=row["implementation_status"],
            added_in_version=row["added_in_version"],
        )

    def get(self, capability_key: str) -> Capability:
        """Return one capability by key, or fail closed if not registered."""

        if not capability_key:
            raise ValueError("capability_key is required")

        with self.database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM capability_registry WHERE capability_key = ?;",
                (capability_key,),
            ).fetchone()

        if row is None:
            raise CapabilityNotFoundError(f"Capability is not registered: {capability_key}")

        return self._row_to_capability(row)

    def is_permitted(self, capability_key: str) -> bool:
        """Return True only if the capability is registered and permitted."""

        try:
            return self.get(capability_key).is_permitted_in_mvp
        except CapabilityNotFoundError:
            return False

    def list_capabilities(self, *, permitted_only: Optional[bool] = None) -> list[Capability]:
        """Return all capabilities, optionally filtered by permission status."""

        sql = "SELECT * FROM capability_registry"
        params: tuple[Any, ...] = ()
        if permitted_only is not None:
            sql += " WHERE is_permitted_in_mvp = ?"
            params = (1 if permitted_only else 0,)
        sql += " ORDER BY is_permitted_in_mvp DESC, capability_key ASC;"

        with self.database.connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_capability(row) for row in rows]

    def assert_permitted(self, capability_key: str) -> Capability:
        """Hard gate for MVP capability use.

        Unknown capabilities fail closed. Explicitly blocked capabilities fail with
        a clear error. This method should be called before any recommendation,
        simulation, or action path can proceed.
        """

        capability = self.get(capability_key)
        if not capability.is_permitted_in_mvp:
            reason = capability.blocked_reason or capability.safety_notes or capability.description
            raise CapabilityNotPermittedError(
                f"Capability '{capability_key}' is explicitly blocked in the MVP. Reason: {reason}"
            )
        return capability


# =============================================================================
# Manual smoke test
# =============================================================================


if __name__ == "__main__":
    db = Database()
    db.initialize()

    expected_domain_tables = {
        "device_profile",
        "system_snapshot",
        "event_log",
        "goal_record",
        "recommendation_record",
        "action_record",
        "outcome_record",
        "user_tolerance_profile",
        "capability_registry",
    }
    tables = set(db.table_names())
    missing = expected_domain_tables.difference(tables)
    if missing:
        raise SystemExit(f"Missing expected Axon tables: {sorted(missing)}")

    db.verify_event_log_is_immutable()

    registry = CapabilityRegistry(db)
    permitted = registry.assert_permitted("startup_app_toggle")

    blocked_ok = False
    try:
        registry.assert_permitted("registry_modification")
    except CapabilityNotPermittedError:
        blocked_ok = True

    if not blocked_ok:
        raise SystemExit("Blocked capability unexpectedly passed assert_permitted().")

    logger = EventLogger(db)
    logger.log_event(
        source_engine="database",
        event_type="database_core_smoke_test_passed",
        payload={"permitted_capability_checked": permitted.capability_key},
    )

    snapshots = SnapshotManager(db, logger)
    profile_id = snapshots.create_device_profile(
        hostname="smoke-test",
        os_platform="test",
        raw_payload={"purpose": "database smoke test"},
    )
    baseline_id = snapshots.create_system_snapshot(
        device_profile_id=profile_id,
        snapshot_type="baseline",
        cpu_usage_percent=12.5,
        ram_usage_percent=33.3,
        storage_free_gb=100.0,
        raw_snapshot={"purpose": "database smoke test"},
    )
    latest = snapshots.get_latest_baseline()
    if latest is None or latest["snapshot_id"] != baseline_id:
        raise SystemExit("Latest baseline snapshot lookup failed.")

    print(f"Axon database initialised at: {db.db_path}")
    print("Schema tables present: passed")
    print("Event log immutability check: passed")
    print("Capability hard gate check: passed")
    print("Snapshot helper check: passed")
