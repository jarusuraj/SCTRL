"""Acer WMI and ACPI platform profile backend for SCTRL.

Supports:
- ACPI platform_profile (/sys/firmware/acpi/platform_profile)
- Acer WMI platform device (/sys/devices/platform/acer-wmi/)
- Gaming profile selection and fan mode switching
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sctrl.constants import SYSFS_ACER_WMI, SYSFS_PLATFORM_PROFILE
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
            actual = self.get_current_profile()
            verified = (actual.lower() == profile_value.lower())
            return WriteResult(
                success=True,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                actual_value=actual,
                verified=verified,
                backend=self.backend_name,
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
    """Controls fans via Acer WMI or compatible kernel driver."""

    def __init__(self, wmi_dir: str | Path = SYSFS_ACER_WMI) -> None:
        self._dir = Path(wmi_dir)
        self._mode_file = self._dir / "fan_mode"
        self._cpu_speed_file = self._dir / "cpu_fan_speed"
        self._gpu_speed_file = self._dir / "gpu_fan_speed"
        self._current_mode = FanMode.AUTO

    @property
    def backend_name(self) -> str:
        return "acer_wmi"

    def probe(self) -> list[CapabilityRecord]:
        records: list[CapabilityRecord] = []
        if self._mode_file.exists():
            records.append(CapabilityRecord(
                feature_id=FeatureId.FAN_MODE,
                status=FeatureStatus.SUPPORTED,
                interface=str(self._mode_file),
                readable=True,
                writable=True,
                supported_values=["auto", "max", "custom"],
            ))
        return records

    def get_current_mode(self) -> FanMode:
        return self._current_mode

    def set_mode_auto(self) -> WriteResult:
        self._current_mode = FanMode.AUTO
        if self._mode_file.exists():
            try:
                self._mode_file.write_text("auto")
            except Exception as e:
                return WriteResult(
                    success=False,
                    feature=FeatureId.FAN_MODE,
                    requested_value="auto",
                    backend=self.backend_name,
                    error=str(e),
                )
        return WriteResult(
            success=True,
            feature=FeatureId.FAN_MODE,
            requested_value="auto",
            actual_value="auto",
            verified=True,
            backend=self.backend_name,
        )

    def set_mode_max(self) -> WriteResult:
        self._current_mode = FanMode.MAX
        if self._mode_file.exists():
            try:
                self._mode_file.write_text("max")
            except Exception as e:
                return WriteResult(
                    success=False,
                    feature=FeatureId.FAN_MODE,
                    requested_value="max",
                    backend=self.backend_name,
                    error=str(e),
                )
        return WriteResult(
            success=True,
            feature=FeatureId.FAN_MODE,
            requested_value="max",
            actual_value="max",
            verified=True,
            backend=self.backend_name,
        )

    def set_fan_speed(self, fan: str, speed_percent: int) -> WriteResult:
        target_file = self._cpu_speed_file if fan == "cpu" else self._gpu_speed_file
        if not target_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                backend=self.backend_name,
                error=f"Fan speed control file {target_file} not found",
            )
        try:
            target_file.write_text(str(speed_percent))
            return WriteResult(
                success=True,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                actual_value=speed_percent,
                verified=True,
                backend=self.backend_name,
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                backend=self.backend_name,
                error=str(e),
            )

    def get_supported_range(self, fan: str) -> tuple[int, int]:
        return (0, 100)
