"""Performance profile manager for SCTRL daemon.

Maps logical profiles (quiet, balanced, performance, turbo) to driver-specific
strings and manages profile transitions with verification and AC power checks.
"""

from __future__ import annotations

import logging
from typing import Any

from sctrl.constants import DEFAULT_PROFILES
from sctrl.errors import HardwareWriteError, UnsupportedError
from sctrl.models import (
    FeatureId,
    FeatureStatus,
    LogicalProfile,
    ProfileState,
)
from daemon.capability_registry import CapabilityRegistry
from daemon.hardware.base import ProfileBackend, WriteResult

logger = logging.getLogger("sctrld.profile_control")

# Standard mapping from LogicalProfile to ACPI / platform_profile values
DEFAULT_LOGICAL_TO_DRIVER: dict[LogicalProfile, str] = {
    LogicalProfile.QUIET: "quiet",
    LogicalProfile.BALANCED: "balanced",
    LogicalProfile.PERFORMANCE: "performance",
    LogicalProfile.TURBO: "turbo",
}

DEFAULT_DRIVER_TO_LOGICAL: dict[str, LogicalProfile] = {
    "quiet": LogicalProfile.QUIET,
    "low-power": LogicalProfile.QUIET,
    "balanced": LogicalProfile.BALANCED,
    "balance": LogicalProfile.BALANCED,
    "performance": LogicalProfile.PERFORMANCE,
    "turbo": LogicalProfile.TURBO,
}


class ProfileManager:
    """Manages performance profile transitions and state tracking."""

    def __init__(
        self,
        backend: ProfileBackend,
        registry: CapabilityRegistry,
        model_profile_mapping: dict[str, str] | None = None,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._logical_to_driver: dict[LogicalProfile, str] = {}
        self._driver_to_logical: dict[str, LogicalProfile] = {}
        self._setup_mapping(model_profile_mapping)

        self._current_logical: LogicalProfile | None = None
        self._last_write_result: WriteResult | None = None

    def _setup_mapping(self, model_mapping: dict[str, str] | None) -> None:
        """Configure logical <-> driver profile mappings."""
        if model_mapping:
            # e.g., {"quiet": "low-power", "balanced": "balanced", "performance": "performance", "turbo": "turbo"}
            for logical_key, driver_str in model_mapping.items():
                try:
                    lp = LogicalProfile(logical_key.lower())
                    self._logical_to_driver[lp] = driver_str
                    self._driver_to_logical[driver_str.lower()] = lp
                except ValueError:
                    logger.warning("Unknown logical profile in model mapping: %s", logical_key)
        else:
            self._logical_to_driver = dict(DEFAULT_LOGICAL_TO_DRIVER)
            self._driver_to_logical = dict(DEFAULT_DRIVER_TO_LOGICAL)

    @property
    def is_supported(self) -> bool:
        cap = self._registry.get(FeatureId.PERFORMANCE_PROFILE)
        return cap is not None and cap.status == FeatureStatus.SUPPORTED

    def get_available_profiles(self) -> list[LogicalProfile]:
        """Return logical profiles supported on this platform."""
        if not self.is_supported:
            return []
        driver_profiles = self._backend.get_available_profiles()
        available: list[LogicalProfile] = []
        for dp in driver_profiles:
            lp = self._driver_to_logical.get(dp.lower())
            if lp and lp not in available:
                available.append(lp)
        return available

    def get_current_profile(self) -> LogicalProfile | None:
        """Query firmware for currently active profile."""
        if not self.is_supported:
            return None
        firmware_str = self._backend.get_current_profile().lower()
        logical = self._driver_to_logical.get(firmware_str)
        if logical:
            self._current_logical = logical
        return self._current_logical

    def get_state(self) -> ProfileState:
        """Get full profile state."""
        firmware_str = self._backend.get_current_profile() if self.is_supported else ""
        applied = self._driver_to_logical.get(firmware_str.lower(), self._current_logical)
        return ProfileState(
            requested=self._current_logical,
            applied=applied,
            firmware_reported=firmware_str,
            available_profiles=self.get_available_profiles(),
            unavailable_reason="" if self.is_supported else "Profile switching not supported or driver missing",
        )

    def set_profile(
        self,
        profile: LogicalProfile,
        is_ac_online: bool | None = None,
    ) -> WriteResult:
        """Switch performance profile.

        Args:
            profile: Target logical profile.
            is_ac_online: Optional flag indicating AC power connection.
                          Turbo mode requires AC power if known.
        """
        if not self.is_supported:
            raise UnsupportedError("Performance profiles are not supported on this system")

        if profile == LogicalProfile.TURBO and is_ac_online is False:
            raise HardwareWriteError(
                "Turbo profile requires AC power connection",
                feature="performance_profile",
            )

        driver_val = self._logical_to_driver.get(profile)
        if not driver_val:
            raise UnsupportedError(f"Profile {profile.value} has no driver mapping")

        available = [p.lower() for p in self._backend.get_available_profiles()]
        if available and driver_val.lower() not in available:
            raise UnsupportedError(
                f"Driver profile '{driver_val}' not in available list: {available}"
            )

        logger.info("Setting performance profile: %s (driver value: %s)", profile.value, driver_val)
        result = self._backend.set_profile(driver_val)
        self._last_write_result = result

        if result.success:
            self._current_logical = profile
            # Update registry capability record
            self._registry.update_value(FeatureId.PERFORMANCE_PROFILE, profile.value)
        else:
            logger.error("Failed to set profile %s: %s", profile.value, result.error)

        return result
