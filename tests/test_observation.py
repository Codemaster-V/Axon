"""
tests/test_observation.py — Axon S5 Observation Engine Smoke Tests
==================================================================

Target location:
    tests/test_observation.py

Purpose:
    Smoke-test the live S2/S3/S4 foundations:
        - database initialisation
        - database idempotency
        - event_log immutability triggers
        - S4 EventLogger append-only write behaviour
        - capability registry hard gate and row counts
        - standalone seed SQL idempotency
        - S3 collectors snapshot shape and privacy defaults

Test framework:
    pytest

Isolation strategy:
    All database tests use pytest's tmp_path fixture — a real temporary SQLite
    file per test. This matches how Database resolves paths and avoids any
    interaction with the live project database.

Out of scope for S5:
    - GPU telemetry assertions (ASSUMPTION-006 remains open)
    - Windows-only assertions that would fail in non-Windows environments
    - performance/load benchmarking
    - full-stack integration (S15)
    - automatic seed wiring into Database.initialize() (RISK-011 remains open)

RISK-011 note:
    The capability_registry rows are still populated automatically by the S2
    migration file's embedded INSERT OR IGNORE rows. The standalone S4 seed file
    exists and is tested here for manual idempotency, but automatic schema/seeds/
    execution is not wired yet.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Project root and sys.path setup
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk upward from this file to find the Axon project root."""
    start = Path(__file__).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "schema" / "migrations" / "001_initial_schema.sql").exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate Axon project root. Expected to find "
        "schema/migrations/001_initial_schema.sql above "
        f"{start}."
    )


PROJECT_ROOT = _find_project_root()
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


# ---------------------------------------------------------------------------
# Imports — deferred until sys.path is configured
# ---------------------------------------------------------------------------

from axon.core.database import (  # noqa: E402
    CapabilityNotFoundError,
    CapabilityNotPermittedError,
    CapabilityRegistry,
    Database,
)
from axon.core.event_logger import EventLogger  # noqa: E402
from axon.engines.observation_engine.collectors import (  # noqa: E402
    collect_system_snapshot,
)


# ---------------------------------------------------------------------------
# Expected schema / snapshot shapes
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    # Migration bookkeeping table.
    "schema_migrations",
    # Confirmed Schema V0.2 entities.
    "device_profile",
    "system_snapshot",
    "event_log",
    "user_tolerance_profile",
    "goal_record",
    "capability_registry",
    "recommendation_record",
    "action_record",
    "outcome_record",
}

EXPECTED_SNAPSHOT_TOP_LEVEL_KEYS = {
    "cpu_usage_percent",
    "ram_usage_percent",
    "disk_usage_percent",
    "snapshot_data",
    "environmental_context",
}

EXPECTED_SNAPSHOT_DATA_KEYS = {
    "collector_version",
    "collected_at_utc",
    "collection_scope",
    "device_profile",
    "cpu",
    "memory",
    "disk",
    "network",
    "power",
    "temperatures",
    "gpu",
    "processes",
    "startup_apps",
    "collection_errors",
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Return an initialised Database backed by a temporary SQLite file."""
    database = Database(
        db_path=tmp_path / "axon_test.sqlite3",
        project_root=PROJECT_ROOT,
    )
    database.initialize()
    return database


@pytest.fixture()
def event_logger(db: Database) -> EventLogger:
    """Return the S4 EventLogger wired to the temporary test database."""
    return EventLogger(db)


@pytest.fixture()
def capability_registry(db: Database) -> CapabilityRegistry:
    """Return a CapabilityRegistry wired to the temporary test database."""
    return CapabilityRegistry(db)


def fetch_one_value(db: Database, sql: str, params: tuple[Any, ...] = ()) -> Any:
    """Run a scalar SELECT against the temporary test database."""
    with db.connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row is not None else None


def count_system_errors(db: Database) -> int:
    return int(
        fetch_one_value(
            db,
            "SELECT COUNT(*) FROM event_log WHERE event_type = 'system_error';",
        )
    )


# ---------------------------------------------------------------------------
# Database — initialisation
# ---------------------------------------------------------------------------

def test_database_initialises(db: Database) -> None:
    """Database.initialize() creates all expected schema tables."""
    actual = set(db.table_names())
    missing = EXPECTED_TABLES - actual

    assert not missing, f"Tables missing after initialize(): {sorted(missing)}"


def test_database_idempotency(tmp_path: Path) -> None:
    """Calling Database.initialize() twice does not raise or corrupt the DB."""
    database = Database(
        db_path=tmp_path / "axon_idempotent.sqlite3",
        project_root=PROJECT_ROOT,
    )

    database.initialize()
    first_tables = set(database.table_names())

    database.initialize()
    second_tables = set(database.table_names())

    assert EXPECTED_TABLES.issubset(second_tables)
    assert first_tables == second_tables


# ---------------------------------------------------------------------------
# EventLogger — valid writes and wrappers
# ---------------------------------------------------------------------------

def test_event_logger_writes_valid_event(event_logger: EventLogger, db: Database) -> None:
    """A valid EventLogger write returns an event_id and lands in event_log."""
    event_id = event_logger.log(
        event_type=EventLogger.EVENT_OBSERVATION_COMPLETED,
        source_engine=EventLogger.SOURCE_OBSERVATION,
        payload={"purpose": "s5_smoke_test"},
    )

    assert event_id is not None, "EventLogger.log() returned None for a valid event"
    assert isinstance(event_id, str)
    assert event_id.startswith("event_")

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT event_id, source_engine, event_type, severity, payload_json
            FROM event_log
            WHERE event_id = ?;
            """,
            (event_id,),
        ).fetchone()

    assert row is not None, f"Event {event_id} not found in event_log"
    assert row["source_engine"] == EventLogger.SOURCE_OBSERVATION
    assert row["event_type"] == EventLogger.EVENT_OBSERVATION_COMPLETED
    assert row["severity"] == "info"

    payload = json.loads(row["payload_json"])
    assert payload["purpose"] == "s5_smoke_test"


def test_event_logger_keyword_wrapper(event_logger: EventLogger, db: Database) -> None:
    """log_event() keyword wrapper accepts the expected S2-compatible shape."""
    event_id = event_logger.log_event(
        source_engine=EventLogger.SOURCE_OBSERVATION,
        event_type=EventLogger.EVENT_OBSERVATION_COMPLETED,
        payload={"stage": "end"},
        severity="info",
        related_entity_type="system_snapshot",
        related_entity_id="snapshot_abc123",
    )

    assert event_id is not None

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT related_entity_type, related_entity_id
            FROM event_log
            WHERE event_id = ?;
            """,
            (event_id,),
        ).fetchone()

    assert row is not None
    assert row["related_entity_type"] == "system_snapshot"
    assert row["related_entity_id"] == "snapshot_abc123"


# ---------------------------------------------------------------------------
# EventLogger — rejection/degradation cases
# ---------------------------------------------------------------------------

def test_event_logger_rejects_invalid_event_type(
    event_logger: EventLogger,
    db: Database,
) -> None:
    """Unknown event_type returns None and writes a diagnostic system_error."""
    before = count_system_errors(db)

    result = event_logger.log_event(
        source_engine=EventLogger.SOURCE_OBSERVATION,
        event_type="this_event_type_does_not_exist",
        payload={"purpose": "invalid_event_type_test"},
    )

    after = count_system_errors(db)

    assert result is None
    assert after == before + 1


def test_event_logger_invalid_severity_degrades_to_info(
    event_logger: EventLogger,
    db: Database,
) -> None:
    """
    Invalid severity 'warn' degrades to 'info' and still writes the event.

    S4 merged decision: event data is more valuable than perfect severity.
    """
    event_id = event_logger.log_event(
        source_engine=EventLogger.SOURCE_OBSERVATION,
        event_type=EventLogger.EVENT_OBSERVATION_STARTED,
        payload={"purpose": "invalid_severity_test"},
        severity="warn",
    )

    assert event_id is not None

    severity = fetch_one_value(
        db,
        "SELECT severity FROM event_log WHERE event_id = ?;",
        (event_id,),
    )
    assert severity == "info"


def test_event_logger_rejects_invalid_payload(
    event_logger: EventLogger,
    db: Database,
) -> None:
    """Non-Mapping payload returns None and writes a diagnostic system_error."""
    before = count_system_errors(db)

    result = event_logger.log_event(
        source_engine=EventLogger.SOURCE_OBSERVATION,
        event_type=EventLogger.EVENT_OBSERVATION_STARTED,
        payload="this is not a mapping",  # type: ignore[arg-type]
    )

    after = count_system_errors(db)

    assert result is None
    assert after == before + 1


# ---------------------------------------------------------------------------
# Event log immutability triggers
# ---------------------------------------------------------------------------

def test_event_log_update_is_blocked(event_logger: EventLogger, db: Database) -> None:
    """The S2 BEFORE UPDATE trigger blocks UPDATE on event_log rows."""
    event_id = event_logger.log_event(
        source_engine=EventLogger.SOURCE_OBSERVATION,
        event_type=EventLogger.EVENT_OBSERVATION_STARTED,
        payload={"purpose": "immutability_update_test"},
    )

    assert event_id is not None

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.connection() as conn:
            conn.execute(
                "UPDATE event_log SET event_type = ? WHERE event_id = ?;",
                ("mutation_should_fail", event_id),
            )


def test_event_log_delete_is_blocked(event_logger: EventLogger, db: Database) -> None:
    """The S2 BEFORE DELETE trigger blocks DELETE on event_log rows."""
    event_id = event_logger.log_event(
        source_engine=EventLogger.SOURCE_OBSERVATION,
        event_type=EventLogger.EVENT_OBSERVATION_STARTED,
        payload={"purpose": "immutability_delete_test"},
    )

    assert event_id is not None

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.connection() as conn:
            conn.execute(
                "DELETE FROM event_log WHERE event_id = ?;",
                (event_id,),
            )


# ---------------------------------------------------------------------------
# Capability registry — counts
# ---------------------------------------------------------------------------

def test_capability_registry_total_count(capability_registry: CapabilityRegistry) -> None:
    """Capability registry has exactly 13 rows seeded."""
    all_capabilities = capability_registry.list_capabilities()
    assert len(all_capabilities) == 13


def test_capability_registry_permitted_count(capability_registry: CapabilityRegistry) -> None:
    """Exactly 6 capabilities are permitted in MVP."""
    permitted = capability_registry.list_capabilities(permitted_only=True)
    assert len(permitted) == 6


def test_capability_registry_blocked_count(capability_registry: CapabilityRegistry) -> None:
    """Exactly 7 capabilities are explicitly blocked in MVP."""
    blocked = capability_registry.list_capabilities(permitted_only=False)
    assert len(blocked) == 7


# ---------------------------------------------------------------------------
# Capability registry — hard gate
# ---------------------------------------------------------------------------

def test_capability_hard_gate_permits_startup_app_toggle(
    capability_registry: CapabilityRegistry,
) -> None:
    """assert_permitted() passes for startup_app_toggle."""
    capability = capability_registry.assert_permitted("startup_app_toggle")

    assert capability.capability_key == "startup_app_toggle"
    assert capability.is_permitted_in_mvp is True


def test_capability_hard_gate_blocks_registry_modification(
    capability_registry: CapabilityRegistry,
) -> None:
    """assert_permitted() raises for registry_modification."""
    with pytest.raises(CapabilityNotPermittedError):
        capability_registry.assert_permitted("registry_modification")


def test_capability_is_permitted_returns_true_for_permitted(
    capability_registry: CapabilityRegistry,
) -> None:
    """is_permitted() returns True for a permitted capability."""
    assert capability_registry.is_permitted("startup_app_toggle") is True


def test_capability_is_permitted_returns_false_for_blocked(
    capability_registry: CapabilityRegistry,
) -> None:
    """is_permitted() returns False for a blocked capability."""
    assert capability_registry.is_permitted("registry_modification") is False


def test_capability_is_permitted_returns_false_for_unknown(
    capability_registry: CapabilityRegistry,
) -> None:
    """Unknown capabilities fail closed through is_permitted()."""
    assert capability_registry.is_permitted("not_registered") is False


def test_capability_get_unknown_raises_not_found(
    capability_registry: CapabilityRegistry,
) -> None:
    """CapabilityRegistry.get() raises for unknown capability keys."""
    with pytest.raises(CapabilityNotFoundError):
        capability_registry.get("not_registered")


# ---------------------------------------------------------------------------
# Capability registry — standalone seed file idempotency
# ---------------------------------------------------------------------------

def test_standalone_seed_file_is_idempotent(tmp_path: Path) -> None:
    """
    The standalone S4 seed file is safe to execute against a DB already seeded
    by the migration.

    This validates RISK-011's documented behaviour without requiring seed
    execution to be wired into Database.initialize() yet.
    """
    database = Database(
        db_path=tmp_path / "axon_seed_idempotency.sqlite3",
        project_root=PROJECT_ROOT,
    )
    database.initialize()

    seed_path = PROJECT_ROOT / "schema" / "seeds" / "001_capability_registry.sql"
    assert seed_path.exists(), f"Seed file not found: {seed_path}"

    seed_sql = seed_path.read_text(encoding="utf-8")

    conn = database.connect()
    try:
        conn.executescript(seed_sql)
        conn.executescript(seed_sql)
    finally:
        conn.close()

    registry = CapabilityRegistry(database)

    assert len(registry.list_capabilities()) == 13
    assert len(registry.list_capabilities(permitted_only=True)) == 6
    assert len(registry.list_capabilities(permitted_only=False)) == 7


# ---------------------------------------------------------------------------
# Observation Engine collectors — no exception / shape
# ---------------------------------------------------------------------------

def test_collectors_do_not_raise() -> None:
    """collect_system_snapshot() completes without raising."""
    snapshot = collect_system_snapshot(process_limit=10)

    assert isinstance(snapshot, dict)


def test_collectors_snapshot_top_level_keys() -> None:
    """collect_system_snapshot() returns expected top-level keys."""
    snapshot = collect_system_snapshot(process_limit=10)

    missing = EXPECTED_SNAPSHOT_TOP_LEVEL_KEYS - set(snapshot.keys())
    assert not missing, f"Snapshot missing top-level keys: {sorted(missing)}"


def test_collectors_snapshot_data_keys() -> None:
    """snapshot_data contains expected collector keys."""
    snapshot = collect_system_snapshot(process_limit=10)

    snapshot_data = snapshot.get("snapshot_data", {})
    assert isinstance(snapshot_data, dict)

    missing = EXPECTED_SNAPSHOT_DATA_KEYS - set(snapshot_data.keys())
    assert not missing, f"snapshot_data missing keys: {sorted(missing)}"


def test_collectors_snapshot_is_json_serialisable() -> None:
    """The full collector snapshot must be JSON-serialisable."""
    snapshot = collect_system_snapshot(process_limit=10)

    try:
        encoded = json.dumps(snapshot)
    except (TypeError, ValueError) as exc:
        pytest.fail(f"Collector snapshot is not JSON-serialisable: {exc}")

    assert isinstance(encoded, str)
    assert encoded.startswith("{")


# ---------------------------------------------------------------------------
# Observation Engine collectors — privacy defaults
# ---------------------------------------------------------------------------

def test_collectors_no_active_window_title_by_default() -> None:
    """active_window_title is not collected by default."""
    snapshot = collect_system_snapshot(process_limit=10)
    environmental_context = snapshot.get("environmental_context", {})

    assert environmental_context.get("active_window_title") is None


def test_collectors_no_process_cmdline_by_default() -> None:
    """Process entries do not include command-line args by default."""
    snapshot = collect_system_snapshot(process_limit=10)
    processes_block = snapshot.get("snapshot_data", {}).get("processes", {})
    process_list = (
        processes_block.get("processes", [])
        if isinstance(processes_block, dict)
        else []
    )

    for process in process_list:
        assert "cmdline" not in process


def test_collectors_no_process_username_by_default() -> None:
    """Process entries do not include usernames by default."""
    snapshot = collect_system_snapshot(process_limit=10)
    processes_block = snapshot.get("snapshot_data", {}).get("processes", {})
    process_list = (
        processes_block.get("processes", [])
        if isinstance(processes_block, dict)
        else []
    )

    for process in process_list:
        assert "username" not in process
