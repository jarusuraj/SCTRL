"""Linuwu-sense driver backend for SCTRL.

Supports the community linuwu-sense kernel module for Acer Predator and Nitro laptops.
All node names MUST be resolved from exact names listed in the model profile (quirks)
and verified against docs/hw-dump.txt.
No substring or fuzzy guessing is permitted.
An unconfigured or missing node results in FeatureStatus.DRIVER_MISSING and no writes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sctrl.models import (
    CapabilityRecord,
    FanMode,
    FeatureId,
    FeatureStatus,
)
from sctrl.model_db import ModelProfile
from daemon.hardware.base import (
    FanControlBackend,
    ProfileBackend,
    WriteResult,
)

logger = logging.getLogger("sctrld.linuwu_sense")

# Standard sysfs platform device path for linuwu-sense
DEFAULT_LINUWU_SYSFS_DIR = Path("/sys/devices/platform/linuwu-sense")


class LinuwuSenseBackend(FanControlBackend, ProfileBackend):
    """Interacts with linuwu-sense driver using exact profile node definitions."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        model_profile: ModelProfile | None = None,
    ) -> None:
        self._model_profile = model_profile
        self._base_dir = Path(base_dir) if base_dir else self._resolve_base_dir()

        self._mode_file: Path | None = None
        self._cpu_speed_file: Path | None = None
        self._gpu_speed_file: Path | None = None
        self._profile_file: Path | None = None
        self._current_mode = FanMode.AUTO

        self._resolve_nodes()

    @property
    def backend_name(self) -> str:
        return "linuwu-sense"

    @property
    def is_available(self) -> bool:
        return self._base_dir is not None and self._base_dir.exists()

    def _resolve_base_dir(self) -> Path | None:
        quirks = self._model_profile.quirks if self._model_profile else {}
        custom_base = quirks.get("linuwu_base_dir")
        if custom_base:
            p = Path(custom_base)
            if p.exists():
                return p
        if DEFAULT_LINUWU_SYSFS_DIR.exists():
            return DEFAULT_LINUWU_SYSFS_DIR
        return None

    def _resolve_nodes(self) -> None:
        """Resolve nodes strictly using exact names from model profile quirks."""
        if not self._base_dir or not self._base_dir.exists():
            return

        quirks = self._model_profile.quirks if self._model_profile else {}

        mode_name = quirks.get("linuwu_fan_mode_node")
        cpu_name = quirks.get("linuwu_cpu_speed_node")
        gpu_name = quirks.get("linuwu_gpu_speed_node")
        prof_name = quirks.get("linuwu_profile_node")

        if mode_name:
            target = self._base_dir / mode_name
            if target.exists():
                self._mode_file = target

        if cpu_name:
            target = self._base_dir / cpu_name
            if target.exists():
                self._cpu_speed_file = target

        if gpu_name:
            target = self._base_dir / gpu_name
            if target.exists():
                self._gpu_speed_file = target

        if prof_name:
            target = self._base_dir / prof_name
            if target.exists():
                self._profile_file = target

    # --- FanControlBackend interface ---

    def probe(self) -> list[CapabilityRecord]:
        records: list[CapabilityRecord] = []

        # 1. Fan mode capability
        if self._mode_file and self._mode_file.exists():
            records.append(CapabilityRecord(
                feature_id=FeatureId.FAN_MODE,
                status=FeatureStatus.SUPPORTED,
                interface=str(self._mode_file),
                readable=True,
                writable=True,
                supported_values=["auto", "max", "custom"],
                current_value=self._current_mode.value,
                confidence="profile_verified",
            ))
        else:
            records.append(CapabilityRecord(
                feature_id=FeatureId.FAN_MODE,
                status=FeatureStatus.DRIVER_MISSING,
                interface="",
                readable=False,
                writable=False,
                last_error="linuwu-sense fan_mode node not resolved or file missing",
            ))

        # 2. Fan speed / curve capability
        if (self._cpu_speed_file and self._cpu_speed_file.exists()) or (
            self._gpu_speed_file and self._gpu_speed_file.exists()
        ):
            target_iface = str(self._cpu_speed_file or self._gpu_speed_file)
            min_spd = self._model_profile.fans.min_speed_percent if self._model_profile else 0
            max_spd = self._model_profile.fans.max_speed_percent if self._model_profile else 100
            records.append(CapabilityRecord(
                feature_id=FeatureId.FAN_CURVE,
                status=FeatureStatus.SUPPORTED,
                interface=target_iface,
                readable=True,
                writable=True,
                supported_range=(min_spd, max_spd),
                confidence="profile_verified",
            ))
        else:
            records.append(CapabilityRecord(
                feature_id=FeatureId.FAN_CURVE,
                status=FeatureStatus.DRIVER_MISSING,
                interface="",
                readable=False,
                writable=False,
                last_error="linuwu-sense fan speed nodes not resolved or file missing",
            ))

        # 3. Performance profile capability
        if self._profile_file and self._profile_file.exists():
            records.append(CapabilityRecord(
                feature_id=FeatureId.PERFORMANCE_PROFILE,
                status=FeatureStatus.SUPPORTED,
                interface=str(self._profile_file),
                readable=True,
                writable=True,
                supported_values=self.get_available_profiles(),
                current_value=self.get_current_profile(),
                confidence="profile_verified",
            ))
        else:
            records.append(CapabilityRecord(
                feature_id=FeatureId.PERFORMANCE_PROFILE,
                status=FeatureStatus.DRIVER_MISSING,
                interface="",
                readable=False,
                writable=False,
                last_error="linuwu-sense platform_profile node not resolved or file missing",
            ))

        return records

    def get_current_mode(self) -> FanMode:
        return self._current_mode

    def set_mode_auto(self) -> WriteResult:
        if not self._mode_file or not self._mode_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_MODE,
                requested_value="auto",
                backend=self.backend_name,
                error="fan_mode node missing",
            )
        try:
            self._mode_file.write_text("auto")
            # Read-back verification
            readback = self._mode_file.read_text().strip().lower()
            verified = (readback == "auto")
            if verified:
                self._current_mode = FanMode.AUTO
            return WriteResult(
                success=verified,
                feature=FeatureId.FAN_MODE,
                requested_value="auto",
                actual_value=readback,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Readback mismatch: expected 'auto', got '{readback}'",
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_MODE,
                requested_value="auto",
                backend=self.backend_name,
                error=str(e),
            )

    def set_mode_max(self) -> WriteResult:
        if not self._mode_file or not self._mode_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_MODE,
                requested_value="max",
                backend=self.backend_name,
                error="fan_mode node missing",
            )
        try:
            self._mode_file.write_text("max")
            # Read-back verification
            readback = self._mode_file.read_text().strip().lower()
            verified = (readback == "max")
            if verified:
                self._current_mode = FanMode.MAX
            return WriteResult(
                success=verified,
                feature=FeatureId.FAN_MODE,
                requested_value="max",
                actual_value=readback,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Readback mismatch: expected 'max', got '{readback}'",
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_MODE,
                requested_value="max",
                backend=self.backend_name,
                error=str(e),
            )

    def set_fan_speed(self, fan: str, speed_percent: int) -> WriteResult:
        target_file = self._cpu_speed_file if fan == "cpu" else self._gpu_speed_file
        if not target_file or not target_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                backend=self.backend_name,
                error=f"No control node resolved for {fan} fan",
            )
        try:
            target_file.write_text(str(speed_percent))
            # Read-back verification
            readback_str = target_file.read_text().strip()
            try:
                readback_val = int(readback_str)
                verified = (readback_val == speed_percent)
            except ValueError:
                verified = False
                readback_val = None

            return WriteResult(
                success=verified,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                actual_value=readback_val,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Readback mismatch: wrote {speed_percent}, read {readback_str}",
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
        if self._model_profile:
            return (self._model_profile.fans.min_speed_percent, self._model_profile.fans.max_speed_percent)
        return (0, 100)

    # --- ProfileBackend interface ---

    def get_current_profile(self) -> str:
        if self._profile_file and self._profile_file.exists():
            try:
                return self._profile_file.read_text().strip()
            except Exception:
                pass
        return ""

    def get_available_profiles(self) -> list[str]:
        if self._model_profile and self._model_profile.profile_mapping:
            return list(self._model_profile.profile_mapping.values())
        return ["quiet", "balanced", "performance", "turbo"]

    def set_profile(self, profile_value: str) -> WriteResult:
        if not self._profile_file or not self._profile_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                backend=self.backend_name,
                error="linuwu-sense profile node missing",
            )
        try:
            self._profile_file.write_text(profile_value)
            readback = self._profile_file.read_text().strip()
            verified = (readback.lower() == profile_value.lower())
            return WriteResult(
                success=verified,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                actual_value=readback,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Readback mismatch: expected '{profile_value}', got '{readback}'",
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                backend=self.backend_name,
                error=str(e),
            )
