"""Battery charge limit and health controller for SCTRL daemon.

Provides safe control and monitoring for battery charge threshold (e.g. 80% limit)
to prolong battery lifespan.
"""

from __future__ import annotations

import logging
from typing import Any

from sctrl.constants import DEFAULT_CHARGE_LIMIT_PCT
from sctrl.errors import HardwareWriteError, UnsupportedError, ValidationError
from sctrl.models import FeatureId, FeatureStatus, SensorReading
from daemon.capability_registry import CapabilityRegistry
from daemon.hardware.base import BatteryBackend, WriteResult

logger = logging.getLogger("sctrld.battery_control")


class BatteryController:
    """Controls battery charging limits and monitors battery status."""

    def __init__(
        self,
        backend: BatteryBackend,
        registry: CapabilityRegistry,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._target_limit: int | None = None

    @property
    def is_charge_limit_supported(self) -> bool:
        cap = self._registry.get(FeatureId.CHARGE_LIMIT)
        return cap is not None and cap.status == FeatureStatus.SUPPORTED and cap.writable

    @property
    def charge_limit_range(self) -> tuple[int, int]:
        rng = self._backend.get_charge_limit_range()
        if rng:
            return rng
        return (50, 100)

    def get_charge_percent(self) -> SensorReading:
        return self._backend.read_charge_percent()

    def get_charge_state(self) -> str:
        return self._backend.read_charge_state()

    def get_current_limit(self) -> int | None:
        if not self.is_charge_limit_supported:
            return None
        return self._backend.get_charge_limit()

    def set_charge_limit(self, percent: int) -> WriteResult:
        """Set battery charge threshold percentage.

        Args:
            percent: Desired threshold (typically 80% for longevity or 100% for full charge).
        """
        self._registry.check_write_permission(FeatureId.CHARGE_LIMIT)

        if not self.is_charge_limit_supported:
            raise UnsupportedError("Battery charge limit is not supported or not writable on this system")

        min_pct, max_pct = self.charge_limit_range
        if not min_pct <= percent <= max_pct:
            raise ValidationError(
                f"Charge limit {percent}% out of allowed range [{min_pct}, {max_pct}]",
                field="charge_limit",
                value=percent,
            )

        logger.info("Setting battery charge limit to %d%%", percent)
        result = self._backend.set_charge_limit(percent)

        if result.success:
            self._target_limit = percent
            self._registry.update_value(FeatureId.CHARGE_LIMIT, percent)
        else:
            logger.error("Failed to set battery charge limit: %s", result.error)

        return result
