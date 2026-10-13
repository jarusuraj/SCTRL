"""Thermal policy and watchdog for SCTRL daemon.

Monitors temperatures and triggers alerts and emergency overrides
when thresholds are exceeded. Independent of user fan settings.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any, Callable

from sctrl.constants import (
    ALERT_COOLDOWN_S,
    DEFAULT_CPU_CRITICAL_TEMP_C,
    DEFAULT_CPU_WARN_TEMP_C,
    DEFAULT_GPU_CRITICAL_TEMP_C,
    DEFAULT_GPU_WARN_TEMP_C,
    STALE_SENSOR_TIMEOUT_S,
)
from sctrl.models import SensorReading, ValueQuality

logger = logging.getLogger("sctrld.thermal_policy")


@unique
class ThermalState(Enum):
    """Current thermal state."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ThermalAlert:
    """A thermal alert event."""
    sensor: str  # "cpu" or "gpu"
    state: ThermalState
    temp_c: float
    threshold_c: int
    timestamp: float = field(default_factory=time.time)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor": self.sensor,
            "state": self.state.value,
            "temp_c": self.temp_c,
            "threshold_c": self.threshold_c,
            "timestamp": self.timestamp,
            "message": self.message,
        }


@dataclass
class ThermalThresholds:
    """Configurable thermal thresholds.

    These are user-level thresholds, NOT manufacturer limits.
    """
    cpu_warn_c: int = DEFAULT_CPU_WARN_TEMP_C
    cpu_critical_c: int = DEFAULT_CPU_CRITICAL_TEMP_C
    gpu_warn_c: int = DEFAULT_GPU_WARN_TEMP_C
    gpu_critical_c: int = DEFAULT_GPU_CRITICAL_TEMP_C


class ThermalPolicy:
    """Monitors temperatures and manages thermal alerts.

    - Tracks state transitions (normal -> warning -> critical).
    - Enforces alert cooldowns to prevent notification spam.
    - Detects stale sensor data.
    - Triggers emergency callbacks when critical thresholds are exceeded.
    """

    def __init__(
        self,
        thresholds: ThermalThresholds | None = None,
        on_alert: Callable[[ThermalAlert], None] | None = None,
        on_emergency: Callable[[str], None] | None = None,
        cooldown_s: int = ALERT_COOLDOWN_S,
        stale_timeout_s: float = STALE_SENSOR_TIMEOUT_S,
    ) -> None:
        self._thresholds = thresholds or ThermalThresholds()
        self._on_alert = on_alert
        self._on_emergency = on_emergency
        self._cooldown_s = cooldown_s
        self._stale_timeout_s = stale_timeout_s

        self._cpu_state = ThermalState.UNKNOWN
        self._gpu_state = ThermalState.UNKNOWN
        self._last_cpu_alert_time: float = 0.0
        self._last_gpu_alert_time: float = 0.0
        self._alerts_history: list[ThermalAlert] = []

    @property
    def cpu_state(self) -> ThermalState:
        return self._cpu_state

    @property
    def gpu_state(self) -> ThermalState:
        return self._gpu_state

    @property
    def thresholds(self) -> ThermalThresholds:
        return self._thresholds

    def update_thresholds(self, thresholds: ThermalThresholds) -> None:
        """Update thermal thresholds."""
        self._thresholds = thresholds
        logger.info(
            "Thermal thresholds updated: CPU warn=%dC crit=%dC, GPU warn=%dC crit=%dC",
            thresholds.cpu_warn_c,
            thresholds.cpu_critical_c,
            thresholds.gpu_warn_c,
            thresholds.gpu_critical_c,
        )

    def evaluate(
        self,
        cpu_reading: SensorReading | None,
        gpu_reading: SensorReading | None,
        now: float | None = None,
    ) -> list[ThermalAlert]:
        """Evaluate current temperatures against thresholds.

        Args:
            cpu_reading: Current CPU temperature reading.
            gpu_reading: Current GPU temperature reading.
            now: Current monotonic time (for testing).

        Returns:
            List of new alerts generated during this evaluation.
        """
        if now is None:
            now = time.monotonic()

        alerts: list[ThermalAlert] = []

        if cpu_reading:
            cpu_alerts = self._evaluate_sensor(
                "cpu",
                cpu_reading,
                self._thresholds.cpu_warn_c,
                self._thresholds.cpu_critical_c,
                self._cpu_state,
                self._last_cpu_alert_time,
                now,
            )
            if cpu_alerts:
                self._cpu_state = cpu_alerts[-1].state
                self._last_cpu_alert_time = now
                alerts.extend(cpu_alerts)
            elif cpu_reading.is_available and cpu_reading.value is not None:
                new_state = self._compute_state(
                    cpu_reading.value,
                    self._thresholds.cpu_warn_c,
                    self._thresholds.cpu_critical_c,
                )
                self._cpu_state = new_state

        if gpu_reading:
            gpu_alerts = self._evaluate_sensor(
                "gpu",
                gpu_reading,
                self._thresholds.gpu_warn_c,
                self._thresholds.gpu_critical_c,
                self._gpu_state,
                self._last_gpu_alert_time,
                now,
            )
            if gpu_alerts:
                self._gpu_state = gpu_alerts[-1].state
                self._last_gpu_alert_time = now
                alerts.extend(gpu_alerts)
            elif gpu_reading.is_available and gpu_reading.value is not None:
                new_state = self._compute_state(
                    gpu_reading.value,
                    self._thresholds.gpu_warn_c,
                    self._thresholds.gpu_critical_c,
                )
                self._gpu_state = new_state

        self._alerts_history.extend(alerts)
        # Bound history
        if len(self._alerts_history) > 100:
            self._alerts_history = self._alerts_history[-50:]

        return alerts

    def is_sensor_stale(self, reading: SensorReading, now: float | None = None) -> bool:
        """Check if a sensor reading is stale."""
        if now is None:
            now = time.monotonic()
        return (
            reading.quality == ValueQuality.STALE
            or (now - reading.timestamp) > self._stale_timeout_s
        )

    def get_recent_alerts(self, max_count: int = 20) -> list[dict[str, Any]]:
        """Get recent alerts as serializable dicts."""
        return [a.to_dict() for a in self._alerts_history[-max_count:]]

    def _evaluate_sensor(
        self,
        sensor: str,
        reading: SensorReading,
        warn_c: int,
        critical_c: int,
        current_state: ThermalState,
        last_alert_time: float,
        now: float,
    ) -> list[ThermalAlert]:
        """Evaluate a single sensor's temperature."""
        alerts: list[ThermalAlert] = []

        if not reading.is_available or reading.value is None:
            return alerts

        temp = reading.value
        new_state = self._compute_state(temp, warn_c, critical_c)

        # Check cooldown
        if now - last_alert_time < self._cooldown_s and new_state == current_state:
            return alerts

        # State transition
        if new_state != current_state:
            if new_state == ThermalState.CRITICAL:
                alert = ThermalAlert(
                    sensor=sensor,
                    state=ThermalState.CRITICAL,
                    temp_c=temp,
                    threshold_c=critical_c,
                    message=(
                        f"{sensor.upper()} temperature critical: {temp:.1f}C "
                        f"(threshold: {critical_c}C). Note: this is a "
                        "user-configured threshold, not a manufacturer limit."
                    ),
                )
                alerts.append(alert)
                logger.warning(
                    "THERMAL CRITICAL: %s at %.1fC (threshold %dC)",
                    sensor, temp, critical_c,
                )

                # Trigger emergency callback
                if self._on_emergency:
                    self._on_emergency(alert.message)
                if self._on_alert:
                    self._on_alert(alert)

            elif new_state == ThermalState.WARNING:
                alert = ThermalAlert(
                    sensor=sensor,
                    state=ThermalState.WARNING,
                    temp_c=temp,
                    threshold_c=warn_c,
                    message=(
                        f"{sensor.upper()} temperature warning: {temp:.1f}C "
                        f"(threshold: {warn_c}C). Note: this is a "
                        "user-configured threshold, not a manufacturer limit."
                    ),
                )
                alerts.append(alert)
                logger.info(
                    "Thermal warning: %s at %.1fC (threshold %dC)",
                    sensor, temp, warn_c,
                )
                if self._on_alert:
                    self._on_alert(alert)

            elif new_state == ThermalState.NORMAL and current_state in (
                ThermalState.WARNING, ThermalState.CRITICAL,
            ):
                logger.info(
                    "Thermal normalized: %s at %.1fC", sensor, temp,
                )

        return alerts

    @staticmethod
    def _compute_state(temp: float, warn_c: int, critical_c: int) -> ThermalState:
        if temp >= critical_c:
            return ThermalState.CRITICAL
        if temp >= warn_c:
            return ThermalState.WARNING
        return ThermalState.NORMAL
