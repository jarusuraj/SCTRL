"""Acer ACPI platform profile and hardware interface for SCTRL.

Standard Linux ACPI platform_profile (/sys/firmware/acpi/platform_profile)
provides kernel-native performance profile switching without custom kernel patches.
No invented sysfs paths are used. If custom fan nodes are not present,
capabilities report FeatureStatus.DRIVER_MISSING and no writes occur.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sctrl.constants import SYSFS_PLATFORM_PROFILE
from sctrl.models import (
    CapabilityRecord,
    FanMode,
    FeatureId,
    FeatureStatus,
)
from daemon.hardware.base import (
    FanControlBackend,
    ProfileBackend,
    WriteResult,
)

logger = logging.getLogger("sctrld.acer_wmi")


class PlatformProfileBackend(ProfileBackend):
    """Controls laptop performance profiles via standard Linux ACPI platform_profile."""

    def __init__(
        self,
        profile_file: str | Path = SYSFS_PLATFORM_PROFILE,
        choices_file: str | Path = "/sys/firmware/acpi/platform_profile_choices",
    ) -> None:
        self._profile_file = Path(profile_file)
        self._choices_file = Path(choices_file)

    @property
    def backend_name(self) -> str:
        return "platform_profile"

    def probe(self) -> list[CapabilityRecord]:
        records: list[CapabilityRecord] = []
        if self._profile_file.exists():
            choices = self.get_available_profiles()
            records.append(CapabilityRecord(
                feature_id=FeatureId.PERFORMANCE_PROFILE,
                status=FeatureStatus.SUPPORTED,
                interface=str(self._profile_file),
                readable=True,
                writable=True,
                supported_values=choices,
                current_value=self.get_current_profile(),
            ))
        else:
            records.append(CapabilityRecord(
                feature_id=FeatureId.PERFORMANCE_PROFILE,
                status=FeatureStatus.DRIVER_MISSING,
                interface=str(self._profile_file),
                readable=False,
                writable=False,
                last_error="ACPI platform_profile interface not found",
            ))
        return records

    def get_current_profile(self) -> str:
        if not self._profile_file.exists():
            return ""
        try:
            return self._profile_file.read_text().strip()
        except Exception as e:
            logger.debug("Failed reading platform_profile: %s", e)
            return ""

    def get_available_profiles(self) -> list[str]:
        if not self._choices_file.exists():
            return []
        try:
            return self._choices_file.read_text().strip().split()
        except Exception as e:
            logger.debug("Failed reading platform_profile_choices: %s", e)
            return []

    def set_profile(self, profile_value: str) -> WriteResult:
        if not self._profile_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                backend=self.backend_name,
                error="platform_profile sysfs path does not exist",
            )
        try:
            self._profile_file.write_text(profile_value)
            readback = self.get_current_profile()
            verified = (readback.lower() == profile_value.lower())
            return WriteResult(
                success=verified,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                actual_value=readback,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Verification mismatch: expected '{profile_value}', got '{readback}'",
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                backend=self.backend_name,
                error=str(e),
            )


class AcerWmiFanBackend(FanControlBackend):
    """Stub fan backend for standard upstream acer-wmi (which lacks custom fan nodes).

    Does NOT invent fake sysfs paths. If a genuine fan interface is not discovered,
    probes report FeatureStatus.DRIVER_MISSING and zero writes occur.
    """

    def __init__(self) -> None:
        self._current_mode = FanMode.AUTO

    @property
    def backend_name(self) -> str:
        return "acer_wmi"

    def probe(self) -> list[CapabilityRecord]:
        return [
            CapabilityRecord(
                feature_id=FeatureId.FAN_MODE,
                status=FeatureStatus.DRIVER_MISSING,
                interface="",
                readable=False,
                writable=False,
                last_error="Standard acer-wmi driver lacks custom fan sysfs interface. Requires linuwu-sense.",
            ),
            CapabilityRecord(
                feature_id=FeatureId.FAN_CURVE,
                status=FeatureStatus.DRIVER_MISSING,
                interface="",
                readable=False,
                writable=False,
                last_error="Custom fan curve not supported by stock acer-wmi driver.",
            ),
        ]

    def get_current_mode(self) -> FanMode:
        return self._current_mode

    def set_mode_auto(self) -> WriteResult:
        return WriteResult(
            success=False,
            feature=FeatureId.FAN_MODE,
            requested_value="auto",
            backend=self.backend_name,
            error="Stock acer-wmi driver lacks fan control interface. No write performed.",
        )

    def set_mode_max(self) -> WriteResult:
        return WriteResult(
            success=False,
            feature=FeatureId.FAN_MODE,
            requested_value="max",
            backend=self.backend_name,
            error="Stock acer-wmi driver lacks fan control interface. No write performed.",
        )

    def set_fan_speed(self, fan: str, speed_percent: int) -> WriteResult:
        return WriteResult(
            success=False,
            feature=FeatureId.FAN_CURVE,
            requested_value=speed_percent,
            backend=self.backend_name,
            error="Stock acer-wmi driver lacks fan control interface. No write performed.",
        )

    def get_supported_range(self, fan: str) -> tuple[int, int]:
        return (0, 100)
