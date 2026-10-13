"""Linux sysfs battery and charge control backend for SCTRL.

Reads battery telemetry and controls battery charging threshold via
/sys/class/power_supply/BAT*/charge_control_end_threshold.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sctrl.constants import SYSFS_POWER_SUPPLY
from sctrl.models import (
    CapabilityRecord,
    FeatureId,
    FeatureStatus,
    SensorReading,
    ValueQuality,
)
from daemon.hardware.base import BatteryBackend, WriteResult

logger = logging.getLogger("sctrld.battery_backend")


class SysfsBatteryBackend(BatteryBackend):
    """Interacts with Linux kernel battery power_supply subsystem."""

    def __init__(self, sysfs_root: str | Path = SYSFS_POWER_SUPPLY) -> None:
        self._root = Path(sysfs_root)
        self._bat_dir: Path | None = None
        self._threshold_file: Path | None = None

    @property
    def backend_name(self) -> str:
        return "sysfs_battery"

    def probe(self) -> list[CapabilityRecord]:
        records: list[CapabilityRecord] = []
        if not self._root.exists():
            return records

        # Look for BAT0, BAT1, or BATT
        for bat_dir in sorted(self._root.glob("BAT*")):
            self._bat_dir = bat_dir
            records.append(CapabilityRecord(
                feature_id=FeatureId.BATTERY_CHARGE,
                status=FeatureStatus.SUPPORTED,
                interface=str(bat_dir / "capacity"),
                readable=True,
            ))
            records.append(CapabilityRecord(
                feature_id=FeatureId.BATTERY_STATE,
                status=FeatureStatus.SUPPORTED,
                interface=str(bat_dir / "status"),
                readable=True,
            ))

            # Check charge_control_end_threshold
            thresh = bat_dir / "charge_control_end_threshold"
            if thresh.exists():
                self._threshold_file = thresh
                writable = os.access(str(thresh), os.W_OK) if hasattr(os, "access") else True
                records.append(CapabilityRecord(
                    feature_id=FeatureId.CHARGE_LIMIT,
                    status=FeatureStatus.SUPPORTED if writable else FeatureStatus.PERMISSION_DENIED,
                    interface=str(thresh),
                    readable=True,
                    writable=writable,
                    supported_range=(50, 100),
                ))
            break

        return records

    def read_charge_percent(self) -> SensorReading:
        if not self._bat_dir:
            return SensorReading(value=None, unit="%", quality=ValueQuality.UNAVAILABLE)
        cap_file = self._bat_dir / "capacity"
        try:
            val = float(cap_file.read_text().strip())
            return SensorReading(value=val, unit="%", quality=ValueQuality.MEASURED, source=str(cap_file))
        except Exception:
            return SensorReading(value=None, unit="%", quality=ValueQuality.UNAVAILABLE)

    def read_charge_state(self) -> str:
        if not self._bat_dir:
            return "unknown"
        status_file = self._bat_dir / "status"
        try:
            return status_file.read_text().strip().lower()
        except Exception:
            return "unknown"

    def get_charge_limit(self) -> int | None:
        if not self._threshold_file or not self._threshold_file.exists():
            return None
        try:
            return int(self._threshold_file.read_text().strip())
        except Exception:
            return None

    def set_charge_limit(self, percent: int) -> WriteResult:
        if not self._threshold_file:
            return WriteResult(
                success=False,
                feature=FeatureId.CHARGE_LIMIT,
                requested_value=percent,
                backend=self.backend_name,
                error="charge_control_end_threshold not supported on this battery",
            )
        try:
            self._threshold_file.write_text(str(percent))
            # Verify write
            actual = self.get_charge_limit()
            verified = (actual == percent)
            return WriteResult(
                success=verified,
                feature=FeatureId.CHARGE_LIMIT,
                requested_value=percent,
                actual_value=actual,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Readback mismatch: wrote {percent}, got {actual}",
            )
        except PermissionError:
            return WriteResult(
                success=False,
                feature=FeatureId.CHARGE_LIMIT,
                requested_value=percent,
                backend=self.backend_name,
                error="Permission denied writing charge limit (daemon must run as root)",
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.CHARGE_LIMIT,
                requested_value=percent,
                backend=self.backend_name,
                error=str(e),
            )

    def get_charge_limit_range(self) -> tuple[int, int] | None:
        if self._threshold_file and self._threshold_file.exists():
            return (50, 100)
        return None
