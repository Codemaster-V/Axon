"""
AXON S3 — Observation Engine Collectors

Location:
    src/axon/engines/observation_engine/collectors.py

Purpose:
    Read-only system telemetry collection for the Axon MVP.

Scope:
    - Collect CPU, RAM, disk, network, power, process, startup-app,
      environmental context, temperature, and GPU-adjacent telemetry where available.
    - Return structured, JSON-serialisable dictionaries.
    - Perform no database writes.
    - Perform no system changes.

Non-negotiable S3 safety boundary:
    - Never modify system state.
    - Never suspend processes.
    - Never change startup entries.
    - Never change registry values.
    - Never change power plans.
    - Never delete or clean files.
    - Never overclock, undervolt, or interact with drivers/BIOS/firmware.

Design notes:
    - psutil is the primary telemetry library.
    - Windows-only collectors degrade gracefully on non-Windows systems.
    - GPU telemetry remains best-effort. Adapter detection is not treated as
      the same thing as usable GPU load/temperature telemetry.
    - Every collector returns a dict/list structure that can be JSON encoded.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import platform
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


logger = logging.getLogger(__name__)


try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - exercised through degraded runtime path
    psutil = None  # type: ignore


JsonDict = dict[str, Any]

COLLECTOR_VERSION = "0.2.0-s3-merged"
DEFAULT_PROCESS_LIMIT = 100
DEFAULT_COMMAND_TIMEOUT_SECONDS = 2.5


def utc_now_iso() -> str:
    """Return a compact UTC timestamp suitable for event/snapshot storage."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_now_iso() -> str:
    """Return local system time in ISO format for human/contextual debugging."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def bytes_to_gib(value: int | float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / (1024**3), 3)
    except (TypeError, ValueError, OverflowError):
        return None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = (
            value.strip()
            .replace("%", "")
            .replace("MiB", "")
            .replace("Mib", "")
            .replace("MB", "")
            .replace("mb", "")
        )
        if cleaned.upper() in {"N/A", "NA", "NONE", ""}:
            return None
        value = cleaned

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    numeric = safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


def unavailable(reason: str, provider: str | None = None) -> JsonDict:
    return {
        "available": False,
        "provider": provider,
        "error": reason,
    }


def available(provider: str | None = None, **payload: Any) -> JsonDict:
    result: JsonDict = {
        "available": True,
        "provider": provider,
    }
    result.update(payload)
    return result


class SystemCollectors:
    """
    Read-only telemetry collector for Axon's Observation Engine.

    The class intentionally does not depend on the database layer.
    Persistence belongs in database.py / later orchestration code.
    """

    def __init__(
        self,
        *,
        process_limit: int = DEFAULT_PROCESS_LIMIT,
        include_exe_paths: bool = False,
        include_active_window_title: bool = False,
        measure_disk_throughput: bool = False,
        command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        self.process_limit = max(0, process_limit)
        self.include_exe_paths = include_exe_paths
        self.include_active_window_title = include_active_window_title
        self.measure_disk_throughput = measure_disk_throughput
        self.command_timeout_seconds = command_timeout_seconds

    # ------------------------------------------------------------------
    # Snapshot assembly
    # ------------------------------------------------------------------

    def collect_system_snapshot(self) -> JsonDict:
        """
        Collect a complete read-only system snapshot.

        Return shape is designed for the S2 system_snapshot table:
            - scalar columns:
                cpu_usage_percent
                ram_usage_percent
                disk_usage_percent
            - JSON blobs:
                snapshot_data
                environmental_context

        No database writes occur here.
        """
        collection_errors: list[JsonDict] = []

        def safe_collect(name: str, collector: Callable[[], JsonDict]) -> JsonDict:
            try:
                return collector()
            except Exception as exc:  # defensive: one bad collector must not kill snapshot
                logger.debug("%s collector failed: %s", name, exc)
                error_payload = {
                    "collector": name,
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
                collection_errors.append(error_payload)
                return unavailable(f"{name} collector failed: {exc.__class__.__name__}: {exc}")

        cpu_data = safe_collect("cpu", self.collect_cpu)
        memory_data = safe_collect("memory", self.collect_memory)
        disk_data = safe_collect("disk", self.collect_disks)
        network_data = safe_collect("network", self.collect_network)
        power_data = safe_collect("power", self.collect_power)
        temperatures_data = safe_collect("temperatures", self.collect_temperatures)
        gpu_data = safe_collect("gpu", self.collect_gpu)
        process_data = safe_collect("processes", self.collect_processes)
        startup_data = safe_collect("startup_apps", self.collect_startup_apps)
        device_profile = safe_collect("device_profile", self.collect_device_profile)
        environmental_context = safe_collect("environmental_context", self.collect_environmental_context)

        cpu_usage_percent = cpu_data.get("usage_percent") if cpu_data.get("available") else None

        ram_usage_percent = None
        if memory_data.get("available"):
            virtual_memory = memory_data.get("virtual", {})
            if isinstance(virtual_memory, dict):
                ram_usage_percent = virtual_memory.get("percent")

        disk_usage_percent = None
        if disk_data.get("available"):
            drives = disk_data.get("partitions", [])
            usage_values = []
            for drive in drives:
                if not isinstance(drive, dict):
                    continue
                usage = drive.get("usage", {})
                if isinstance(usage, dict) and usage.get("percent") is not None:
                    usage_values.append(usage["percent"])
            if usage_values:
                disk_usage_percent = max(usage_values)

        snapshot_data: JsonDict = {
            "collector_version": COLLECTOR_VERSION,
            "collected_at_utc": utc_now_iso(),
            "collection_scope": "read_only_observation",
            "device_profile": device_profile,
            "cpu": cpu_data,
            "memory": memory_data,
            "disk": disk_data,
            "network": network_data,
            "power": power_data,
            "temperatures": temperatures_data,
            "gpu": gpu_data,
            "processes": process_data,
            "startup_apps": startup_data,
            "collection_errors": collection_errors,
        }

        return {
            "cpu_usage_percent": cpu_usage_percent,
            "ram_usage_percent": ram_usage_percent,
            "disk_usage_percent": disk_usage_percent,
            "snapshot_data": snapshot_data,
            "environmental_context": environmental_context,
        }

    # ------------------------------------------------------------------
    # Core collectors
    # ------------------------------------------------------------------

    def collect_device_profile(self) -> JsonDict:
        boot_time_utc: str | None = None

        if psutil is not None:
            try:
                boot_time_utc = (
                    datetime.fromtimestamp(psutil.boot_time(), timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )
            except Exception as exc:
                logger.debug("Boot time collection failed: %s", exc)
                boot_time_utc = None

        return available(
            "platform",
            hostname=socket.gethostname(),
            os={
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": sys.version.split()[0],
            },
            boot_time_utc=boot_time_utc,
            axon_process={
                "pid": os.getpid(),
                "cwd": str(Path.cwd()),
            },
        )

    def collect_cpu(self) -> JsonDict:
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        freq_payload: JsonDict | None = None
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                freq_payload = {
                    "current_mhz": safe_float(freq.current),
                    "min_mhz": safe_float(freq.min),
                    "max_mhz": safe_float(freq.max),
                }
        except Exception as exc:
            logger.debug("CPU frequency collection failed: %s", exc)
            freq_payload = None

        load_average: JsonDict | None = None
        try:
            one, five, fifteen = os.getloadavg()
            load_average = {
                "one_min": round(one, 3),
                "five_min": round(five, 3),
                "fifteen_min": round(fifteen, 3),
            }
        except (AttributeError, OSError):
            # Expected on Windows. Kept because it is useful if Axon tooling is
            # ever smoke-tested on Linux/macOS.
            load_average = None

        temperature_celsius: float | None = None
        try:
            sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
            if sensors_temperatures is not None:
                sensors = sensors_temperatures(fahrenheit=False)
                if sensors:
                    for key in ("coretemp", "k10temp"):
                        if key in sensors and sensors[key]:
                            temperature_celsius = safe_float(getattr(sensors[key][0], "current", None))
                            break
                    if temperature_celsius is None:
                        first_key = next(iter(sensors))
                        if sensors[first_key]:
                            temperature_celsius = safe_float(getattr(sensors[first_key][0], "current", None))
        except Exception as exc:
            logger.debug("CPU temperature collection failed or unavailable: %s", exc)
            temperature_celsius = None

        try:
            cpu_times = psutil.cpu_times_percent(interval=None, percpu=False)
            cpu_times_payload = cpu_times._asdict()
        except Exception:
            cpu_times_payload = None

        try:
            # Intentional two-step sampling:
            # - overall CPU is sampled over a short blocking interval.
            # - per-core CPU uses psutil's last-call window immediately after.
            # They are close enough for S3 observation but not treated as a
            # precise scientific sample pair.
            usage_percent = psutil.cpu_percent(interval=0.15)
            per_cpu_percent = psutil.cpu_percent(interval=None, percpu=True)

            return available(
                "psutil",
                usage_percent=round(float(usage_percent), 1),
                per_cpu_percent=[round(float(value), 1) for value in per_cpu_percent],
                logical_cores=psutil.cpu_count(logical=True),
                physical_cores=psutil.cpu_count(logical=False),
                frequency=freq_payload,
                temperature_celsius=round(temperature_celsius, 1) if temperature_celsius is not None else None,
                load_average=load_average,
                cpu_times_percent=cpu_times_payload,
            )
        except Exception as exc:
            logger.debug("CPU collection failed: %s", exc)
            return unavailable(str(exc), provider="psutil")

    def collect_memory(self) -> JsonDict:
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        try:
            virtual = psutil.virtual_memory()
            swap = psutil.swap_memory()

            return available(
                "psutil",
                virtual={
                    "total_bytes": virtual.total,
                    "available_bytes": virtual.available,
                    "used_bytes": virtual.used,
                    "free_bytes": virtual.free,
                    "total_gib": bytes_to_gib(virtual.total),
                    "available_gib": bytes_to_gib(virtual.available),
                    "used_gib": bytes_to_gib(virtual.used),
                    "percent": round(float(virtual.percent), 1),
                },
                swap={
                    "total_bytes": swap.total,
                    "used_bytes": swap.used,
                    "free_bytes": swap.free,
                    "total_gib": bytes_to_gib(swap.total),
                    "used_gib": bytes_to_gib(swap.used),
                    "free_gib": bytes_to_gib(swap.free),
                    "percent": round(float(swap.percent), 1),
                },
            )
        except Exception as exc:
            logger.debug("Memory collection failed: %s", exc)
            return unavailable(str(exc), provider="psutil")

    def collect_disks(self) -> JsonDict:
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        partitions: list[JsonDict] = []
        warnings: list[JsonDict] = []

        try:
            disk_partitions = psutil.disk_partitions(all=False)
        except Exception as exc:
            disk_partitions = []
            warnings.append(
                {
                    "collector": "disk_partitions",
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
            )

        for partition in disk_partitions:
            partition_payload: JsonDict = {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "opts": partition.opts,
                "available": True,
            }

            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partition_payload["usage"] = {
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "total_gib": bytes_to_gib(usage.total),
                    "used_gib": bytes_to_gib(usage.used),
                    "free_gib": bytes_to_gib(usage.free),
                    "percent": round(float(usage.percent), 1),
                }
            except (PermissionError, OSError) as exc:
                partition_payload["available"] = False
                partition_payload["error"] = f"{exc.__class__.__name__}: {exc}"

            partitions.append(partition_payload)

        io_snapshot: JsonDict | None = None
        throughput: JsonDict | None = None

        try:
            io_before = psutil.disk_io_counters(perdisk=False)
            if io_before is not None:
                io_snapshot = io_before._asdict()

            # Disk I/O counters are cumulative since boot, not bytes/sec.
            # Current throughput requires two readings over an interval.
            # In normal S3 snapshots this is disabled to avoid slowing every
            # collection. A later observation loop can calculate deltas across
            # repeated snapshots more cleanly.
            if self.measure_disk_throughput:
                import time

                interval_seconds = 0.5
                time.sleep(interval_seconds)
                io_after = psutil.disk_io_counters(perdisk=False)
                if io_before is not None and io_after is not None:
                    throughput = {
                        "interval_seconds": interval_seconds,
                        "read_bytes_per_sec": round(
                            (io_after.read_bytes - io_before.read_bytes) / interval_seconds
                        ),
                        "write_bytes_per_sec": round(
                            (io_after.write_bytes - io_before.write_bytes) / interval_seconds
                        ),
                    }
        except Exception as exc:
            warnings.append(
                {
                    "collector": "disk_io",
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
            )

        return available(
            "psutil",
            partitions=partitions,
            disk_io_snapshot=io_snapshot,
            throughput=throughput,
            throughput_note=(
                "disk_io_snapshot is cumulative since boot. "
                "Set measure_disk_throughput=True for a short blocking bytes/sec estimate, "
                "or calculate deltas in the later observation loop."
            ),
            warnings=warnings,
        )

    def collect_network(self) -> JsonDict:
        """
        Collect network I/O counters.

        Network telemetry was not a core S3 requirement, but it is read-only,
        non-invasive, and useful for future performance explanations.
        IP and MAC addresses are intentionally not collected.
        """
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        per_nic_io: JsonDict = {}
        per_nic_stats: JsonDict = {}

        try:
            net_io = psutil.net_io_counters(pernic=True)
            per_nic_io = {nic: counters._asdict() for nic, counters in net_io.items()}
        except Exception as exc:
            logger.debug("Per-interface network I/O collection failed: %s", exc)

        try:
            net_stats = psutil.net_if_stats()
            per_nic_stats = {nic: stats._asdict() for nic, stats in net_stats.items()}
        except Exception as exc:
            logger.debug("Network interface stats collection failed: %s", exc)

        total_io: JsonDict | None = None
        try:
            total = psutil.net_io_counters(pernic=False)
            if total is not None:
                total_io = total._asdict()
        except Exception as exc:
            logger.debug("Total network I/O collection failed: %s", exc)

        return available(
            "psutil",
            total_io=total_io,
            per_interface_io=per_nic_io,
            interface_stats=per_nic_stats,
            privacy_note="IP and MAC addresses are intentionally not collected in S3.",
        )

    def collect_power(self) -> JsonDict:
        battery_payload = self._collect_battery()
        power_scheme = self._collect_windows_power_scheme()

        return available(
            "psutil + powercfg",
            battery=battery_payload,
            active_power_scheme=power_scheme,
        )

    def collect_temperatures(self) -> JsonDict:
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
        if sensors_temperatures is None:
            return unavailable("psutil.sensors_temperatures is not available on this platform", provider="psutil")

        try:
            raw_temps = sensors_temperatures(fahrenheit=False)
        except Exception as exc:
            return unavailable(
                f"Temperature collection failed or unavailable: {exc.__class__.__name__}: {exc}",
                provider="psutil",
            )

        if not raw_temps:
            return unavailable("No temperature sensors reported by psutil", provider="psutil")

        sensors: JsonDict = {}
        for sensor_name, entries in raw_temps.items():
            sensors[sensor_name] = []
            for entry in entries:
                sensors[sensor_name].append(
                    {
                        "label": getattr(entry, "label", None),
                        "current_c": safe_float(getattr(entry, "current", None)),
                        "high_c": safe_float(getattr(entry, "high", None)),
                        "critical_c": safe_float(getattr(entry, "critical", None)),
                    }
                )

        return available("psutil", sensors=sensors)

    def collect_gpu(self) -> JsonDict:
        """
        Collect GPU telemetry where available.

        Provider order:
            1. nvidia-smi subprocess path
            2. GPUtil optional library
            3. pynvml optional library
            4. Windows adapter detection via PowerShell CIM / WMI-style data

        Adapter detection is useful, but it is not the same as true telemetry.
        WMI/CIM adapter detection usually cannot provide reliable GPU load,
        used VRAM, free VRAM, or temperature.
        """
        provider_attempts: list[JsonDict] = []

        for collector in (
            self._collect_gpu_nvidia_smi,
            self._collect_gpu_gputil,
            self._collect_gpu_pynvml,
        ):
            result = collector()
            provider_attempts.append(
                {
                    "provider": result.get("provider"),
                    "available": result.get("available"),
                    "error": result.get("error"),
                }
            )
            if result.get("available"):
                adapters = self._collect_windows_video_adapters()
                return available(
                    result.get("provider"),
                    telemetry_available=True,
                    telemetry=result.get("gpus", []),
                    detected_adapters=adapters.get("adapters", []),
                    adapter_detection=adapters,
                    provider_attempts=provider_attempts,
                    limitations=[
                        "GPU telemetry remains best-effort until validated on real NVIDIA, AMD, and Intel hardware.",
                    ],
                )

        adapters = self._collect_windows_video_adapters()
        adapter_available = bool(adapters.get("available") and adapters.get("adapters"))

        return {
            "available": adapter_available,
            "provider": "PowerShell CIM adapter detection" if adapter_available else None,
            "telemetry_available": False,
            "error": None if adapter_available else "No supported GPU telemetry provider available",
            "telemetry": [],
            "detected_adapters": adapters.get("adapters", []),
            "adapter_detection": adapters,
            "provider_attempts": provider_attempts,
            "limitations": [
                "Adapter detection is not GPU telemetry.",
                "Do not infer GPU load, temperature, or VRAM usage when telemetry_available is false.",
                "ASSUMPTION-006 remains open until tested on NVIDIA, AMD, and Intel Windows hardware.",
            ],
        }

    def collect_processes(self) -> JsonDict:
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        processes: list[JsonDict] = []
        skipped: list[JsonDict] = []

        attrs = [
            "pid",
            "name",
            "status",
            "create_time",
            "cpu_percent",
            "memory_percent",
            "num_threads",
        ]

        if self.include_exe_paths:
            attrs.append("exe")

        try:
            iterator = psutil.process_iter(attrs=attrs)
        except Exception as exc:
            logger.debug("process_iter failed: %s", exc)
            return unavailable(str(exc), provider="psutil")

        for proc in iterator:
            try:
                info = proc.info

                process_payload: JsonDict = {
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "status": info.get("status"),
                    "cpu_percent": safe_float(info.get("cpu_percent")),
                    "memory_percent": safe_float(info.get("memory_percent")),
                    "num_threads": info.get("num_threads"),
                    "create_time_utc": self._timestamp_to_utc(info.get("create_time")),
                }

                if self.include_exe_paths:
                    process_payload["exe"] = info.get("exe")

                processes.append(process_payload)

            except psutil.NoSuchProcess:
                skipped.append({"reason": "NoSuchProcess"})
            except psutil.AccessDenied:
                skipped.append({"pid": getattr(proc, "pid", None), "reason": "AccessDenied"})
            except Exception as exc:
                skipped.append(
                    {
                        "pid": getattr(proc, "pid", None),
                        "reason": f"{exc.__class__.__name__}: {exc}",
                    }
                )

        processes.sort(
            key=lambda item: (
                item.get("cpu_percent") or 0.0,
                item.get("memory_percent") or 0.0,
            ),
            reverse=True,
        )

        limited_processes = processes[: self.process_limit] if self.process_limit else []

        return available(
            "psutil",
            process_count_seen=len(processes),
            process_count_returned=len(limited_processes),
            limit=self.process_limit,
            processes=limited_processes,
            skipped_count=len(skipped),
            skipped_examples=skipped[:10],
            privacy_note="Command-line arguments and user names are intentionally not collected in S3.",
            sample_note="Per-process cpu_percent may be zero on first sample; later observation loops can prime this.",
        )

    def collect_startup_apps(self) -> JsonDict:
        """
        Read startup entries without modifying them.

        Registry reads are observational only. This method never writes to
        registry and never disables startup items.
        """
        registry_entries = self._read_windows_startup_registry()
        folder_entries = self._read_windows_startup_folders()

        registry_count = len(registry_entries.get("entries", [])) if isinstance(registry_entries, dict) else 0
        folder_count = len(folder_entries.get("entries", [])) if isinstance(folder_entries, dict) else 0

        return available(
            "Windows registry read + Startup folders",
            registry=registry_entries,
            folders=folder_entries,
            total_entries=registry_count + folder_count,
            safety_note="Read-only enumeration only. No startup entries are changed in S3.",
        )

    def collect_environmental_context(self) -> JsonDict:
        """
        Return contextual metadata about the current system session.

        active_window_title is excluded by default. It can reveal private
        document names, browser tabs, emails, or banking pages.
        """
        context: JsonDict = {
            "available": True,
            "provider": "platform + psutil",
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python_version": sys.version.split()[0],
            "collection_timestamp_utc": utc_now_iso(),
            "collection_timestamp_local": local_now_iso(),
            "time_of_day_local": datetime.now().astimezone().strftime("%H:%M:%S"),
            "weekday_local": datetime.now().astimezone().strftime("%A"),
        }

        if psutil is not None:
            try:
                boot_time = psutil.boot_time()
                context["session_uptime_seconds"] = round(datetime.now().timestamp() - boot_time)
                context["boot_time_utc"] = self._timestamp_to_utc(boot_time)
            except Exception:
                context["session_uptime_seconds"] = None
                context["boot_time_utc"] = None

        context["battery"] = self._collect_battery()

        if self.include_active_window_title:
            context["active_window_title"] = self._collect_active_window_title()
            context["active_window_title_privacy_note"] = (
                "Active window title collection is opt-in because it may expose private user data."
            )
        else:
            context["active_window_title"] = None
            context["active_window_title_privacy_note"] = (
                "Not collected by default for privacy."
            )

        return context

    # ------------------------------------------------------------------
    # Windows / optional-provider helpers
    # ------------------------------------------------------------------

    def _collect_battery(self) -> JsonDict:
        if psutil is None:
            return unavailable("psutil is not installed", provider="psutil")

        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return unavailable("Battery data unavailable or system has no battery", provider="psutil")

            seconds_left = battery.secsleft
            if hasattr(psutil, "POWER_TIME_UNLIMITED") and seconds_left == psutil.POWER_TIME_UNLIMITED:
                seconds_left = None
            elif hasattr(psutil, "POWER_TIME_UNKNOWN") and seconds_left == psutil.POWER_TIME_UNKNOWN:
                seconds_left = None

            return available(
                "psutil",
                percent=round(float(battery.percent), 1),
                plugged=battery.power_plugged,
                seconds_left=seconds_left,
            )
        except Exception as exc:
            return unavailable(
                f"Battery collector failed or unavailable: {exc.__class__.__name__}: {exc}",
                provider="psutil",
            )

    def _collect_active_window_title(self) -> JsonDict:
        if not is_windows():
            return unavailable("Active window title collection is only attempted on Windows", provider="pygetwindow")

        try:
            import pygetwindow as gw  # type: ignore

            active_window = gw.getActiveWindow()
            return available(
                "pygetwindow",
                title=active_window.title if active_window else None,
            )
        except ImportError:
            return unavailable("pygetwindow is not installed", provider="pygetwindow")
        except Exception as exc:
            return unavailable(
                f"Active window title collection failed: {exc.__class__.__name__}: {exc}",
                provider="pygetwindow",
            )

    def _collect_windows_power_scheme(self) -> JsonDict:
        if not is_windows():
            return unavailable("Windows powercfg is only available on Windows", provider="powercfg")

        result = self._run_command(["powercfg", "/getactivescheme"], timeout_seconds=5.0)

        if not result["ok"]:
            return unavailable(result["error"], provider="powercfg")

        stdout = result["stdout"].strip()
        scheme_guid = None
        scheme_name = None

        guid_match = re.search(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            stdout,
        )
        name_match = re.search(r"\((.*?)\)", stdout)

        if guid_match:
            scheme_guid = guid_match.group(1)
        if name_match:
            scheme_name = name_match.group(1)

        return available(
            "powercfg",
            scheme_guid=scheme_guid,
            scheme_name=scheme_name,
            raw=stdout,
        )

    def _collect_gpu_nvidia_smi(self) -> JsonDict:
        query = (
            "name,driver_version,temperature.gpu,utilization.gpu,"
            "memory.total,memory.used,memory.free"
        )

        result = self._run_command(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ]
        )

        if not result["ok"]:
            return unavailable(result["error"], provider="nvidia-smi")

        stdout = result["stdout"].strip()
        if not stdout:
            return unavailable("nvidia-smi returned no GPU rows", provider="nvidia-smi")

        gpus: list[JsonDict] = []
        for row in csv.reader(stdout.splitlines()):
            if len(row) < 7:
                continue

            name, driver, temp_c, util_percent, mem_total_mib, mem_used_mib, mem_free_mib = [
                cell.strip() for cell in row[:7]
            ]

            gpus.append(
                {
                    "name": name or None,
                    "driver_version": driver or None,
                    "temperature_celsius": safe_float(temp_c),
                    "load_percent": safe_float(util_percent),
                    "vram_total_mb": safe_int(mem_total_mib),
                    "vram_used_mb": safe_int(mem_used_mib),
                    "vram_free_mb": safe_int(mem_free_mib),
                }
            )

        if not gpus:
            return unavailable("nvidia-smi output could not be parsed", provider="nvidia-smi")

        return available("nvidia-smi", gpus=gpus)

    def _collect_gpu_gputil(self) -> JsonDict:
        try:
            import GPUtil  # type: ignore
        except ImportError:
            return unavailable("GPUtil is not installed", provider="GPUtil")

        try:
            gpus = GPUtil.getGPUs()
            if not gpus:
                return unavailable("GPUtil returned no GPUs", provider="GPUtil")

            results: list[JsonDict] = []
            for gpu in gpus:
                results.append(
                    {
                        "id": getattr(gpu, "id", None),
                        "name": getattr(gpu, "name", None),
                        "load_percent": (
                            round(float(gpu.load) * 100, 1)
                            if getattr(gpu, "load", None) is not None
                            else None
                        ),
                        "vram_total_mb": safe_float(getattr(gpu, "memoryTotal", None)),
                        "vram_used_mb": safe_float(getattr(gpu, "memoryUsed", None)),
                        "vram_free_mb": safe_float(getattr(gpu, "memoryFree", None)),
                        "temperature_celsius": safe_float(getattr(gpu, "temperature", None)),
                    }
                )

            return available("GPUtil", gpus=results)
        except Exception as exc:
            return unavailable(f"GPUtil collection failed: {exc.__class__.__name__}: {exc}", provider="GPUtil")

    def _collect_gpu_pynvml(self) -> JsonDict:
        try:
            import pynvml  # type: ignore
        except ImportError:
            return unavailable("pynvml is not installed", provider="pynvml")

        initialized = False
        try:
            pynvml.nvmlInit()
            initialized = True
            count = pynvml.nvmlDeviceGetCount()

            results: list[JsonDict] = []
            for index in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode(errors="replace")

                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    load_percent = util.gpu if util else None
                except Exception:
                    load_percent = None

                try:
                    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                except Exception:
                    mem = None

                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                except Exception:
                    temp = None

                results.append(
                    {
                        "id": index,
                        "name": name,
                        "load_percent": load_percent,
                        "vram_total_mb": round(mem.total / 1024 / 1024, 1) if mem else None,
                        "vram_used_mb": round(mem.used / 1024 / 1024, 1) if mem else None,
                        "vram_free_mb": round(mem.free / 1024 / 1024, 1) if mem else None,
                        "temperature_celsius": temp,
                    }
                )

            if not results:
                return unavailable("pynvml returned no GPUs", provider="pynvml")

            return available("pynvml", gpus=results)

        except Exception as exc:
            return unavailable(f"pynvml collection failed: {exc.__class__.__name__}: {exc}", provider="pynvml")
        finally:
            if initialized:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass

    def _collect_windows_video_adapters(self) -> JsonDict:
        if not is_windows():
            return unavailable("Windows video adapter detection only runs on Windows", provider="PowerShell CIM")

        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name,AdapterRAM,DriverVersion,VideoProcessor | "
                "ConvertTo-Json -Compress"
            ),
        ]

        result = self._run_command(command, timeout_seconds=3.5)

        if not result["ok"]:
            return unavailable(result["error"], provider="PowerShell CIM")

        stdout = result["stdout"].strip()
        if not stdout:
            return unavailable("PowerShell CIM returned no display adapter data", provider="PowerShell CIM")

        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return unavailable(f"Could not parse adapter JSON: {exc}", provider="PowerShell CIM")

        if isinstance(parsed, dict):
            parsed_adapters = [parsed]
        elif isinstance(parsed, list):
            parsed_adapters = parsed
        else:
            parsed_adapters = []

        adapters: list[JsonDict] = []
        for adapter in parsed_adapters:
            adapters.append(
                {
                    "name": adapter.get("Name"),
                    "adapter_ram_bytes": adapter.get("AdapterRAM"),
                    "adapter_ram_gib": bytes_to_gib(adapter.get("AdapterRAM")),
                    "driver_version": adapter.get("DriverVersion"),
                    "video_processor": adapter.get("VideoProcessor"),
                    "telemetry_available": False,
                    "note": "Adapter detected only; no reliable load/temperature telemetry from this path.",
                }
            )

        return available("PowerShell CIM", adapters=adapters)

    def _read_windows_startup_registry(self) -> JsonDict:
        if not is_windows():
            return unavailable("Windows startup registry is only available on Windows", provider="winreg")

        try:
            import winreg  # type: ignore
        except ImportError:
            return unavailable("winreg module is unavailable", provider="winreg")

        registry_locations = [
            ("HKCU", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ("HKCU", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
        ]

        startup_approved_locations = [
            ("HKCU", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
            ("HKCU", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"),
        ]

        approved_lookup = self._read_startup_approved_lookup(startup_approved_locations, winreg)

        entries: list[JsonDict] = []
        warnings: list[JsonDict] = []
        seen_keys: set[tuple[str, str, str]] = set()

        for hive_name, hive, subkey in registry_locations:
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
                    value_count = winreg.QueryInfoKey(key)[1]

                    for index in range(value_count):
                        try:
                            name, value, value_type = winreg.EnumValue(key, index)
                            seen_key = (hive_name, subkey, name)
                            if seen_key in seen_keys:
                                continue
                            seen_keys.add(seen_key)

                            approved = approved_lookup.get((hive_name, name))
                            if approved is None:
                                enabled_state = "unknown"
                                enabled_state_source = None
                            else:
                                enabled_state = "enabled" if approved else "disabled"
                                enabled_state_source = "StartupApproved"

                            entries.append(
                                {
                                    "source": "registry",
                                    "hive": hive_name,
                                    "key": subkey,
                                    "name": name,
                                    "command": str(value),
                                    "registry_value_type": value_type,
                                    "enabled_state": enabled_state,
                                    "enabled_state_source": enabled_state_source,
                                }
                            )
                        except OSError as exc:
                            warnings.append(
                                {
                                    "hive": hive_name,
                                    "key": subkey,
                                    "error": f"EnumValue failed: {exc}",
                                }
                            )

            except FileNotFoundError:
                continue
            except PermissionError as exc:
                warnings.append(
                    {
                        "hive": hive_name,
                        "key": subkey,
                        "error": f"PermissionError: {exc}",
                    }
                )
            except OSError as exc:
                warnings.append(
                    {
                        "hive": hive_name,
                        "key": subkey,
                        "error": f"OSError: {exc}",
                    }
                )

        return available(
            "winreg",
            entries=entries,
            warnings=warnings,
            startup_approved_entries_seen=len(approved_lookup),
            safety_note="Registry opened read-only using KEY_READ.",
        )

    @staticmethod
    def _read_startup_approved_lookup(
        startup_approved_locations: list[tuple[str, Any, str]],
        winreg_module: Any,
    ) -> dict[tuple[str, str], bool]:
        """
        Read Task Manager startup enabled/disabled state where available.

        Common byte interpretation:
            first byte 0x02 => enabled
            first byte 0x03 => disabled

        This is treated as best-effort. Missing or unreadable entries produce
        enabled_state='unknown' rather than overclaiming.
        """
        lookup: dict[tuple[str, str], bool] = {}

        for hive_name, hive, subkey in startup_approved_locations:
            try:
                with winreg_module.OpenKey(hive, subkey, 0, winreg_module.KEY_READ) as key:
                    value_count = winreg_module.QueryInfoKey(key)[1]
                    for index in range(value_count):
                        try:
                            name, data, _value_type = winreg_module.EnumValue(key, index)
                            if isinstance(data, bytes) and len(data) > 0:
                                if data[0] == 0x02:
                                    lookup[(hive_name, name)] = True
                                elif data[0] == 0x03:
                                    lookup[(hive_name, name)] = False
                        except OSError:
                            continue
            except (FileNotFoundError, PermissionError, OSError):
                continue

        return lookup

    def _read_windows_startup_folders(self) -> JsonDict:
        if not is_windows():
            return unavailable("Windows startup folders are only checked on Windows", provider="filesystem")

        folders: list[tuple[str, Path]] = []

        appdata = os.environ.get("APPDATA")
        if appdata:
            folders.append(
                (
                    "current_user_startup_folder",
                    Path(appdata) / r"Microsoft\Windows\Start Menu\Programs\Startup",
                )
            )

        programdata = os.environ.get("PROGRAMDATA")
        if programdata:
            folders.append(
                (
                    "all_users_startup_folder",
                    Path(programdata) / r"Microsoft\Windows\Start Menu\Programs\Startup",
                )
            )

        entries: list[JsonDict] = []
        warnings: list[JsonDict] = []

        for folder_label, folder in folders:
            try:
                if not folder.exists():
                    continue

                for item in folder.iterdir():
                    entries.append(
                        {
                            "source": "startup_folder",
                            "folder_type": folder_label,
                            "folder": str(folder),
                            "name": item.name,
                            "path": str(item),
                            "suffix": item.suffix,
                            "is_file": item.is_file(),
                            "enabled_state": "present",
                            "enabled_state_source": "startup_folder_presence",
                        }
                    )

            except PermissionError as exc:
                warnings.append({"folder": str(folder), "error": f"PermissionError: {exc}"})
            except OSError as exc:
                warnings.append({"folder": str(folder), "error": f"OSError: {exc}"})

        return available(
            "filesystem",
            entries=entries,
            warnings=warnings,
            safety_note="Startup folders are listed only. Files are not opened, changed, or deleted.",
        )

    def _run_command(
        self,
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> JsonDict:
        timeout = timeout_seconds or self.command_timeout_seconds

        try:
            creationflags = 0
            if is_windows() and hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                creationflags=creationflags,
            )

            if completed.returncode != 0:
                stderr = completed.stderr.strip()
                stdout = completed.stdout.strip()
                return {
                    "ok": False,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": completed.returncode,
                    "error": stderr or f"Command exited with code {completed.returncode}",
                }

            return {
                "ok": True,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
                "error": None,
            }

        except FileNotFoundError:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "error": f"Command not found: {command[0]}",
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "error": f"Command timed out after {timeout} seconds: {command[0]}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "error": f"{exc.__class__.__name__}: {exc}",
            }

    @staticmethod
    def _timestamp_to_utc(timestamp: Any) -> str | None:
        numeric = safe_float(timestamp)
        if numeric is None:
            return None

        try:
            return (
                datetime.fromtimestamp(numeric, timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        except Exception:
            return None


# ----------------------------------------------------------------------
# Public module-level convenience functions
# ----------------------------------------------------------------------

def collect_system_snapshot(
    *,
    process_limit: int = DEFAULT_PROCESS_LIMIT,
    include_exe_paths: bool = False,
    include_active_window_title: bool = False,
    measure_disk_throughput: bool = False,
) -> JsonDict:
    """
    Public convenience function for S3/S5 tests.

    Example:
        snapshot = collect_system_snapshot(process_limit=25)
    """
    collector = SystemCollectors(
        process_limit=process_limit,
        include_exe_paths=include_exe_paths,
        include_active_window_title=include_active_window_title,
        measure_disk_throughput=measure_disk_throughput,
    )
    return collector.collect_system_snapshot()


def collect_full_snapshot(
    *,
    process_limit: int = DEFAULT_PROCESS_LIMIT,
    include_exe_paths: bool = False,
    include_active_window_title: bool = False,
    measure_disk_throughput: bool = False,
) -> JsonDict:
    """
    Compatibility alias for Claude/Sol/Cline smoke tests.

    Equivalent to collect_system_snapshot().
    """
    return collect_system_snapshot(
        process_limit=process_limit,
        include_exe_paths=include_exe_paths,
        include_active_window_title=include_active_window_title,
        measure_disk_throughput=measure_disk_throughput,
    )


def collect_device_profile() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_device_profile()


def collect_cpu() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_cpu()


def collect_ram() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_memory()


def collect_memory() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_memory()


def collect_disk(*, measure_disk_throughput: bool = False) -> JsonDict:
    return SystemCollectors(
        process_limit=0,
        measure_disk_throughput=measure_disk_throughput,
    ).collect_disks()


def collect_disks(*, measure_disk_throughput: bool = False) -> JsonDict:
    return collect_disk(measure_disk_throughput=measure_disk_throughput)


def collect_network() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_network()


def collect_power_profile() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_power()


def collect_power() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_power()


def collect_gpu() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_gpu()


def collect_processes(process_limit: int = DEFAULT_PROCESS_LIMIT) -> JsonDict:
    return SystemCollectors(process_limit=process_limit).collect_processes()


def collect_startup_apps() -> JsonDict:
    return SystemCollectors(process_limit=0).collect_startup_apps()


def collect_environmental_context(
    *,
    include_active_window_title: bool = False,
) -> JsonDict:
    return SystemCollectors(
        process_limit=0,
        include_active_window_title=include_active_window_title,
    ).collect_environmental_context()


__all__ = [
    "COLLECTOR_VERSION",
    "SystemCollectors",
    "collect_system_snapshot",
    "collect_full_snapshot",
    "collect_device_profile",
    "collect_cpu",
    "collect_ram",
    "collect_memory",
    "collect_disk",
    "collect_disks",
    "collect_network",
    "collect_power_profile",
    "collect_power",
    "collect_gpu",
    "collect_processes",
    "collect_startup_apps",
    "collect_environmental_context",
]


if __name__ == "__main__":
    # Lightweight smoke-test entry point.
    # Keep process_limit low so manual output remains readable.
    import argparse

    parser = argparse.ArgumentParser(description="Run Axon S3 collectors smoke test.")
    parser.add_argument("--process-limit", type=int, default=10)
    parser.add_argument("--include-active-window-title", action="store_true")
    parser.add_argument("--measure-disk-throughput", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    smoke_snapshot = collect_system_snapshot(
        process_limit=args.process_limit,
        include_active_window_title=args.include_active_window_title,
        measure_disk_throughput=args.measure_disk_throughput,
    )

    # Truncate process list in manual output to keep smoke-test readable.
    display_snapshot = dict(smoke_snapshot)
    snapshot_data = dict(display_snapshot.get("snapshot_data", {}))
    process_block = snapshot_data.get("processes")
    if isinstance(process_block, dict) and isinstance(process_block.get("processes"), list):
        process_block = dict(process_block)
        process_block["processes"] = process_block["processes"][: args.process_limit]
        process_block["_truncated_for_display"] = True
        snapshot_data["processes"] = process_block
    display_snapshot["snapshot_data"] = snapshot_data

    print(json.dumps(display_snapshot, indent=2, ensure_ascii=False, default=str))
