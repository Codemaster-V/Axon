"""
event_logger.py — Axon S4 Event Logger
======================================

Responsible for writing structured events to the immutable event_log table.

Boundary:
    WRITE ONLY to event_log.
    No reads.
    No updates.
    No deletes.

The event_log table enforces immutability at the database level via S2 triggers.
This module reinforces append-only behaviour at the application level by exposing
only insert/log methods.

Public logging methods never raise. Callers do not need try/except around log
calls. On success, methods return the new event_id. On failure, they return None.

Live schema (S2 merged v2) — event_log columns used by this module:
    event_id             TEXT PRIMARY KEY
    occurred_at          TEXT NOT NULL
    source_engine        TEXT NOT NULL
    event_type           TEXT NOT NULL
    severity             TEXT NOT NULL DEFAULT 'info'
    related_entity_type  TEXT
    related_entity_id    TEXT
    payload_json         TEXT NOT NULL DEFAULT '{}'
    schema_version       TEXT NOT NULL DEFAULT '0.2'
    created_at           TEXT NOT NULL

EVENT_LOGGER_VERSION: "0.1.0-s4"
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


EVENT_LOGGER_VERSION = "0.1.0-s4"
_SCHEMA_VERSION = "0.2"

logger = logging.getLogger(__name__)

JsonMapping = Mapping[str, Any]


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _ensure_src_on_path_for_direct_execution() -> None:
    """
    Support direct script execution:

        python src/axon/core/event_logger.py

    Normal package imports should not need this. This helper is only used by
    the __main__ self-test and lazy fallback import path.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        src_dir = parent / "src"
        if (src_dir / "axon").exists():
            src_text = str(src_dir)
            if src_text not in sys.path:
                sys.path.insert(0, src_text)
            return


def _load_database_class() -> type[Any] | None:
    """
    Lazily import the S2 Database class without creating a DB dependency at
    module import time.
    """
    try:
        from .database import Database  # type: ignore

        return Database
    except Exception:
        try:
            _ensure_src_on_path_for_direct_execution()
            from axon.core.database import Database  # type: ignore

            return Database
        except Exception as exc:
            logger.debug("Could not import S2 Database class: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp with trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_event_id() -> str:
    """Create a readable event_id consistent with S2 new_id('event') style."""
    return f"event_{uuid.uuid4().hex}"


def json_dumps_defensive(value: Any) -> str:
    """
    JSON-serialize a value for event_log.payload_json.

    EventLogger must never raise to callers, so this function falls back to a
    safe diagnostic payload if normal serialization fails.
    """
    if value is None:
        value = {}

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        fallback = {
            "serialization_error": f"{exc.__class__.__name__}: {exc}",
            "payload_repr": repr(value),
        }
        try:
            return json.dumps(
                fallback,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            )
        except Exception:
            return "{}"


def _safe_short_string(value: Any, *, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


# ---------------------------------------------------------------------------
# EventLogger
# ---------------------------------------------------------------------------

class EventLogger:
    """
    Append-only event logger for Axon's event_log table.

    Public methods never raise. On successful insert they return the new
    event_id. On failure they return None and write diagnostic details to
    Python logging.

    This class intentionally exposes no update/delete/read methods.
    """

    # Source engines from Axon's five-engine architecture plus DB/system emitters.
    SOURCE_OBSERVATION = "observation_engine"
    SOURCE_GOAL = "goal_engine"
    SOURCE_DECISION = "decision_engine"
    SOURCE_ACTION = "action_engine"
    SOURCE_LEARNING = "learning_engine"
    SOURCE_DATABASE = "database"
    SOURCE_SYSTEM = "system"
    SOURCE_EVENT_LOGGER = "event_logger"

    VALID_SOURCE_ENGINES = frozenset(
        {
            SOURCE_OBSERVATION,
            SOURCE_GOAL,
            SOURCE_DECISION,
            SOURCE_ACTION,
            SOURCE_LEARNING,
            SOURCE_DATABASE,
            SOURCE_SYSTEM,
            SOURCE_EVENT_LOGGER,
        }
    )

    # Event type constants from the S4 brief.
    EVENT_OBSERVATION_STARTED = "observation_started"
    EVENT_OBSERVATION_COMPLETED = "observation_completed"
    EVENT_OBSERVATION_FAILED = "observation_failed"

    EVENT_GOAL_CREATED = "goal_created"
    EVENT_GOAL_UPDATED = "goal_updated"
    EVENT_GOAL_COMPLETED = "goal_completed"

    EVENT_RECOMMENDATION_GENERATED = "recommendation_generated"
    EVENT_RECOMMENDATION_APPROVED = "recommendation_approved"
    EVENT_RECOMMENDATION_DECLINED = "recommendation_declined"

    EVENT_ACTION_STARTED = "action_started"
    EVENT_ACTION_COMPLETED = "action_completed"
    EVENT_ACTION_FAILED = "action_failed"
    EVENT_ACTION_ROLLED_BACK = "action_rolled_back"

    EVENT_OUTCOME_RECORDED = "outcome_recorded"
    EVENT_CAPABILITY_REGISTRY_LOADED = "capability_registry_loaded"
    EVENT_SYSTEM_ERROR = "system_error"

    # Compatibility/system events already used by S2 database.py.
    EVENT_DATABASE_INTEGRITY_CHECK = "database_integrity_check"
    EVENT_DATABASE_CORE_SMOKE_TEST_PASSED = "database_core_smoke_test_passed"
    EVENT_DEVICE_PROFILE_CREATED = "device_profile_created"
    EVENT_SYSTEM_SNAPSHOT_CREATED = "system_snapshot_created"

    VALID_EVENT_TYPES = frozenset(
        {
            EVENT_OBSERVATION_STARTED,
            EVENT_OBSERVATION_COMPLETED,
            EVENT_OBSERVATION_FAILED,
            EVENT_GOAL_CREATED,
            EVENT_GOAL_UPDATED,
            EVENT_GOAL_COMPLETED,
            EVENT_RECOMMENDATION_GENERATED,
            EVENT_RECOMMENDATION_APPROVED,
            EVENT_RECOMMENDATION_DECLINED,
            EVENT_ACTION_STARTED,
            EVENT_ACTION_COMPLETED,
            EVENT_ACTION_FAILED,
            EVENT_ACTION_ROLLED_BACK,
            EVENT_OUTCOME_RECORDED,
            EVENT_CAPABILITY_REGISTRY_LOADED,
            EVENT_SYSTEM_ERROR,
            EVENT_DATABASE_INTEGRITY_CHECK,
            EVENT_DATABASE_CORE_SMOKE_TEST_PASSED,
            EVENT_DEVICE_PROFILE_CREATED,
            EVENT_SYSTEM_SNAPSHOT_CREATED,
        }
    )

    VALID_SEVERITIES = frozenset({"debug", "info", "warning", "error", "critical"})

    DEFAULT_SEVERITY_BY_EVENT_TYPE = {
        EVENT_OBSERVATION_FAILED: "warning",
        EVENT_ACTION_FAILED: "error",
        EVENT_ACTION_ROLLED_BACK: "warning",
        EVENT_SYSTEM_ERROR: "error",
    }

    def __init__(self, database_manager: Any) -> None:
        """
        Args:
            database_manager:
                Preferred: S2 Database instance exposing connection().
                Fallbacks supported for tests: get_connection(), connect(),
                or a raw sqlite3.Connection.

        The logger does not own database bootstrapping, migrations, or seed
        execution.
        """
        self.database_manager = database_manager

    def log(
        self,
        event_type: str,
        source_engine: str,
        payload: JsonMapping | None,
        severity: str | None = None,
        related_entity_id: str | None = None,
        related_entity_type: str | None = None,
    ) -> str | None:
        """
        Insert one event into event_log.

        Returns:
            event_id on success, None on failure.

        Never raises to callers.
        """
        event_type = _safe_short_string(event_type, fallback="")
        source_engine = _safe_short_string(source_engine, fallback="unknown")

        if event_type not in self.VALID_EVENT_TYPES:
            self._log_system_error(
                {
                    "error": "unknown_event_type",
                    "received": event_type,
                    "known_types": sorted(self.VALID_EVENT_TYPES),
                    "source_engine": source_engine,
                    "related_entity_id": related_entity_id,
                    "related_entity_type": related_entity_type,
                    "event_logger_version": EVENT_LOGGER_VERSION,
                }
            )
            return None

        if source_engine not in self.VALID_SOURCE_ENGINES:
            logger.warning(
                "EventLogger: unknown source_engine '%s' — writing event anyway",
                source_engine,
            )

        resolved_severity = (
            severity
            or self.DEFAULT_SEVERITY_BY_EVENT_TYPE.get(event_type)
            or "info"
        )
        resolved_severity = _safe_short_string(resolved_severity, fallback="info").lower()

        # Merged decision: invalid severity should degrade to info rather than
        # losing the event. Event data is more valuable than perfect severity.
        if resolved_severity not in self.VALID_SEVERITIES:
            logger.warning(
                "EventLogger: invalid severity '%s' for event_type '%s' — defaulting to 'info'",
                resolved_severity,
                event_type,
            )
            resolved_severity = "info"

        if not isinstance(payload, Mapping):
            self._log_system_error(
                {
                    "error": "payload_not_mapping",
                    "received_type": type(payload).__name__,
                    "event_type": event_type,
                    "source_engine": source_engine,
                    "payload_repr": repr(payload),
                    "event_logger_version": EVENT_LOGGER_VERSION,
                }
            )
            return None

        safe_payload = dict(payload)
        safe_payload.setdefault("event_logger_version", EVENT_LOGGER_VERSION)

        return self._write_event(
            event_type=event_type,
            source_engine=source_engine,
            severity=resolved_severity,
            payload=safe_payload,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type,
        )

    def log_event(
        self,
        *,
        source_engine: str,
        event_type: str,
        payload: JsonMapping | None = None,
        severity: str | None = None,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
    ) -> str | None:
        """
        Keyword-compatible wrapper matching the S2 database.py logger shape.

        Returns event_id on success, None on failure.
        """
        return self.log(
            event_type=event_type,
            source_engine=source_engine,
            payload=payload or {},
            severity=severity,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type,
        )

    # ------------------------------------------------------------------
    # Thin convenience wrappers
    # ------------------------------------------------------------------

    def log_observation_started(self, payload: JsonMapping | None = None) -> str | None:
        return self.log(
            event_type=self.EVENT_OBSERVATION_STARTED,
            source_engine=self.SOURCE_OBSERVATION,
            payload=payload or {},
        )

    def log_observation_completed(self, payload: JsonMapping | None = None) -> str | None:
        return self.log(
            event_type=self.EVENT_OBSERVATION_COMPLETED,
            source_engine=self.SOURCE_OBSERVATION,
            payload=payload or {},
        )

    def log_observation_failed(self, payload: JsonMapping | None = None) -> str | None:
        return self.log(
            event_type=self.EVENT_OBSERVATION_FAILED,
            source_engine=self.SOURCE_OBSERVATION,
            payload=payload or {},
        )

    def log_system_error(self, payload: JsonMapping | None = None) -> str | None:
        """
        Public system_error helper.

        Uses normal validation. Internal validation failures use
        _log_system_error(), which bypasses validation and writes directly to
        avoid recursive logging loops.
        """
        return self.log(
            event_type=self.EVENT_SYSTEM_ERROR,
            source_engine=self.SOURCE_SYSTEM,
            payload=payload or {},
        )

    def log_capability_registry_loaded(self, payload: JsonMapping | None = None) -> str | None:
        return self.log(
            event_type=self.EVENT_CAPABILITY_REGISTRY_LOADED,
            source_engine=self.SOURCE_DATABASE,
            payload=payload or {},
        )

    # ------------------------------------------------------------------
    # Internal write path
    # ------------------------------------------------------------------

    def _log_system_error(self, payload: JsonMapping | None = None) -> str | None:
        """
        Internal guarded system_error write path.

        This bypasses public validation to avoid recursive logging loops if
        public validation itself fails. It still catches all exceptions.
        """
        safe_payload = dict(payload or {})
        safe_payload.setdefault("event_logger_version", EVENT_LOGGER_VERSION)
        safe_payload.setdefault("logged_by", "EventLogger._log_system_error")

        return self._write_event(
            event_type=self.EVENT_SYSTEM_ERROR,
            source_engine=self.SOURCE_EVENT_LOGGER,
            severity="error",
            payload=safe_payload,
            related_entity_id=None,
            related_entity_type=None,
        )

    def _write_event(
        self,
        *,
        event_type: str,
        source_engine: str,
        severity: str,
        payload: JsonMapping,
        related_entity_id: str | None,
        related_entity_type: str | None,
    ) -> str | None:
        """
        Low-level append-only INSERT.

        This method never raises to callers.
        """
        event_id = new_event_id()
        now = utc_now()
        payload_json = json_dumps_defensive(dict(payload))

        try:
            connection_context = self._connection_context()
            with connection_context as conn:
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
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                        _SCHEMA_VERSION,
                        now,
                    ),
                )
            return event_id

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "EventLogger failed to write event_type=%s source_engine=%s error=%s",
                event_type,
                source_engine,
                exc,
            )
            return None

    def _connection_context(self) -> Any:
        """
        Return a context manager yielding a sqlite3.Connection-like object.

        Preferred production path uses S2 Database.connection(), which handles
        BEGIN/COMMIT, rollback, close, WAL, busy_timeout, and foreign_keys.
        """
        if self.database_manager is None:
            raise RuntimeError("database_manager is required")

        if hasattr(self.database_manager, "connection"):
            return self.database_manager.connection()

        if hasattr(self.database_manager, "get_connection"):
            conn = self.database_manager.get_connection()
            return _ConnectionContext(conn, commit_on_exit=True, close_on_exit=True)

        if hasattr(self.database_manager, "connect"):
            conn = self.database_manager.connect()
            return _ConnectionContext(conn, commit_on_exit=True, close_on_exit=True)

        if isinstance(self.database_manager, sqlite3.Connection):
            # Supported as a lightweight fallback for tests only.
            return nullcontext(self.database_manager)

        raise TypeError(
            "database_manager must provide connection(), get_connection(), connect(), "
            "or be a sqlite3.Connection"
        )


class _ConnectionContext:
    """
    Small fallback context manager for raw sqlite3 connections.

    Preferred production path is S2 Database.connection().
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        commit_on_exit: bool = True,
        close_on_exit: bool = True,
    ) -> None:
        self.conn = conn
        self.commit_on_exit = commit_on_exit
        self.close_on_exit = close_on_exit

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            if exc_type is None and self.commit_on_exit:
                self.conn.commit()
            elif exc_type is not None:
                self.conn.rollback()
        finally:
            if self.close_on_exit:
                self.conn.close()
        return False


# ---------------------------------------------------------------------------
# Module-level convenience wrapper
# ---------------------------------------------------------------------------

def log_event(
    database_manager: Any,
    *,
    source_engine: str,
    event_type: str,
    payload: JsonMapping | None = None,
    severity: str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> str | None:
    """
    One-shot convenience function.

    Returns event_id on success, None on failure.
    """
    return EventLogger(database_manager).log(
        event_type=event_type,
        source_engine=source_engine,
        payload=payload or {},
        severity=severity,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )


__all__ = [
    "EVENT_LOGGER_VERSION",
    "EventLogger",
    "log_event",
]


# ---------------------------------------------------------------------------
# Manual self-test
# ---------------------------------------------------------------------------

def _run_self_test(db_path: str | None = None) -> int:
    Database = _load_database_class()
    if Database is None:
        print("Could not import axon.core.database.Database", file=sys.stderr)
        return 1

    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    db = Database(**kwargs)
    db.initialize()

    event_logger = EventLogger(db)

    success_count = 0
    failure_count = 0

    for event_type in sorted(EventLogger.VALID_EVENT_TYPES):
        event_id = event_logger.log(
            event_type=event_type,
            source_engine=EventLogger.SOURCE_SYSTEM,
            payload={
                "purpose": "event_logger_self_test",
                "event_type_under_test": event_type,
            },
            severity="debug" if event_type != EventLogger.EVENT_SYSTEM_ERROR else "error",
        )
        if event_id:
            success_count += 1
        else:
            failure_count += 1

    invalid_result = event_logger.log(
        event_type="invalid_event_type_for_self_test",
        source_engine=EventLogger.SOURCE_SYSTEM,
        payload={"purpose": "confirm_invalid_type_returns_none_and_logs_system_error"},
        severity="info",
    )

    invalid_severity_result = event_logger.log(
        event_type=EventLogger.EVENT_SYSTEM_ERROR,
        source_engine=EventLogger.SOURCE_SYSTEM,
        payload={"purpose": "confirm_invalid_severity_defaults_to_info"},
        severity="warn",
    )

    invalid_payload_result = event_logger.log(
        event_type=EventLogger.EVENT_SYSTEM_ERROR,
        source_engine=EventLogger.SOURCE_SYSTEM,
        payload="this is not a mapping",  # type: ignore[arg-type]
        severity="error",
    )

    print(f"Axon EventLogger self-test DB: {getattr(db, 'db_path', db_path)}")
    print(f"Valid event inserts succeeded: {success_count}")
    print(f"Valid event inserts failed: {failure_count}")
    print(f"Invalid event returned None: {invalid_result is None}")
    print(f"Invalid severity degraded and wrote event: {invalid_severity_result is not None}")
    print(f"Invalid payload returned None: {invalid_payload_result is None}")

    return (
        0
        if success_count > 0
        and failure_count == 0
        and invalid_result is None
        and invalid_severity_result is not None
        and invalid_payload_result is None
        else 2
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Axon S4 EventLogger self-test.")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite DB path. Defaults to Database() project data path.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    raise SystemExit(_run_self_test(args.db_path))
