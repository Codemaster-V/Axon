# ============================================================
# AXON — Observation Engine
# Version: 0.1
# Created: 2026-05-18
# ============================================================
# Responsibilities:
#   - Collect system telemetry (CPU, RAM, GPU, thermals, disk)
#   - Enumerate running processes and startup apps
#   - Take system snapshots (used for rollback and baselining)
#   - Log all observations to the event log
#
# Design principles:
#   - Clean class boundaries so a C# wrapper can replace this layer later
#   - All public methods return plain dicts or lists (no internal types leaked)
#   - Graceful degradation: if a metric is unavailable, return None (not crash)
#   - All activity is logged to the event_log table
# ============================================================

import sqlite3
import psutil
import json
import platform
import datetime
import os
import subprocess
from typing import Optional

# ============================================================
# DATABASE CONNECTION HELPER
# ============================================================

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """
    Returns a SQLite connection with row factory set so results
    come back as dictionaries — easier to work with and easier
    to port to C# later.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_database(db_path: str, schema_path: str) -> None:
    """
    Initialises the database from the SQL schema file.
    Safe to run multiple times — uses CREATE IF NOT EXISTS.
    """
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    conn = get_db_connection(db_path)
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    print(f"[Axon] Database initialised at: {db_path}")


# ============================================================
# EVENT LOGGER
# Thin wrapper so every engine can log events consistently.
# ============================================================

class EventLogger:
    """
    Writes to the event_log table.
    All engines use this — it is the system's memory layer.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def log(
        self,
        event_type: str,
        source: str,
        payload: Optional[dict] = None,
        related_goal_id: Optional[int] = None,
        related_action_id: Optional[int] = None,
    ) -> int:
        """
        Writes one event to the event_log.
        Returns the new event id.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.execute(
            """
            INSERT INTO event_log (event_type, source, payload, related_goal_id, related_action_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                source,
                json.dumps(payload) if payload else None,
                related_goal_id,
                related_action_id,
            ),
        )
        conn.commit()
        event_id = cursor.lastrowid
        conn.close()
        return event_id


# ============================================================
# OBSERVATION ENGINE
# ============================================================

class ObservationEngine:
    """
    Collects telemetry, usage patterns, hardware state, and
    app behaviour. First engine to be implemented per DOC2.

    All public methods return plain Python dicts or lists so
    the data is easy to serialise, test, and hand to other
    engines or a future C# layer.
    """

    SOURCE = "observation_engine"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = EventLogger(db_path)

    # --------------------------------------------------------
    # DEVICE PROFILE
    # --------------------------------------------------------

    def collect_device_profile(self) -> dict:
        """
        Collects hardware fingerprint.
        Stores in device_profile table if not already present.
        Returns the profile as a dict.
        """
        cpu_freq = psutil.cpu_freq()
        ram = psutil.virtual_memory()
        disk_partitions = psutil.disk_partitions()

        drives = []
        for partition in disk_partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                })
            except PermissionError:
                # Some system partitions are inaccessible — skip gracefully
                pass

        # GPU info: attempt via WMI on Windows; fallback gracefully
        gpu_name, gpu_vram_gb = self._get_gpu_info()

        profile = {
            "device_name": platform.node(),
            "os_version": f"{platform.system()} {platform.release()} {platform.version()}",
            "cpu_name": platform.processor(),
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "cpu_cores_logical": psutil.cpu_count(logical=True),
            "cpu_base_clock_mhz": round(cpu_freq.max, 2) if cpu_freq else None,
            "ram_total_gb": round(ram.total / (1024 ** 3), 2),
            "gpu_name": gpu_name,
            "gpu_vram_gb": gpu_vram_gb,
            "storage_drives": json.dumps(drives),
        }

        # Save to DB (upsert by device name)
        conn = get_db_connection(self.db_path)
        existing = conn.execute(
            "SELECT id FROM device_profile WHERE device_name = ?",
            (profile["device_name"],)
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE device_profile SET
                    os_version=?, cpu_name=?, cpu_cores_physical=?, cpu_cores_logical=?,
                    cpu_base_clock_mhz=?, ram_total_gb=?, gpu_name=?, gpu_vram_gb=?,
                    storage_drives=?, updated_at=datetime('now')
                WHERE device_name=?
                """,
                (
                    profile["os_version"], profile["cpu_name"],
                    profile["cpu_cores_physical"], profile["cpu_cores_logical"],
                    profile["cpu_base_clock_mhz"], profile["ram_total_gb"],
                    profile["gpu_name"], profile["gpu_vram_gb"],
                    profile["storage_drives"], profile["device_name"],
                )
            )
        else:
            conn.execute(
                """
                INSERT INTO device_profile
                    (device_name, os_version, cpu_name, cpu_cores_physical, cpu_cores_logical,
                     cpu_base_clock_mhz, ram_total_gb, gpu_name, gpu_vram_gb, storage_drives)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile["device_name"], profile["os_version"], profile["cpu_name"],
                    profile["cpu_cores_physical"], profile["cpu_cores_logical"],
                    profile["cpu_base_clock_mhz"], profile["ram_total_gb"],
                    profile["gpu_name"], profile["gpu_vram_gb"],
                    profile["storage_drives"],
                )
            )

        conn.commit()
        conn.close()

        self.logger.log(
            event_type="device_profile_collected",
            source=self.SOURCE,
            payload={"device_name": profile["device_name"], "os_version": profile["os_version"]},
        )

        return profile

    def _get_gpu_info(self) -> tuple:
        """
        Attempts to get GPU name and VRAM via WMI on Windows.
        Returns (None, None) gracefully if unavailable.
        This is isolated so it's easy to replace with a better
        method later (e.g. GPUtil, vendor-specific APIs).
        """
        try:
            import wmi
            w = wmi.WMI()
            gpus = w.Win32_VideoController()
            if gpus:
                gpu = gpus[0]
                vram_gb = round(int(gpu.AdapterRAM) / (1024 ** 3), 2) if gpu.AdapterRAM else None
                return gpu.Name, vram_gb
        except Exception:
            pass
        return None, None

    # --------------------------------------------------------
    # SYSTEM SNAPSHOT
    # --------------------------------------------------------

    def take_snapshot(self, snapshot_type: str = "scheduled", notes: str = None) -> dict:
        """
        Captures a point-in-time system state.
        Used before any action (for rollback) and on schedule (for baselining).
        Returns the snapshot as a dict including its database id.
        """
        cpu_pct = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/") if os.name != "nt" else psutil.disk_usage("C:\\")

        # Temperatures — graceful fallback if unavailable
        cpu_temp, gpu_temp = self._get_temperatures()

        # GPU usage — graceful fallback
        gpu_usage_pct, gpu_vram_used_gb = self._get_gpu_usage()

        # Running processes (top 20 by memory)
        processes = self._get_running_processes(limit=20)

        # Startup apps (Windows only)
        startup_apps = self._get_startup_apps()

        # Current power profile
        power_profile = self._get_power_profile()

        snapshot = {
            "snapshot_type": snapshot_type,
            "cpu_usage_pct": cpu_pct,
            "ram_usage_pct": ram.percent,
            "ram_used_gb": round(ram.used / (1024 ** 3), 2),
            "gpu_usage_pct": gpu_usage_pct,
            "gpu_vram_used_gb": gpu_vram_used_gb,
            "cpu_temp_c": cpu_temp,
            "gpu_temp_c": gpu_temp,
            "active_processes": json.dumps(processes),
            "startup_apps": json.dumps(startup_apps),
            "power_profile": power_profile,
            "storage_free_gb": round(disk.free / (1024 ** 3), 2),
            "notes": notes,
        }

        conn = get_db_connection(self.db_path)
        cursor = conn.execute(
            """
            INSERT INTO system_snapshot
                (snapshot_type, cpu_usage_pct, ram_usage_pct, ram_used_gb,
                 gpu_usage_pct, gpu_vram_used_gb, cpu_temp_c, gpu_temp_c,
                 active_processes, startup_apps, power_profile, storage_free_gb, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["snapshot_type"], snapshot["cpu_usage_pct"],
                snapshot["ram_usage_pct"], snapshot["ram_used_gb"],
                snapshot["gpu_usage_pct"], snapshot["gpu_vram_used_gb"],
                snapshot["cpu_temp_c"], snapshot["gpu_temp_c"],
                snapshot["active_processes"], snapshot["startup_apps"],
                snapshot["power_profile"], snapshot["storage_free_gb"],
                snapshot["notes"],
            )
        )
        conn.commit()
        snapshot["id"] = cursor.lastrowid
        conn.close()

        self.logger.log(
            event_type="snapshot_taken",
            source=self.SOURCE,
            payload={
                "snapshot_id": snapshot["id"],
                "snapshot_type": snapshot_type,
                "cpu_pct": cpu_pct,
                "ram_pct": ram.percent,
            },
        )

        return snapshot

    def _get_temperatures(self) -> tuple:
        """
        Attempts to read CPU and GPU temperatures.
        Returns (cpu_temp, gpu_temp) — either may be None.
        Temperature access varies by hardware vendor and Windows config.
        """
        cpu_temp = None
        gpu_temp = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Try common keys
                for key in ["coretemp", "cpu_thermal", "k10temp", "acpitz"]:
                    if key in temps:
                        readings = temps[key]
                        if readings:
                            cpu_temp = readings[0].current
                            break
        except (AttributeError, NotImplementedError):
            # psutil.sensors_temperatures() not available on all platforms
            pass
        return cpu_temp, gpu_temp

    def _get_gpu_usage(self) -> tuple:
        """
        Attempts to get GPU utilisation and VRAM usage.
        Returns (gpu_usage_pct, gpu_vram_used_gb) — either may be None.
        Isolated for easy replacement with vendor-specific APIs.
        """
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                return round(gpu.load * 100, 1), round(gpu.memoryUsed / 1024, 2)
        except Exception:
            pass
        return None, None

    def _get_running_processes(self, limit: int = 20) -> list:
        """
        Returns top N processes by memory usage.
        Only captures safe, non-sensitive fields.
        """
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
            try:
                info = proc.info
                processes.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_pct": info["cpu_percent"],
                    "ram_mb": round(info["memory_info"].rss / (1024 ** 2), 1) if info["memory_info"] else None,
                    "status": info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process ended or inaccessible — skip gracefully
                pass

        # Sort by RAM usage descending, return top N
        processes.sort(key=lambda x: x.get("ram_mb") or 0, reverse=True)
        return processes[:limit]

    def _get_startup_apps(self) -> list:
        """
        Returns startup apps on Windows via registry query.
        Returns empty list gracefully on non-Windows or if access denied.
        """
        startup_apps = []
        if os.name != "nt":
            return startup_apps
        try:
            result = subprocess.run(
                ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("HKEY"):
                    parts = line.split(None, 2)
                    if len(parts) >= 3:
                        startup_apps.append({
                            "name": parts[0],
                            "type": parts[1],
                            "path": parts[2],
                        })
        except Exception:
            pass
        return startup_apps

    def _get_power_profile(self) -> Optional[str]:
        """
        Returns the current Windows power plan name.
        Returns None gracefully on non-Windows or error.
        """
        if os.name != "nt":
            return None
        try:
            result = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True, text=True, timeout=5
            )
            # Output format: "Power Scheme GUID: <guid>  (<name>)"
            output = result.stdout
            if "(" in output and ")" in output:
                return output.split("(")[-1].split(")")[0].strip()
        except Exception:
            pass
        return None

    # --------------------------------------------------------
    # LIVE TELEMETRY READING
    # --------------------------------------------------------

    def get_live_telemetry(self) -> dict:
        """
        Returns a lightweight real-time reading without saving to DB.
        Used for the UI dashboard and simulation estimates.
        """
        cpu_pct = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        cpu_temp, gpu_temp = self._get_temperatures()
        gpu_usage_pct, gpu_vram_used_gb = self._get_gpu_usage()

        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "cpu_usage_pct": cpu_pct,
            "ram_usage_pct": ram.percent,
            "ram_used_gb": round(ram.used / (1024 ** 3), 2),
            "ram_total_gb": round(ram.total / (1024 ** 3), 2),
            "gpu_usage_pct": gpu_usage_pct,
            "gpu_vram_used_gb": gpu_vram_used_gb,
            "cpu_temp_c": cpu_temp,
            "gpu_temp_c": gpu_temp,
        }


# ============================================================
# QUICK SELF-TEST
# Run this file directly to verify everything works:
#   python observation_engine.py
# ============================================================

if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("AXON — Observation Engine Self-Test")
    print("=" * 60)

    # Use a temp DB for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "axon_test.db")
        schema_path = os.path.join(os.path.dirname(__file__), "axon_schema.sql")

        print(f"\n[1] Initialising database at {db_path}")
        init_database(db_path, schema_path)

        engine = ObservationEngine(db_path)

        print("\n[2] Collecting device profile...")
        profile = engine.collect_device_profile()
        print(f"    Device:  {profile['device_name']}")
        print(f"    OS:      {profile['os_version']}")
        print(f"    CPU:     {profile['cpu_name']}")
        print(f"    Cores:   {profile['cpu_cores_physical']} physical / {profile['cpu_cores_logical']} logical")
        print(f"    RAM:     {profile['ram_total_gb']} GB")
        print(f"    GPU:     {profile['gpu_name'] or 'Not detected'}")

        print("\n[3] Taking baseline snapshot...")
        snapshot = engine.take_snapshot(snapshot_type="baseline", notes="Self-test baseline")
        print(f"    Snapshot ID:  {snapshot['id']}")
        print(f"    CPU Usage:    {snapshot['cpu_usage_pct']}%")
        print(f"    RAM Usage:    {snapshot['ram_usage_pct']}%")
        print(f"    RAM Used:     {snapshot['ram_used_gb']} GB")
        print(f"    CPU Temp:     {snapshot['cpu_temp_c'] or 'N/A'} °C")
        print(f"    Power Plan:   {snapshot['power_profile'] or 'N/A'}")
        print(f"    Free Storage: {snapshot['storage_free_gb']} GB")

        print("\n[4] Reading live telemetry...")
        live = engine.get_live_telemetry()
        print(f"    Timestamp:  {live['timestamp']}")
        print(f"    CPU:        {live['cpu_usage_pct']}%")
        print(f"    RAM:        {live['ram_usage_pct']}% ({live['ram_used_gb']} / {live['ram_total_gb']} GB)")

        print("\n[5] Checking event log...")
        conn = get_db_connection(db_path)
        events = conn.execute("SELECT event_type, source, created_at FROM event_log").fetchall()
        conn.close()
        for event in events:
            print(f"    [{event['created_at']}] {event['source']} → {event['event_type']}")

    print("\n" + "=" * 60)
    print("Self-test complete. All systems nominal.")
    print("=" * 60)
