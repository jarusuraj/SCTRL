"""Hardware discovery engine for SCTRL.

Probes the system for available hardware interfaces, sensors, and
drivers. Builds a complete capability map without modifying any hardware.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sctrl.models import (
    CapabilityRecord,
    DMIInfo,
    FeatureId,
    FeatureStatus,
    SupportTier,
)
from sctrl.model_db import ModelDatabase, ModelProfile, TierResult, compute_support_tier

from daemon.hardware.base import (
    BatteryBackend,
    FanControlBackend,
    KeyboardBackend,
    ProfileBackend,
    SensorBackend,
    SystemInfoBackend,
)

logger = logging.getLogger("sctrld.discovery")


@dataclass
class DiscoveryResult:
    """Complete discovery result."""
    dmi: DMIInfo = field(default_factory=DMIInfo)
    tier_result: TierResult = field(
        default_factory=lambda: TierResult(
            tier=SupportTier.UNSUPPORTED,
            reason="Discovery not run",
        )
    )
    profile: ModelProfile | None = None
    capabilities: dict[FeatureId, CapabilityRecord] = field(default_factory=dict)
    active_drivers: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HardwareDiscovery:
    """Orchestrates hardware discovery from all backends.

    Probes each registered backend and assembles a unified capability map.
    Does not modify any hardware state.
    """

    def __init__(
        self,
        model_db: ModelDatabase,
        system_info: SystemInfoBackend,
        sensor: SensorBackend | None = None,
        fan_control: FanControlBackend | None = None,
        profile: ProfileBackend | None = None,
        battery: BatteryBackend | None = None,
        keyboard: KeyboardBackend | None = None,
    ) -> None:
        self._model_db = model_db
        self._system_info = system_info
        self._sensor = sensor
        self._fan_control = fan_control
        self._profile = profile
        self._battery = battery
        self._keyboard = keyboard

    def discover(self) -> DiscoveryResult:
        """Run full hardware discovery.

        Returns:
            DiscoveryResult with DMI, tier, capabilities, and errors.
        """
        result = DiscoveryResult()
        active_drivers: list[str] = []

        # Step 1: Read DMI
        try:
            result.dmi = self._system_info.read_dmi()
        except Exception as exc:
            result.errors.append(f"DMI read failed: {exc}")
            logger.warning("DMI read failed: %s", exc)

        # Step 2: Find model profile
        result.profile = self._model_db.find_profile(result.dmi)

        # Step 3: Compute support tier
        result.tier_result = compute_support_tier(result.dmi, result.profile)

        # Step 4: Probe all backends
        tier = result.tier_result.tier

        # System info capabilities (always available)
        self._probe_system_info(result, active_drivers)

        # Sensor backends
        if self._sensor:
            self._probe_backend(
                self._sensor, "sensor", result, tier, active_drivers
            )

        # Fan control
        if self._fan_control:
            self._probe_backend(
                self._fan_control, "fan_control", result, tier, active_drivers
            )

        # Performance profiles
        if self._profile:
            self._probe_backend(
                self._profile, "profile", result, tier, active_drivers
            )

        # Battery
        if self._battery:
            self._probe_backend(
                self._battery, "battery", result, tier, active_drivers
            )

        # Keyboard
        if self._keyboard:
            self._probe_backend(
                self._keyboard, "keyboard", result, tier, active_drivers
            )

        result.active_drivers = active_drivers
        return result

    def _probe_system_info(
        self,
        result: DiscoveryResult,
        active_drivers: list[str],
    ) -> None:
        """Probe system info backend for CPU/RAM/GPU utilization."""
        backend = self._system_info
        try:
            caps = [
                CapabilityRecord(
                    feature_id=FeatureId.CPU_UTIL,
                    status=FeatureStatus.SUPPORTED,
                    interface=backend.backend_name,
                    readable=True,
                    writable=False,
                    confidence="runtime",
                    tier=result.tier_result.tier,
                ),
                CapabilityRecord(
                    feature_id=FeatureId.RAM_UTIL,
                    status=FeatureStatus.SUPPORTED,
                    interface=backend.backend_name,
                    readable=True,
                    writable=False,
                    confidence="runtime",
                    tier=result.tier_result.tier,
                ),
                CapabilityRecord(
                    feature_id=FeatureId.UPTIME,
                    status=FeatureStatus.SUPPORTED,
                    interface=backend.backend_name,
                    readable=True,
                    writable=False,
                    confidence="runtime",
                    tier=result.tier_result.tier,
                ),
            ]

            # GPU utilization - may not be available
            try:
                gpu_reading = backend.read_gpu_util()
                gpu_status = (
                    FeatureStatus.SUPPORTED
                    if gpu_reading.is_available
                    else FeatureStatus.UNAVAILABLE
                )
            except Exception:
                gpu_status = FeatureStatus.UNAVAILABLE

            caps.append(
                CapabilityRecord(
                    feature_id=FeatureId.GPU_UTIL,
                    status=gpu_status,
                    interface=backend.backend_name,
                    readable=gpu_status == FeatureStatus.SUPPORTED,
                    writable=False,
                    confidence="runtime",
                    tier=result.tier_result.tier,
                )
            )

            for cap in caps:
                result.capabilities[cap.feature_id] = cap

            if backend.backend_name not in active_drivers:
                active_drivers.append(backend.backend_name)

        except Exception as exc:
            result.errors.append(f"System info probe failed: {exc}")
            logger.warning("System info probe failed: %s", exc)

    def _probe_backend(
        self,
        backend: Any,
        category: str,
        result: DiscoveryResult,
        tier: SupportTier,
        active_drivers: list[str],
    ) -> None:
        """Probe a backend and add its capabilities to the result."""
        try:
            caps = backend.probe()
            for cap in caps:
                # Apply tier to each capability
                updated = CapabilityRecord(
                    feature_id=cap.feature_id,
                    status=cap.status,
                    interface=cap.interface,
                    readable=cap.readable,
                    writable=self._filter_writable(cap, tier),
                    current_value=cap.current_value,
                    supported_range=cap.supported_range,
                    supported_values=cap.supported_values,
                    last_probe_time=cap.last_probe_time,
                    last_error=cap.last_error,
                    confidence=cap.confidence,
                    tier=tier,
                )
                result.capabilities[cap.feature_id] = updated

            if backend.backend_name not in active_drivers:
                active_drivers.append(backend.backend_name)

        except Exception as exc:
            result.errors.append(f"{category} probe ({backend.backend_name}) failed: {exc}")
            logger.warning(
                "%s probe (%s) failed: %s", category, backend.backend_name, exc
            )

    def _filter_writable(
        self, cap: CapabilityRecord, tier: SupportTier
    ) -> bool:
        """Determine if a capability should be writable given the tier.

        Tiers 3 (detected) and 4 (unsupported) disable driver-specific writes.
        Standard interfaces (platform_profile, charge_control_end_threshold)
        are permitted on tier 3 with user confirmation.
        """
        if not cap.writable:
            return False

        if tier in (SupportTier.VERIFIED, SupportTier.COMMUNITY):
            return True

        if tier == SupportTier.DETECTED:
            # Only standard interfaces allowed
            standard_features = {
                FeatureId.PERFORMANCE_PROFILE,
                FeatureId.PLATFORM_PROFILE,
                FeatureId.CHARGE_LIMIT,
            }
            return cap.feature_id in standard_features

        # Unsupported: no writes
        return False
