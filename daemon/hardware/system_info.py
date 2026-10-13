"""System information backend for SCTRL.

Reads DMI identity from /sys/class/dmi/id/, system telemetry via psutil or /proc,
and kernel/distro information.
"""

from __future__ import annotations

import logging
import platform
import time
from pathlib import Path

from sctrl.constants import SYSFS_DMI_ID
from sctrl.models import DMIInfo, SensorReading, ValueQuality
from daemon.hardware.base import SystemInfoBackend

logger = logging.getLogger("sctrld.system_info")

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class RealSystemInfoBackend(SystemInfoBackend):
    """Retrieves system and DMI telemetry from Linux sysfs and procfs."""

    def __init__(self, dmi_root: str | Path = SYSFS_DMI_ID) -> None:
        self._dmi_root = Path(dmi_root)
        self._dmi_cached: DMIInfo | None = None

    @property
    def backend_name(self) -> str:
        return "system_info"

    def _read_dmi_field(self, field_name: str) -> str:
        field_file = self._dmi_root / field_name
        if field_file.exists():
            try:
                return field_file.read_text().strip()
            except Exception:
                return ""
        return ""

    def read_dmi(self) -> DMIInfo:
        if self._dmi_cached is not None:
            return self._dmi_cached

        if self._dmi_root.exists():
            self._dmi_cached = DMIInfo(
                product_name=self._read_dmi_field("product_name"),
                board_name=self._read_dmi_field("board_name"),
                vendor=self._read_dmi_field("sys_vendor") or self._read_dmi_field("bios_vendor"),
                bios_version=self._read_dmi_field("bios_version"),
                bios_date=self._read_dmi_field("bios_date"),
                sys_vendor=self._read_dmi_field("sys_vendor"),
                chassis_type=self._read_dmi_field("chassis_type"),
            )
        else:
            # Fallback for mock/test/Windows environments
            self._dmi_cached = DMIInfo(
                product_name="Generic PC",
                board_name="Generic Board",
                vendor="Generic",
                bios_version="1.0.0",
            )
        return self._dmi_cached

    def read_cpu_util(self) -> SensorReading:
        if _HAS_PSUTIL:
            try:
                pct = psutil.cpu_percent(interval=None)
                return SensorReading(value=float(pct), unit="%", quality=ValueQuality.MEASURED, source="psutil")
            except Exception:
                pass
        return SensorReading(value=None, unit="%", quality=ValueQuality.UNAVAILABLE)

    def read_ram_usage(self) -> tuple[SensorReading, SensorReading, SensorReading]:
        if _HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                used = SensorReading(value=float(mem.used), unit="B", quality=ValueQuality.MEASURED, source="psutil")
                total = SensorReading(value=float(mem.total), unit="B", quality=ValueQuality.MEASURED, source="psutil")
                pct = SensorReading(value=float(mem.percent), unit="%", quality=ValueQuality.MEASURED, source="psutil")
                return (used, total, pct)
            except Exception:
                pass

        unavail = SensorReading(value=None, unit="B", quality=ValueQuality.UNAVAILABLE)
        unavail_pct = SensorReading(value=None, unit="%", quality=ValueQuality.UNAVAILABLE)
        return (unavail, unavail, unavail_pct)

    def read_gpu_util(self) -> SensorReading:
        return SensorReading(value=None, unit="%", quality=ValueQuality.UNAVAILABLE)

    def read_uptime(self) -> float:
        if _HAS_PSUTIL:
            try:
                return time.time() - psutil.boot_time()
            except Exception:
                pass
        proc_uptime = Path("/proc/uptime")
        if proc_uptime.exists():
            try:
                return float(proc_uptime.read_text().split()[0])
            except Exception:
                pass
        return 0.0

    def is_gpu_suspended(self) -> bool:
        return False

    def get_kernel_version(self) -> str:
        return platform.release()

    def get_distro_info(self) -> str:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            try:
                lines = os_release.read_text().splitlines()
                for line in lines:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip('"\'')
            except Exception:
                pass
        return platform.system() + " " + platform.release()
