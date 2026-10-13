"""Linux sysfs hwmon sensor backend for SCTRL.

Discovers and reads hardware sensors from /sys/class/hwmon/.
Handles missing drivers, inaccessible paths, and driver-specific naming conventions.
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path
from typing import Any

from sctrl.constants import SYSFS_HWMON
from sctrl.models import (
    CapabilityRecord,
    FeatureId,
    FeatureStatus,
    SensorReading,
    SupportTier,
    ValueQuality,
)
from daemon.hardware.base import SensorBackend

logger = logging.getLogger("sctrld.hwmon")


class HwmonSensorBackend(SensorBackend):
    """Reads temperatures, fan RPMs, and power from /sys/class/hwmon."""

    def __init__(self, sysfs_root: str | Path = SYSFS_HWMON) -> None:
        self._root = Path(sysfs_root)
        self._cpu_temp_path: Path | None = None
        self._gpu_temp_path: Path | None = None
        self._cpu_fan_path: Path | None = None
        self._gpu_fan_path: Path | None = None
        self._cpu_power_path: Path | None = None
        self._gpu_power_path: Path | None = None

    @property
    def backend_name(self) -> str:
        return "hwmon"

    def probe(self) -> list[CapabilityRecord]:
        """Scan hwmon directories for sensor nodes."""
        records: list[CapabilityRecord] = []
        if not self._root.exists():
            logger.info("Hwmon root %s does not exist", self._root)
            return records

        for hwmon_dir in sorted(self._root.glob("hwmon*")):
            name_file = hwmon_dir / "name"
            driver_name = ""
            if name_file.exists():
                try:
                    driver_name = name_file.read_text().strip()
                except Exception:
                    pass

            logger.debug("Found hwmon device %s: driver='%s'", hwmon_dir.name, driver_name)

            # Look for CPU temp (coretemp, k10temp, zenpower, or acer-wmi)
            if not self._cpu_temp_path and any(k in driver_name for k in ("coretemp", "k10temp", "zenpower", "cpu")):
                temp_inputs = sorted(hwmon_dir.glob("temp*_input"))
                if temp_inputs:
                    self._cpu_temp_path = temp_inputs[0]
                    records.append(CapabilityRecord(
                        feature_id=FeatureId.CPU_TEMP,
                        status=FeatureStatus.SUPPORTED,
                        interface=str(self._cpu_temp_path),
                        readable=True,
                    ))

            # Look for fans (acer-wmi, nct6775, etc.)
            fan_inputs = sorted(hwmon_dir.glob("fan*_input"))
            if fan_inputs:
                if not self._cpu_fan_path and len(fan_inputs) >= 1:
                    self._cpu_fan_path = fan_inputs[0]
                    records.append(CapabilityRecord(
                        feature_id=FeatureId.CPU_FAN_RPM,
                        status=FeatureStatus.SUPPORTED,
                        interface=str(self._cpu_fan_path),
                        readable=True,
                    ))
                if not self._gpu_fan_path and len(fan_inputs) >= 2:
                    self._gpu_fan_path = fan_inputs[1]
                    records.append(CapabilityRecord(
                        feature_id=FeatureId.GPU_FAN_RPM,
                        status=FeatureStatus.SUPPORTED,
                        interface=str(self._gpu_fan_path),
                        readable=True,
                    ))

        return records

    def _read_sysfs_int(self, path: Path | None, divisor: float = 1.0) -> float | None:
        if not path or not path.exists():
            return None
        try:
            val_str = path.read_text().strip()
            return int(val_str) / divisor
        except Exception as e:
            logger.debug("Error reading %s: %s", path, e)
            return None

    def read_cpu_temp(self) -> SensorReading:
        val = self._read_sysfs_int(self._cpu_temp_path, divisor=1000.0)
        if val is not None:
            return SensorReading(value=val, unit="C", quality=ValueQuality.MEASURED, source=str(self._cpu_temp_path))
        return SensorReading(value=None, unit="C", quality=ValueQuality.UNAVAILABLE)

    def read_gpu_temp(self) -> SensorReading:
        val = self._read_sysfs_int(self._gpu_temp_path, divisor=1000.0)
        if val is not None:
            return SensorReading(value=val, unit="C", quality=ValueQuality.MEASURED, source=str(self._gpu_temp_path))
        return SensorReading(value=None, unit="C", quality=ValueQuality.UNAVAILABLE)

    def read_cpu_fan_rpm(self) -> SensorReading:
        val = self._read_sysfs_int(self._cpu_fan_path, divisor=1.0)
        if val is not None:
            return SensorReading(value=float(val), unit="RPM", quality=ValueQuality.MEASURED, source=str(self._cpu_fan_path))
        return SensorReading(value=None, unit="RPM", quality=ValueQuality.UNAVAILABLE)

    def read_gpu_fan_rpm(self) -> SensorReading:
        val = self._read_sysfs_int(self._gpu_fan_path, divisor=1.0)
        if val is not None:
            return SensorReading(value=float(val), unit="RPM", quality=ValueQuality.MEASURED, source=str(self._gpu_fan_path))
        return SensorReading(value=None, unit="RPM", quality=ValueQuality.UNAVAILABLE)

    def read_cpu_power(self) -> SensorReading:
        val = self._read_sysfs_int(self._cpu_power_path, divisor=1000000.0)
        if val is not None:
            return SensorReading(value=val, unit="W", quality=ValueQuality.MEASURED, source=str(self._cpu_power_path))
        return SensorReading(value=None, unit="W", quality=ValueQuality.UNAVAILABLE)

    def read_gpu_power(self) -> SensorReading:
        val = self._read_sysfs_int(self._gpu_power_path, divisor=1000.0)
        if val is not None:
            return SensorReading(value=val, unit="W", quality=ValueQuality.MEASURED, source=str(self._gpu_power_path))
        return SensorReading(value=None, unit="W", quality=ValueQuality.UNAVAILABLE)
