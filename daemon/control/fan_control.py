"""Fan control manager for SCTRL daemon.

Owns fan-control sessions via a lease mechanism. Manages mode transitions,
custom curves, and emergency thermal overrides.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sctrl.constants import FAN_LEASE_DEFAULT_S, FAN_LEASE_MAX_S
from sctrl.errors import LeaseError, ErrorCode, SCTRLError
from sctrl.models import FanCurve, FanLease, FanMode, FeatureId

# pyrefly: ignore [missing-import]
from daemon.capability_registry import CapabilityRegistry
# pyrefly: ignore [missing-import]
from daemon.control.fan_curve import FanCurveController, validate_fan_curve_strict
from daemon.hardware.base import FanControlBackend, WriteResult

logger = logging.getLogger("sctrld.fan_control")


class FanControlManager:
    """Manages fan control with lease-based ownership.

    - Manual control requires a renewable lease.
    - Expired leases return fans to automatic mode.
    - Emergency thermal override supersedes user settings.
    """

    def __init__(
        self,
        backend: FanControlBackend,
        registry: CapabilityRegistry,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._lease: FanLease | None = None
        self._cpu_controller: FanCurveController | None = None
        self._gpu_controller: FanCurveController | None = None
        self._emergency_active = False
        self._last_write_results: dict[str, WriteResult] = {}

    @property
    def current_mode(self) -> FanMode:
        return self._backend.get_current_mode()

    @property
    def has_active_lease(self) -> bool:
        if self._lease is None:
            return False
        if self._lease.is_expired:
            self._handle_lease_expiry()
            return False
        return True

    @property
    def lease_remaining_s(self) -> int:
        if self._lease is None or self._lease.is_expired:
            return 0
        return max(0, int(self._lease.expires_at - time.monotonic()))

    @property
    def emergency_override_active(self) -> bool:
        return self._emergency_active

    def set_mode_auto(self, holder: str = "system") -> WriteResult:
        """Return fans to automatic firmware control."""
        self._registry.check_write_permission(FeatureId.FAN_MODE)

        result = self._backend.set_mode_auto()
        self._record_write(result)

        if result.success:
            self._release_lease()
            self._emergency_active = False
            logger.info("Fan mode set to auto by %s", holder)

        return result

    def set_mode_max(self, holder: str) -> WriteResult:
        """Set fans to maximum speed."""
        self._registry.check_write_permission(FeatureId.FAN_MODE)

        result = self._backend.set_mode_max()
        self._record_write(result)

        if result.success:
            self._acquire_lease(holder, "both", FanMode.MAX)
            logger.info("Fan mode set to max by %s", holder)

        return result

    def set_custom_curve(
        self,
        holder: str,
        cpu_curve: FanCurve | None = None,
        gpu_curve: FanCurve | None = None,
    ) -> WriteResult:
        """Apply custom fan curves.

        Validates curves and acquires a lease for the fan control session.
        """
        self._registry.check_write_permission(FeatureId.FAN_CURVE)

        if cpu_curve is None and gpu_curve is None:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value="custom",
                backend=self._backend.backend_name,
                error="At least one fan curve must be provided",
            )

        # Validate curves against backend ranges and zero-fan safety
        allow_zero = getattr(self, "_allow_zero_fan", False)
        if cpu_curve:
            cpu_min, cpu_max = self._backend.get_supported_range("cpu")
            validate_fan_curve_strict(cpu_curve, min_speed=cpu_min, max_speed=cpu_max, allow_zero_fan=allow_zero)

        if gpu_curve:
            gpu_min, gpu_max = self._backend.get_supported_range("gpu")
            validate_fan_curve_strict(gpu_curve, min_speed=gpu_min, max_speed=gpu_max, allow_zero_fan=allow_zero)

        # Acquire lease
        target = "both" if (cpu_curve and gpu_curve) else ("cpu" if cpu_curve else "gpu")
        lease = self._acquire_lease(holder, target, FanMode.CUSTOM)

        if cpu_curve:
            self._cpu_controller = FanCurveController(cpu_curve)
            lease.curve = cpu_curve

        if gpu_curve:
            self._gpu_controller = FanCurveController(gpu_curve)
            if lease.curve is None:
                lease.curve = gpu_curve

        logger.info("Custom fan curve set by %s for %s", holder, target)

        return WriteResult(
            success=True,
            feature=FeatureId.FAN_CURVE,
            requested_value="custom",
            actual_value="custom",
            verified=True,
            backend=self._backend.backend_name,
        )

    def apply_curve_tick(self, cpu_temp: float | None, gpu_temp: float | None) -> None:
        """Apply fan curve for current temperatures.

        Called periodically by the monitoring loop. Handles hysteresis
        and dwell time internally.
        """
        if not self.has_active_lease:
            return

        if self._emergency_active:
            return

        now = time.monotonic()

        if self._cpu_controller and cpu_temp is not None:
            speed = self._cpu_controller.compute_speed(cpu_temp, now)
            result = self._backend.set_fan_speed("cpu", speed)
            if not result.success:
                logger.warning("CPU fan speed set failed: %s", result.error)

        if self._gpu_controller and gpu_temp is not None:
            speed = self._gpu_controller.compute_speed(gpu_temp, now)
            result = self._backend.set_fan_speed("gpu", speed)
            if not result.success:
                logger.warning("GPU fan speed set failed: %s", result.error)

    def renew_lease(self, holder: str, duration_s: int | None = None) -> bool:
        """Renew an active lease.

        Args:
            holder: Must match the current lease holder.
            duration_s: Lease duration, clamped to max.

        Returns:
            True if renewed, False if no active lease or holder mismatch.
        """
        if self._lease is None:
            return False

        if self._lease.holder != holder:
            logger.warning("Lease renewal rejected: holder mismatch (%s != %s)", holder, self._lease.holder)
            return False

        if duration_s is None:
            duration_s = FAN_LEASE_DEFAULT_S
        duration_s = min(duration_s, FAN_LEASE_MAX_S)

        self._lease.renew(duration_s)
        logger.debug("Lease renewed for %s: %ds", holder, duration_s)
        return True

    def trigger_emergency_override(self, reason: str) -> WriteResult:
        """Activate emergency thermal override.

        Attempts to return fans to auto or max, whichever the backend
        verifiably supports.
        """
        logger.warning("Emergency thermal override triggered: %s", reason)
        self._emergency_active = True

        # Try auto first (firmware control)
        result = self._backend.set_mode_auto()
        if result.success:
            logger.info("Emergency override: returned to firmware auto")
            return result

        # Fallback to max
        result = self._backend.set_mode_max()
        if result.success:
            logger.info("Emergency override: set fans to maximum")
        else:
            logger.error(
                "Emergency override: FAILED to set safe fan mode: %s", result.error
            )

        return result

    def clear_emergency_override(self) -> None:
        """Clear emergency override flag (after temperatures normalize)."""
        if self._emergency_active:
            self._emergency_active = False
            logger.info("Emergency thermal override cleared")

    def check_lease_expiry(self) -> bool:
        """Check and handle lease expiry.

        Returns True if a lease expired and fans were returned to auto.
        """
        if self._lease is None:
            return False

        if not self._lease.is_expired:
            return False

        self._handle_lease_expiry()
        return True

    def _acquire_lease(
        self, holder: str, target: str, mode: FanMode
    ) -> FanLease:
        """Acquire or replace a fan control lease."""
        self._lease = FanLease(
            holder=holder,
            fan_target=target,
            mode=mode,
            expires_at=time.monotonic() + FAN_LEASE_DEFAULT_S,
        )
        logger.info(
            "Fan control lease acquired: holder=%s, target=%s, mode=%s, expires_in=%ds",
            holder, target, mode.value, FAN_LEASE_DEFAULT_S,
        )
        return self._lease

    def _release_lease(self) -> None:
        """Release the current lease."""
        if self._lease:
            logger.info("Fan control lease released: holder=%s", self._lease.holder)
        self._lease = None
        self._cpu_controller = None
        self._gpu_controller = None

    def _handle_lease_expiry(self) -> None:
        """Handle an expired lease by returning to auto mode."""
        holder = self._lease.holder if self._lease else "unknown"
        logger.warning("Fan control lease expired for %s, returning to auto", holder)
        self._lease = None
        self._cpu_controller = None
        self._gpu_controller = None

        try:
            result = self._backend.set_mode_auto()
            if not result.success:
                logger.error("Failed to return to auto after lease expiry: %s", result.error)
        except Exception as exc:
            logger.error("Exception returning to auto after lease expiry: %s", exc)

    def _record_write(self, result: WriteResult) -> None:
        """Record a write result in the capability registry."""
        self._registry.record_write(result.feature, result.to_dict())
        self._last_write_results[result.feature.value] = result

    def get_state(self) -> dict[str, Any]:
        """Get current fan control state for D-Bus."""
        return {
            "mode": self.current_mode.value,
            "lease_active": self.has_active_lease,
            "lease_remaining_s": self.lease_remaining_s,
            "lease_holder": self._lease.holder if self._lease else "",
            "emergency_override": self._emergency_active,
            "backend": self._backend.backend_name,
        }
