"""
goal_engine.py  Axon S6 Goal Engine
====================================

Target location:
    src/axon/engines/goal_engine/goal_engine.py

Purpose:
    Capture user intent through MVP preset modes and persist structured
    goal_record rows for the later Decision Engine.

Scope:
    - Four preset goal modes only.
    - No natural language parsing.
    - No system changes.
    - No Decision Engine calls.
    - No action execution.
    - Domain state is written through the shared S2 Database layer.
    - Audit events are written through the S4 EventLogger.

Live goal_record schema used by this module:
    goal_id                       TEXT PRIMARY KEY
    tolerance_profile_id           TEXT
    created_at                     TEXT NOT NULL
    updated_at                     TEXT
    goal_mode                      TEXT NOT NULL
    raw_user_intent                TEXT
    interpreted_goal_json          TEXT
    priority_json                  TEXT
    acknowledged_tradeoffs_json    TEXT
    status                         TEXT NOT NULL DEFAULT 'active'

Important design note:
    EventLogger writes to event_log only. It does not write goal_record rows.
    GoalEngine uses Database.connection() for goal_record domain writes, then
    uses EventLogger to append immutable audit events.

Active goal model:
    Hybrid domain-state + append-only audit.
    - goal_record stores current state using status='active'/'superseded'.
    - event_log stores append-only audit history of goal transitions.
    - Setting a new goal supersedes any currently active goal rows.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


GOAL_ENGINE_VERSION = "0.1.0-s6"

logger = logging.getLogger(__name__)

JsonMapping = Mapping[str, Any]


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _ensure_src_on_path_for_direct_execution() -> None:
    """
    Support direct script execution:

        python src/axon/engines/goal_engine/goal_engine.py

    Normal package imports should not need this. This helper is only used by
    fallback import paths and __main__ self-test execution.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        src_dir = parent / "src"
        if (src_dir / "axon").exists():
            src_text = str(src_dir)
            if src_text not in sys.path:
                sys.path.insert(0, src_text)
            return


try:
    from axon.core.database import Database, find_project_root, new_id, utc_now
    from axon.core.event_logger import EventLogger
except Exception:  # pragma: no cover - direct script fallback
    _ensure_src_on_path_for_direct_execution()
    from axon.core.database import Database, find_project_root, new_id, utc_now
    from axon.core.event_logger import EventLogger


# ---------------------------------------------------------------------------
# Preset goal mode metadata
# ---------------------------------------------------------------------------

MODE_MAXIMISE_FPS = "maximise_fps"
MODE_QUIET = "quiet_mode"
MODE_FREE_STORAGE = "free_storage"
MODE_BALANCED = "balanced"

VALID_GOAL_MODES = frozenset(
    {
        MODE_MAXIMISE_FPS,
        MODE_QUIET,
        MODE_FREE_STORAGE,
        MODE_BALANCED,
    }
)

GOAL_MODE_METADATA: dict[str, dict[str, Any]] = {
    MODE_MAXIMISE_FPS: {
        "mode": MODE_MAXIMISE_FPS,
        "display_name": "Maximise FPS",
        "description": (
            "Prioritise gaming frame rate by allowing more aggressive "
            "recommendations such as reducing background activity, favouring "
            "performance power settings, and accepting higher fan noise."
        ),
        "intent": "Prioritise gaming frame rate and responsiveness.",
        "tradeoffs": [
            "Higher fan noise",
            "Higher power usage",
            "Reduced battery life on laptops",
            "More background interruptions may be recommended",
        ],
        "risk_level": "moderate",
        "decision_hints": {
            "performance_priority": "high",
            "stability_priority": "moderate",
            "noise_tolerance": "high",
            "battery_priority": "low",
            "interruption_tolerance": "moderate",
            "storage_priority": "low",
            "thermal_tolerance": "high",
            "recommendation_aggression": "moderate",
        },
    },
    MODE_QUIET: {
        "mode": MODE_QUIET,
        "display_name": "Quiet Mode",
        "description": (
            "Reduce fan noise and system aggressiveness by favouring conservative "
            "recommendations that lower heat, reduce background load, and avoid "
            "performance-heavy changes."
        ),
        "intent": "Minimise fan noise and thermal pressure.",
        "tradeoffs": [
            "Lower peak performance",
            "Lower frame rates may be accepted",
            "Background activity may be left alone if stopping it is disruptive",
        ],
        "risk_level": "low",
        "decision_hints": {
            "performance_priority": "low",
            "stability_priority": "high",
            "noise_tolerance": "low",
            "battery_priority": "moderate",
            "interruption_tolerance": "low",
            "storage_priority": "low",
            "thermal_tolerance": "low",
            "recommendation_aggression": "conservative",
        },
    },
    MODE_FREE_STORAGE: {
        "mode": MODE_FREE_STORAGE,
        "display_name": "Free Storage",
        "description": (
            "Identify storage reclaim opportunities and surface safe cleanup "
            "recommendations. This mode is recommendation-first and does not "
            "imply automatic file deletion."
        ),
        "intent": "Find safe ways to reclaim disk space.",
        "tradeoffs": [
            "Cleanup may require user review",
            "Cache cleanup is not true rollback; caches rebuild naturally",
            "Personal files must not be deleted automatically",
        ],
        "risk_level": "low",
        "decision_hints": {
            "performance_priority": "moderate",
            "stability_priority": "high",
            "noise_tolerance": "moderate",
            "battery_priority": "moderate",
            "interruption_tolerance": "low",
            "storage_priority": "high",
            "thermal_tolerance": "moderate",
            "recommendation_aggression": "conservative",
        },
    },
    MODE_BALANCED: {
        "mode": MODE_BALANCED,
        "display_name": "Balanced",
        "description": (
            "Use moderate, low-intervention recommendations that balance "
            "performance, stability, noise, storage, and user interruption."
        ),
        "intent": "Balance performance, stability, noise, storage, and interruption.",
        "tradeoffs": [
            "May not maximise peak FPS",
            "May not minimise fan noise as strongly as Quiet Mode",
            "Optimisations are conservative by default",
        ],
        "risk_level": "low",
        "decision_hints": {
            "performance_priority": "moderate",
            "stability_priority": "high",
            "noise_tolerance": "moderate",
            "battery_priority": "moderate",
            "interruption_tolerance": "low",
            "storage_priority": "moderate",
            "thermal_tolerance": "moderate",
            "recommendation_aggression": "conservative",
        },
    },
}

# Backwards/ergonomic aliases for Claude's naming.
MODE_REGISTRY = GOAL_MODE_METADATA
VALID_MODES = VALID_GOAL_MODES


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def json_dumps_defensive(value: Any) -> str:
    """
    JSON serialise for goal_record JSON columns.

    Uses default=str to keep public GoalEngine methods graceful when callers
    pass values such as Path or datetime inside parameters.
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
            "value_repr": repr(value),
        }
        return json.dumps(
            fallback,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )


def json_loads_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}

    try:
        loaded = json.loads(value)
    except Exception:
        return {"raw": value}

    if isinstance(loaded, dict):
        return loaded

    return {"value": loaded}


def normalise_mode(mode: str) -> str:
    """Normalise user/caller mode input into internal snake_case mode keys."""
    return str(mode or "").strip().lower().replace(" ", "_").replace("-", "_")


def row_to_goal(row: Any | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row goal_record into a structured dict."""
    if row is None:
        return None

    return {
        "goal_id": row["goal_id"],
        "id": row["goal_id"],  # compatibility alias for simple callers/UI
        "tolerance_profile_id": row["tolerance_profile_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "goal_mode": row["goal_mode"],
        "raw_user_intent": row["raw_user_intent"],
        "interpreted_goal": json_loads_object(row["interpreted_goal_json"]),
        "priority": json_loads_object(row["priority_json"]),
        "acknowledged_tradeoffs": json_loads_object(row["acknowledged_tradeoffs_json"]),
        "status": row["status"],
    }


# ---------------------------------------------------------------------------
# GoalEngine
# ---------------------------------------------------------------------------

class GoalEngine:
    """
    MVP Goal Engine for four preset modes.

    The Goal Engine owns goal_record domain state. EventLogger is used only for
    append-only audit events.
    """

    SOURCE_ENGINE = EventLogger.SOURCE_GOAL

    def __init__(
        self,
        database: Database,
        event_logger: EventLogger | None = None,
    ) -> None:
        self.database = database
        self.event_logger = event_logger or EventLogger(database)

    # ------------------------------------------------------------------
    # Public metadata helpers
    # ------------------------------------------------------------------

    def list_available_modes(self) -> list[dict[str, Any]]:
        """Return metadata for all supported preset modes."""
        return [deepcopy(GOAL_MODE_METADATA[mode]) for mode in sorted(VALID_GOAL_MODES)]

    def get_mode_metadata(self, mode: str) -> dict[str, Any] | None:
        """Return metadata for one mode, or None if unknown."""
        normalised = normalise_mode(mode)
        metadata = GOAL_MODE_METADATA.get(normalised)
        return deepcopy(metadata) if metadata is not None else None

    # ------------------------------------------------------------------
    # Goal state methods
    # ------------------------------------------------------------------

    def set_goal(
        self,
        mode: str,
        parameters: JsonMapping | None = None,
    ) -> dict[str, Any]:
        """
        Set the active preset goal.

        Behaviour:
            - validates mode
            - validates parameters are Mapping/None
            - supersedes any currently active goal_record rows
            - inserts a new active goal_record
            - writes goal_updated events for superseded goals
            - writes a goal_created event for the new goal

        Returns a structured success/failure dict. Does not raise for normal
        invalid user input.
        """
        normalised_mode = normalise_mode(mode)

        if normalised_mode not in VALID_GOAL_MODES:
            return {
                "success": False,
                "error": "invalid_goal_mode",
                "mode": mode,
                "normalised_mode": normalised_mode,
                "available_modes": sorted(VALID_GOAL_MODES),
            }

        if parameters is None:
            safe_parameters: dict[str, Any] = {}
        elif isinstance(parameters, Mapping):
            safe_parameters = dict(parameters)
        else:
            return {
                "success": False,
                "error": "invalid_parameters",
                "message": "parameters must be a mapping/dict or None",
                "received_type": type(parameters).__name__,
                "available_modes": sorted(VALID_GOAL_MODES),
            }

        metadata = deepcopy(GOAL_MODE_METADATA[normalised_mode])
        now = utc_now()
        goal_id = new_id("goal")

        interpreted_goal = {
            "mode": normalised_mode,
            "display_name": metadata["display_name"],
            "intent": metadata["intent"],
            "metadata": metadata,
            "parameters": safe_parameters,
            "source": "preset_mode",
            "goal_engine_version": GOAL_ENGINE_VERSION,
        }
        priority = {
            "decision_hints": metadata.get("decision_hints", {}),
            "risk_level": metadata.get("risk_level"),
            "goal_engine_version": GOAL_ENGINE_VERSION,
        }
        acknowledged_tradeoffs = {
            "tradeoffs": metadata.get("tradeoffs", []),
            "acknowledged_by": "preset_selection",
            "goal_engine_version": GOAL_ENGINE_VERSION,
        }

        try:
            with self.database.connection() as conn:
                previous_rows = conn.execute(
                    """
                    SELECT *
                    FROM goal_record
                    WHERE status = 'active'
                    ORDER BY created_at DESC;
                    """
                ).fetchall()

                previous_goals = [
                    goal
                    for goal in (row_to_goal(row) for row in previous_rows)
                    if goal is not None
                ]

                conn.execute(
                    """
                    UPDATE goal_record
                    SET status = 'superseded',
                        updated_at = ?
                    WHERE status = 'active';
                    """,
                    (now,),
                )

                tolerance_profile_id = self._get_active_tolerance_profile_id(conn)

                conn.execute(
                    """
                    INSERT INTO goal_record (
                        goal_id,
                        tolerance_profile_id,
                        created_at,
                        updated_at,
                        goal_mode,
                        raw_user_intent,
                        interpreted_goal_json,
                        priority_json,
                        acknowledged_tradeoffs_json,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        goal_id,
                        tolerance_profile_id,
                        now,
                        now,
                        normalised_mode,
                        f"Preset selected: {metadata['display_name']}",
                        json_dumps_defensive(interpreted_goal),
                        json_dumps_defensive(priority),
                        json_dumps_defensive(acknowledged_tradeoffs),
                        "active",
                    ),
                )

            new_goal = self.get_goal(goal_id)
            if new_goal is None:
                return {
                    "success": False,
                    "error": "goal_write_not_found_after_insert",
                    "goal_id": goal_id,
                    "mode": normalised_mode,
                }

            superseded_event_ids = self._log_superseded_goal_events(
                previous_goals=previous_goals,
                superseded_at=now,
                new_goal_id=goal_id,
                new_goal_mode=normalised_mode,
            )

            event_id = self.event_logger.log_event(
                source_engine=EventLogger.SOURCE_GOAL,
                event_type=EventLogger.EVENT_GOAL_CREATED,
                payload={
                    "goal_id": goal_id,
                    "goal_mode": normalised_mode,
                    "display_name": metadata["display_name"],
                    "parameters": safe_parameters,
                    "previous_goal_ids": [goal["goal_id"] for goal in previous_goals],
                    "previous_goal_modes": [goal["goal_mode"] for goal in previous_goals],
                    "superseded_count": len(previous_goals),
                    "goal_engine_version": GOAL_ENGINE_VERSION,
                },
                severity="info",
                related_entity_type="goal_record",
                related_entity_id=goal_id,
            )

            return {
                "success": True,
                "goal": new_goal,
                "previous_goal": previous_goals[0] if previous_goals else None,
                "previous_goals": previous_goals,
                "superseded_count": len(previous_goals),
                "event_id": event_id,
                "event_logged": event_id is not None,
                "superseded_event_ids": superseded_event_ids,
            }

        except Exception as exc:  # noqa: BLE001
            logger.error("GoalEngine.set_goal failed for mode=%s: %s", normalised_mode, exc)
            self._log_goal_system_error(
                error="set_goal_failed",
                detail=str(exc),
                mode=normalised_mode,
            )
            return {
                "success": False,
                "error": "database_error",
                "mode": normalised_mode,
                "detail": str(exc),
            }

    def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        """Return one goal_record by goal_id, or None."""
        if not goal_id:
            return None

        try:
            with self.database.connection() as conn:
                row = conn.execute(
                    """
                    SELECT *
                    FROM goal_record
                    WHERE goal_id = ?;
                    """,
                    (goal_id,),
                ).fetchone()
            return row_to_goal(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("GoalEngine.get_goal failed for goal_id=%s: %s", goal_id, exc)
            return None

    def get_active_goal(self) -> dict[str, Any] | None:
        """Return the current active goal, or None if no active goal exists."""
        try:
            with self.database.connection() as conn:
                row = conn.execute(
                    """
                    SELECT *
                    FROM goal_record
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """
                ).fetchone()
            return row_to_goal(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("GoalEngine.get_active_goal failed: %s", exc)
            return None

    def get_goal_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Return recent goal records, newest first.

        Invalid limits degrade to 10 rather than raising.
        """
        try:
            safe_limit = int(limit)
            if safe_limit <= 0:
                safe_limit = 10
        except Exception:
            safe_limit = 10

        try:
            with self.database.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM goal_record
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (safe_limit,),
                ).fetchall()

            return [
                goal
                for goal in (row_to_goal(row) for row in rows)
                if goal is not None
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("GoalEngine.get_goal_history failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_active_tolerance_profile_id(conn: Any) -> str | None:
        row = conn.execute(
            """
            SELECT profile_id
            FROM user_tolerance_profile
            WHERE is_active = 1
            ORDER BY created_at DESC
            LIMIT 1;
            """
        ).fetchone()
        return row["profile_id"] if row else None

    def _log_superseded_goal_events(
        self,
        *,
        previous_goals: list[dict[str, Any]],
        superseded_at: str,
        new_goal_id: str,
        new_goal_mode: str,
    ) -> list[str]:
        """Best-effort audit events for previously active goals that were superseded."""
        event_ids: list[str] = []

        for previous_goal in previous_goals:
            event_id = self.event_logger.log_event(
                source_engine=EventLogger.SOURCE_GOAL,
                event_type=EventLogger.EVENT_GOAL_UPDATED,
                payload={
                    "goal_id": previous_goal["goal_id"],
                    "goal_mode": previous_goal["goal_mode"],
                    "status": "superseded",
                    "superseded_at": superseded_at,
                    "superseded_by_goal_id": new_goal_id,
                    "superseded_by_goal_mode": new_goal_mode,
                    "goal_engine_version": GOAL_ENGINE_VERSION,
                },
                severity="info",
                related_entity_type="goal_record",
                related_entity_id=previous_goal["goal_id"],
            )
            if event_id is not None:
                event_ids.append(event_id)

        return event_ids

    def _log_goal_system_error(self, *, error: str, detail: str, mode: str | None = None) -> None:
        """
        Best-effort error audit. EventLogger never raises; ignore the result.
        """
        self.event_logger.log_system_error(
            {
                "error": error,
                "detail": detail,
                "mode": mode,
                "source": "GoalEngine",
                "goal_engine_version": GOAL_ENGINE_VERSION,
            }
        )


__all__ = [
    "GOAL_ENGINE_VERSION",
    "GOAL_MODE_METADATA",
    "MODE_REGISTRY",
    "VALID_GOAL_MODES",
    "VALID_MODES",
    "MODE_MAXIMISE_FPS",
    "MODE_QUIET",
    "MODE_FREE_STORAGE",
    "MODE_BALANCED",
    "GoalEngine",
]


# ---------------------------------------------------------------------------
# Manual self-test
# ---------------------------------------------------------------------------

def _run_self_test(db_path: str | None = None) -> int:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    db = Database(**kwargs)
    db.initialize()

    engine = GoalEngine(db)

    sequence = [
        MODE_BALANCED,
        MODE_MAXIMISE_FPS,
        MODE_QUIET,
        MODE_FREE_STORAGE,
    ]

    print(f"Axon GoalEngine self-test  version {GOAL_ENGINE_VERSION}")
    print(f"DB: {getattr(db, 'db_path', db_path)}")
    print("-" * 60)

    failures: list[str] = []

    available_modes = engine.list_available_modes()
    print(f"Available modes: {[mode['mode'] for mode in available_modes]}")
    if len(available_modes) != 4:
        failures.append(f"Expected 4 available modes, found {len(available_modes)}")

    initial_active = engine.get_active_goal()
    print(f"Initial active goal: {initial_active}")
    if initial_active is not None:
        failures.append("Expected no active goal before set_goal() sequence")

    for mode in sequence:
        result = engine.set_goal(mode)
        active = engine.get_active_goal()
        ok = result.get("success") is True and active is not None and active["goal_mode"] == mode
        print(
            f"set_goal({mode:<14}) success={result.get('success')} "
            f"active={active['goal_mode'] if active else None} "
            f"event_logged={result.get('event_logged')}"
        )

        if not ok:
            failures.append(f"Active goal mismatch after setting {mode}")

    history = engine.get_goal_history(limit=10)
    history_modes = [goal["goal_mode"] for goal in history]
    active_rows = [goal for goal in history if goal.get("status") == "active"]
    superseded_rows = [goal for goal in history if goal.get("status") == "superseded"]

    print("-" * 60)
    print(f"History modes newest-first: {history_modes}")
    print(f"History count: {len(history)}")
    print(f"Active rows in history: {len(active_rows)}")
    print(f"Superseded rows in history: {len(superseded_rows)}")

    for mode in sequence:
        if mode not in history_modes:
            failures.append(f"Missing {mode} from goal history")

    if len(history) < len(sequence):
        failures.append(f"Expected at least {len(sequence)} history records, found {len(history)}")

    if len(active_rows) != 1:
        failures.append(f"Expected exactly one active goal, found {len(active_rows)}")

    if len(superseded_rows) < len(sequence) - 1:
        failures.append(
            f"Expected at least {len(sequence) - 1} superseded goals, found {len(superseded_rows)}"
        )

    invalid = engine.set_goal("turbo_mode")
    print(f"Invalid mode returns success=False: {invalid.get('success') is False}")
    if invalid.get("success") is not False:
        failures.append("Invalid mode did not return structured failure")

    invalid_parameters = engine.set_goal(MODE_BALANCED, parameters="not_a_dict")  # type: ignore[arg-type]
    print(f"Invalid parameters return success=False: {invalid_parameters.get('success') is False}")
    if invalid_parameters.get("success") is not False:
        failures.append("Invalid parameters did not return structured failure")

    metadata = engine.get_mode_metadata("maximise-fps")
    print(f"Hyphenated mode metadata lookup works: {metadata is not None}")
    if metadata is None or metadata.get("mode") != MODE_MAXIMISE_FPS:
        failures.append("Mode normalisation failed for maximise-fps metadata lookup")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f" - {failure}")
        return 2

    print("GoalEngine self-test passed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Axon S6 GoalEngine self-test.")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite DB path. Defaults to Database() project data path.",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Optional Axon project root. Defaults to database.find_project_root().",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.project_root:
        project_root = find_project_root(Path(args.project_root))
        database = Database(db_path=args.db_path, project_root=project_root)
        database.initialize()
        engine = GoalEngine(database)

        failures: list[str] = []
        for mode in [MODE_BALANCED, MODE_MAXIMISE_FPS, MODE_QUIET, MODE_FREE_STORAGE]:
            result = engine.set_goal(mode)
            active = engine.get_active_goal()
            print(
                f"set_goal({mode:<14}) success={result.get('success')} "
                f"active={active['goal_mode'] if active else None}"
            )
            if result.get("success") is not True:
                failures.append(f"set_goal failed for {mode}")

        history = engine.get_goal_history(limit=10)
        print(f"History count: {len(history)}")
        print(f"Active rows: {sum(1 for goal in history if goal.get('status') == 'active')}")
        raise SystemExit(2 if failures else 0)

    raise SystemExit(_run_self_test(args.db_path))
