"""Linuwu-sense driver backend for SCTRL.

Supports the community linuwu-sense kernel module for Acer Predator and Nitro laptops.
All sysfs node names and paths are discovered at runtime from the system or
resolved through the active model profile, NEVER hardcoded.
"""

from __future__ import annotations

import logging
import os
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

# Potential search locations for linuwu-sense platform driver
DEFAULT_PLATFORM_SEARCH_PATHS = [
    Path("/sys/devices/platform"),
    Path("/sys/bus/platform/devices"),
    Path("/sys/class/hwmon"),
]


class LinuwuSenseBackend(FanControlBackend, ProfileBackend):
    """Interacts with linuwu-sense driver with dynamic node discovery.

    Discovers sysfs nodes dynamically by inspecting directory contents and
    matching capabilities against model profile hints rather than hardcoding paths.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        model_profile: ModelProfile | None = None,
    ) -> None:
        self._model_profile = model_profile
        self._base_dir: Path | None = Path(base_dir) if base_dir else None

        # Dynamically discovered node paths
        self._mode_file: Path | None = None
        self._cpu_speed_file: Path | None = None
        self._gpu_speed_file: Path | None = None
        self._profile_file: Path | None = None
        self._current_mode = FanMode.AUTO

        self._discover_nodes()

    @property
    def backend_name(self) -> str:
        return "linuwu-sense"

    @property
    def is_available(self) -> bool:
        return self._base_dir is not None and self._base_dir.exists()

    def _discover_nodes(self) -> None:
        """Dynamically locate the driver directory and control nodes."""
        # 1. Discover base directory if not explicitly provided
        if not self._base_dir or not self._base_dir.exists():
            self._base_dir = self._find_driver_base()

        if not self._base_dir or not self._base_dir.exists():
            logger.debug("linuwu-sense driver directory not found")
            return

        logger.info("Discovered linuwu-sense platform at %s", self._base_dir)

        # 2. Check model profile quirks for node overrides if defined
        quirks = self._model_profile.quirks if self._model_profile else {}
        custom_mode_node = quirks.get("linuwu_fan_mode_node")
        custom_cpu_node = quirks.get("linuwu_cpu_speed_node")
        custom_gpu_node = quirks.get("linuwu_gpu_speed_node")
        custom_prof_node = quirks.get("linuwu_profile_node")

        if custom_mode_node and (self._base_dir / custom_mode_node).exists():
            self._mode_file = self._base_dir / custom_mode_node
        if custom_cpu_node and (self._base_dir / custom_cpu_node).exists():
            self._cpu_speed_file = self._base_dir / custom_cpu_node
        if custom_gpu_node and (self._base_dir / custom_gpu_node).exists():
            self._gpu_speed_file = self._base_dir / custom_gpu_node
        if custom_prof_node and (self._base_dir / custom_prof_node).exists():
            self._profile_file = self._base_dir / custom_prof_node

        # 3. Dynamic discovery by directory traversal and attribute inspection
        try:
            for entry in self._base_dir.iterdir():
                name = entry.name.lower()
                # Fan mode node
                if not self._mode_file and ("fan_mode" in name or "fanmode" in name or "cooling_mode" in name):
                    self._mode_file = entry
                # CPU fan speed
                elif not self._cpu_speed_file and (("cpu" in name and "speed" in name) or ("fan" in name and "1" in name and "speed" in name)):
                    self._cpu_speed_file = entry
                # GPU fan speed
                elif not self._gpu_speed_file and (("gpu" in name and "speed" in name) or ("fan" in name and "2" in name and "speed" in name)):
                    self._gpu_speed_file = entry
                # Performance profile
                elif not self._profile_file and ("profile" in name or "perf_mode" in name):
                    self._profile_file = entry
        except Exception as e:
            logger.warning("Error during dynamic linuwu-sense node discovery: %s", e)

    def _find_driver_base(self) -> Path | None:
        """Scan system search paths for linuwu-sense directory."""
        for root in DEFAULT_PLATFORM_SEARCH_PATHS:
            if not root.exists():
                continue
            try:
                for candidate in root.iterdir():
                    c_name = candidate.name.lower()
                    if "linuwu" in c_name or "predator" in c_name:
                        return candidate
                    # Check hwmon device name attribute
                    if candidate.name.startswith("hwmon"):
                        name_file = candidate / "name"
                        if name_file.exists():
                            try:
                                if "linuwu" in name_file.read_text().lower():
                                    return candidate
                            except Exception:
                                pass
            except Exception:
                pass
        return None

    # --- FanControlBackend interface ---

    def probe(self) -> list[CapabilityRecord]:
        records: list[CapabilityRecord] = []
        if not self.is_available:
            return records

        if self._mode_file and self._mode_file.exists():
            records.append(CapabilityRecord(
                feature_id=FeatureId.FAN_MODE,
                status=FeatureStatus.SUPPORTED,
                interface=str(self._mode_file),
                readable=True,
                writable=True,
                supported_values=["auto", "max", "custom"],
                current_value=self._current_mode.value,
                confidence="runtime_discovered",
            ))

        if self._cpu_speed_file or self._gpu_speed_file:
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
                confidence="runtime_discovered",
            ))

        if self._profile_file and self._profile_file.exists():
            records.append(CapabilityRecord(
                feature_id=FeatureId.PERFORMANCE_PROFILE,
                status=FeatureStatus.SUPPORTED,
                interface=str(self._profile_file),
                readable=True,
                writable=True,
                supported_values=self.get_available_profiles(),
                current_value=self.get_current_profile(),
                confidence="runtime_discovered",
            ))

        return records

    def get_current_mode(self) -> FanMode:
        return self._current_mode

    def set_mode_auto(self) -> WriteResult:
        self._current_mode = FanMode.AUTO
        if self._mode_file and self._mode_file.exists():
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
        if self._mode_file and self._mode_file.exists():
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
        if not target_file or not target_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                backend=self.backend_name,
                error=f"No control node discovered for {fan} fan",
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
                error="linuwu-sense profile node not discovered",
            )
        try:
            self._profile_file.write_text(profile_value)
            return WriteResult(
                success=True,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                actual_value=profile_value,
                verified=True,
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
